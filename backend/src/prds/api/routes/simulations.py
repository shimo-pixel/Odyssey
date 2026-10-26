import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query

from prds.api.schemas.responses import SimulationInput, SimulationProgress, SimulationResult
from prds.config import get_settings, Settings
from prds.kb.client import LightRAGClient
from prds.kbsim.branches import delete_simulation_branches
from prds.kbsim.orchestrator import KbSimOrchestrator
from prds.llm.client import LLMClient
from prds.models.domain import SimulationPhase, SimulationStatus, UserEventInput, ModelInfo
from prds.simulation.control import get_control
from prds.simulation.tasks import get_tasks
from prds.simulation.errors import SimulationFailure
from prds.kb.settings_store import get_model_entry, settings_from_model_entry
from prds.storage.repository import SimulationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulations", tags=["simulations"])

_repo: SimulationRepository | None = None


def get_repo() -> SimulationRepository:
    global _repo
    if _repo is None:
        _repo = SimulationRepository()
    return _repo


async def _run_simulation(run_id: str, simulation_input: SimulationInput, settings: Settings) -> None:
    repo = get_repo()
    current_phase = SimulationPhase.INTAKE
    try:
        llm = LLMClient(settings)
        orchestrator = KbSimOrchestrator(llm, settings)
        await repo.update_progress(run_id, status=SimulationStatus.RUNNING,
                                   phase=current_phase, progress_pct=0.0)

        async def on_phase(phase: SimulationPhase, extra: dict) -> None:
            nonlocal current_phase
            current_phase = phase
            base_pct = {
                SimulationPhase.INTAKE: 3, SimulationPhase.KB_SNAPSHOT: 6,
                SimulationPhase.EVENT_PLAN: 10, SimulationPhase.BRANCH_FORK: 15,
                SimulationPhase.BRANCH_SIM: 18, SimulationPhase.SCORING: 85,
                SimulationPhase.SYNTHESIS: 92, SimulationPhase.CLEANUP: 97,
                SimulationPhase.COMPLETED: 100,
            }.get(phase, 0)
            await repo.update_progress(run_id, phase=phase, progress_pct=float(base_pct),
                                      warnings=extra.get("warnings"), total_events=extra.get("total_events"))

        async def on_event(event_index, alive, total):
            await repo.update_progress(run_id, current_event_index=event_index,
                alive_agents=alive, progress_pct=18 + event_index / max(total, 1) * 65,
                warnings=orchestrator.warnings)

        async def checkpoint(event_index, states):
            await repo.save_checkpoint(run_id, event_index, states)

        async def on_pause():
            await repo.update_progress(run_id, status=SimulationStatus.PAUSED)

        async def on_resume():
            await repo.update_progress(run_id, status=SimulationStatus.RUNNING)

        result = await orchestrator.run(run_id, simulation_input, on_phase=on_phase,
            on_event=on_event, checkpoint=checkpoint, on_pause=on_pause, on_resume=on_resume)
        await repo.save_result(run_id, result)
    except asyncio.CancelledError:
        await repo.update_progress(run_id, status=(SimulationStatus.INTERRUPTED if get_tasks().shutting_down else SimulationStatus.CANCELLED))
        raise
    except Exception as exc:
        failure = exc if isinstance(exc, SimulationFailure) else SimulationFailure(current_phase.value)
        # Avoid returning/logging raw provider responses, URLs containing keys, or prompts.
        logger.error("Simulation %s failed: %s", run_id, failure.issue.model_dump())
        await repo.update_progress(run_id, status=SimulationStatus.FAILED,
                                  phase=SimulationPhase.FAILED, error=str(failure), failure=failure.issue)
    finally:
        get_control().cleanup(run_id)


