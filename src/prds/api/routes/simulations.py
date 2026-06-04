import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from prds.api.schemas.responses import SimulationInput, SimulationProgress, SimulationResult
from prds.config import get_settings
from prds.llm.client import LLMClient, MockLLMClient
from prds.models.domain import SimulationPhase, SimulationStatus, UserEventInput
from prds.simulation.control import get_control
from prds.graph.neo4j_store import get_neo4j_store
from prds.simulation.orchestrator import SimulationOrchestrator
from prds.storage.repository import SimulationRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/simulations", tags=["simulations"])

_repo: SimulationRepository | None = None


def get_repo() -> SimulationRepository:
    global _repo
    if _repo is None:
        _repo = SimulationRepository()
    return _repo


def get_llm_client(use_mock: bool = False) -> LLMClient:
    settings = get_settings()
    if use_mock or not settings.openai_api_key:
        return MockLLMClient()
    return LLMClient(settings)


async def _run_simulation(run_id: str, simulation_input: SimulationInput, use_mock: bool) -> None:
    repo = get_repo()
    llm = get_llm_client(use_mock=use_mock)
    orchestrator = SimulationOrchestrator(llm)
    total_periods = simulation_input.config.periods

    try:
        await repo.update_progress(
            run_id,
            status=SimulationStatus.RUNNING,
            phase=SimulationPhase.ONTOLOGY,
            progress_pct=0.0,
        )

        async def on_phase(phase: SimulationPhase, extra: dict) -> None:
            base_pct = {
                SimulationPhase.ONTOLOGY: 5,
                SimulationPhase.WORLD_INIT: 10,
                SimulationPhase.AGENT_SPAWN: 15,
                SimulationPhase.SIMULATION: 80,
                SimulationPhase.SCORING: 85,
                SimulationPhase.TRAJECTORY: 90,
                SimulationPhase.COUNTERFACTUAL: 95,
                SimulationPhase.SYNTHESIS: 98,
                SimulationPhase.COMPLETED: 100,
            }.get(phase, 0)
            await repo.update_progress(run_id, phase=phase, progress_pct=float(base_pct))

        async def on_period(period: int, alive: int, total: int) -> None:
            sim_pct = 15 + (period / total_periods) * 65
            await repo.update_progress(
                run_id,
                current_period=period,
                alive_agents=alive,
                progress_pct=sim_pct,
            )

        async def checkpoint(period: int, agents, world) -> None:
            await repo.save_checkpoint(run_id, period, agents, world)

        async def on_pause() -> None:
            await repo.update_progress(run_id, status=SimulationStatus.PAUSED)

        async def on_resume() -> None:
            await repo.update_progress(run_id, status=SimulationStatus.RUNNING)

        result = await orchestrator.run(
            run_id,
            simulation_input,
            on_phase=on_phase,
            on_period=on_period,
            checkpoint=checkpoint,
            on_pause=on_pause,
            on_resume=on_resume,
        )
        await repo.save_result(run_id, result)
        get_control().cleanup(run_id)
    except Exception as exc:
        logger.exception("Simulation %s failed", run_id)
        get_control().cleanup(run_id)
        await repo.update_progress(
            run_id,
            status=SimulationStatus.FAILED,
            phase=SimulationPhase.FAILED,
            error=str(exc)[:1000],
        )


@router.post("", response_model=dict)
async def create_simulation(
    simulation_input: SimulationInput,
    background_tasks: BackgroundTasks,
    use_mock: bool = Query(False, description="Use mock LLM for testing without API key"),
) -> dict:
    repo = get_repo()
    run_id = await repo.create_run(simulation_input)
    background_tasks.add_task(_run_simulation, run_id, simulation_input, use_mock)
    return {"simulation_id": run_id, "status": "pending"}


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
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")

    neo4j = get_neo4j_store()
    if neo4j.available:
        loaded = await neo4j.load_simulation_graph(simulation_id)
        if loaded:
            return {"simulation_id": simulation_id, **loaded}

    if progress.status != SimulationStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Simulation not completed")
    result = await repo.get_result(simulation_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return {
        "simulation_id": simulation_id,
        "knowledge_graph": result.knowledge_graph.model_dump(),
        "ontology": result.ontology.model_dump(),
        "world_background": result.world_background.model_dump(),
    }


@router.post("/{simulation_id}/pause")
async def pause_simulation(simulation_id: str) -> dict:
    repo = get_repo()
    progress = await repo.get_progress(simulation_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if progress.status not in (SimulationStatus.RUNNING, SimulationStatus.PAUSED):
        raise HTTPException(status_code=409, detail=f"Cannot pause (status={progress.status.value})")
    if progress.phase != SimulationPhase.SIMULATION:
        raise HTTPException(status_code=409, detail="Pause is only available during the simulation phase")
    if progress.status == SimulationStatus.PAUSED:
        return {"simulation_id": simulation_id, "status": "paused", "message": "Already paused"}
    get_control().request_pause(simulation_id)
    return {"simulation_id": simulation_id, "status": "pause_requested", "message": "Will pause after current period"}


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
        "pending_events_injected_next_period": progress.pending_user_events,
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
    if progress.status != SimulationStatus.PAUSED:
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