async def _create_run(simulation_input: SimulationInput) -> dict:
    config = simulation_input.config
    settings = get_settings().model_copy(deep=True)
    info = None
    if config.model_id:
        entry = await get_model_entry(config.model_id, strict=True)
        if entry is None:
            raise HTTPException(status_code=422, detail="Selected model no longer exists. Select another model.")
        if not entry.get("api_key") or not entry.get("model"):
            raise HTTPException(status_code=422, detail="Selected model is not configured")
        settings = settings_from_model_entry(entry).model_copy(deep=True)
        info = ModelInfo(model_id=entry["id"], name=entry.get("name") or entry["model"],
                         model=entry["model"], analysis_model=entry["model"], provider=entry.get("provider") or "")
    else:
        settings.prds_llm_model = config.llm_model or settings.prds_llm_model
        settings.prds_llm_model_analysis = config.llm_model_analysis or settings.prds_llm_model_analysis
        info = ModelInfo(model=settings.prds_llm_model, analysis_model=settings.prds_llm_model_analysis,
                         provider=settings.prds_llm_provider)
    if not settings.llm_configured:
        raise HTTPException(status_code=503, detail="LLM API key is not configured")
    if not simulation_input.goal.description.strip():
        raise HTTPException(status_code=422, detail="goal.description is required")
    steps = config.agent_count * config.max_events
    if steps > settings.prds_kbsim_max_steps:
        raise HTTPException(status_code=422, detail=f"策略数量 × 事件数量 = {steps}，超过上限 {settings.prds_kbsim_max_steps}。")
    run_id = await get_repo().create_run(simulation_input, info)
    get_tasks().start(run_id, _run_simulation(run_id, simulation_input, settings))
    return {"simulation_id": run_id, "status": "pending"}


@router.post("", response_model=dict)
async def create_simulation(simulation_input: SimulationInput) -> dict:
    return await _create_run(simulation_input)


@router.get("")
async def list_simulations(limit: int = Query(50, ge=1, le=200)) -> dict:
    """Return simulation history summaries for the history card grid."""
    repo = get_repo()
    runs = await repo.list_runs(limit=limit)
    items = []
    for run in runs:
        goal = ""
        background_preview = ""
        agent_count = run.total_agents
        try:
            payload = json.loads(run.input_json or "{}")
            goal = (payload.get("goal") or {}).get("description") or ""
            background = (payload.get("current_state") or {}).get("background") or ""
            background_preview = background[:160] + ("…" if len(background) > 160 else "")
            cfg = payload.get("config") or {}
            if cfg.get("agent_count"):
                agent_count = int(cfg["agent_count"])
        except Exception:
            pass
        items.append(
            {
                "id": run.id,
                "status": run.status,
                "phase": run.phase,
                "progress_pct": run.progress_pct,
                "current_event_index": run.current_event_index,
                "total_events": run.total_events,
                "goal": goal,
                "background_preview": background_preview,
                "agent_count": agent_count,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
                "error": run.error,
                "model_info": json.loads(run.model_info_json) if run.model_info_json else None,
                "warnings": json.loads(run.warnings_json or "[]"),
                "failure": json.loads(run.failure_json) if run.failure_json else None,
            }
        )
    return {"simulations": items}


async def _cancel_run(simulation_id: str) -> None:
    if not await get_tasks().cancel(simulation_id):
        raise HTTPException(status_code=409, detail="Task is still stopping; retry shortly")
    progress = await get_repo().get_progress(simulation_id)
    if progress and progress.status in (SimulationStatus.PENDING, SimulationStatus.RUNNING, SimulationStatus.PAUSED):
        await get_repo().update_progress(simulation_id, status=SimulationStatus.CANCELLED)
    get_control().cleanup(simulation_id)


@router.post("/{simulation_id}/cancel")
async def cancel_simulation(simulation_id: str) -> dict:
    if not await get_repo().get_progress(simulation_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    await _cancel_run(simulation_id)
    progress = await get_repo().get_progress(simulation_id)
    return {"simulation_id": simulation_id, "status": progress.status.value}


@router.post("/{simulation_id}/retry")
async def retry_simulation(simulation_id: str, payload: dict | None = None) -> dict:
    progress = await get_repo().get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status not in (SimulationStatus.FAILED, SimulationStatus.CANCELLED, SimulationStatus.INTERRUPTED):
        raise HTTPException(status_code=409, detail="Only stopped or interrupted runs can be retried")
    original = await get_repo().get_input(simulation_id)
    if payload and payload.get("model_id"):
        original.config.model_id = str(payload["model_id"])
        original.config.llm_model = original.config.llm_model_analysis = None
    return await _create_run(original)


@router.delete("/{simulation_id}")
async def delete_simulation(simulation_id: str) -> dict:
    repo = get_repo()
    if not await repo.get_progress(simulation_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    await _cancel_run(simulation_id)
    try:
        async with asyncio.timeout(20):
            await delete_simulation_branches(LightRAGClient(get_settings()), simulation_id)
    except Exception:
        raise HTTPException(status_code=503, detail="Knowledge graph cleanup failed; record retained. Retry deletion.") from None
    if not await repo.delete_run(simulation_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return {"simulation_id": simulation_id, "deleted": True}


@router.get("/{simulation_id}", response_model=SimulationProgress)
async def get_simulation_status(simulation_id: str) -> SimulationProgress:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return progress


@router.get("/{simulation_id}/result", response_model=SimulationResult)
async def get_simulation_result(simulation_id: str) -> SimulationResult:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status != SimulationStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Simulation not completed (status={progress.status.value})",
        )
    result = await repo.get_result(simulation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@router.get("/{simulation_id}/decisions")
async def list_simulation_decisions(
    simulation_id: str,
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status != SimulationStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Simulation not completed")
    data = await repo.list_agent_decisions(simulation_id, limit=limit)
    return {"simulation_id": simulation_id, **data}


@router.get("/{simulation_id}/agents")
async def list_simulation_agents(
    simulation_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    agents = await repo.list_agents_from_result(simulation_id, offset=offset, limit=limit)
    return {"simulation_id": simulation_id, "agents": agents, "offset": offset, "limit": limit}


@router.get("/{simulation_id}/knowledge-graph")
async def get_knowledge_graph(simulation_id: str) -> dict:
    """Expose the branch knowledge bases so each parallel world's graph is browsable."""
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")

    if progress.status != SimulationStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Simulation not completed")
    result = await repo.get_result(simulation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    branches = [
        {
            "branch_id": b.branch_id,
            "label": b.label,
            "rationality": b.rationality.value,
            "rank": b.rank,
            "workspaces": b.workspaces,
        }
        for b in result.branches
    ]
    return {
        "simulation_id": simulation_id,
        "branches": branches,
        "knowledge_graph": result.knowledge_graph.model_dump(),
        "ontology": result.ontology.model_dump(),
        "world_background": result.world_background.model_dump(),
        "graph_source": "lightrag",
    }


@router.post("/{simulation_id}/pause")
async def pause_simulation(simulation_id: str) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status not in (SimulationStatus.RUNNING, SimulationStatus.PAUSED):
        raise HTTPException(status_code=409, detail=f"Cannot pause (status={progress.status.value})")
    if progress.phase != SimulationPhase.BRANCH_SIM:
        raise HTTPException(status_code=409, detail="Pause is only available during the simulation phase")
    if progress.status == SimulationStatus.PAUSED:
        return {"simulation_id": simulation_id, "status": "paused", "message": "Already paused"}
    if not progress.can_pause:
        raise HTTPException(status_code=409, detail="The final event has started; pause is unavailable")
    get_control().request_pause(simulation_id)
    return {"simulation_id": simulation_id, "status": "pause_requested", "message": "Will pause after current event"}


@router.post("/{simulation_id}/resume")
async def resume_simulation(simulation_id: str) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status != SimulationStatus.PAUSED:
        raise HTTPException(status_code=409, detail=f"Simulation is not paused (status={progress.status.value})")
    if not get_control().resume(simulation_id):
        raise HTTPException(status_code=409, detail="Resume signal failed")
    return {
        "simulation_id": simulation_id,
        "status": "running",
        "pending_events_injected_next_event": progress.pending_user_events,
    }


@router.get("/{simulation_id}/events")
async def list_user_events(simulation_id: str) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    events = get_control().list_pending_user_events(simulation_id)
    return {
        "simulation_id": simulation_id,
        "status": progress.status.value,
        "events": [e.model_dump() for e in events],
    }


@router.post("/{simulation_id}/events")
async def add_user_event(simulation_id: str, event: UserEventInput) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status != SimulationStatus.PAUSED or not get_control().is_paused(simulation_id):
        raise HTTPException(status_code=409, detail="Events can only be added while simulation is paused")
    saved = get_control().add_user_event(simulation_id, event)
    return {
        "simulation_id": simulation_id,
        "event": saved.model_dump(),
        "pending_count": get_control().pending_event_count(simulation_id),
    }


@router.delete("/{simulation_id}/events")
async def clear_user_events(simulation_id: str) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status != SimulationStatus.PAUSED:
        raise HTTPException(status_code=409, detail="Events can only be cleared while simulation is paused")
    get_control().clear_pending_user_events(simulation_id)
    return {"simulation_id": simulation_id, "pending_count": 0}
