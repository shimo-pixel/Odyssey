import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from prds.api.schemas.responses import SimulationInput, SimulationProgress, SimulationResult
from prds.config import get_settings
from prds.intake.refine import RefinedProposal, RefineRequest, refine_user_input
from prds.llm.client import LLMClient
from prds.models.domain import SimulationPhase, SimulationStatus, UserEventInput
from prds.simulation.control import get_control
from prds.graph.neo4j_store import get_neo4j_store
from prds.graph.graphiti_store import get_graphiti_store
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


def get_llm_client() -> LLMClient:
    return LLMClient(get_settings())


async def _run_simulation(run_id: str, simulation_input: SimulationInput) -> None:
    repo = get_repo()
    llm = get_llm_client()
    orchestrator = SimulationOrchestrator(llm)
    total_events = simulation_input.config.max_events

    try:
        await repo.update_progress(
            run_id,
            status=SimulationStatus.RUNNING,
            phase=SimulationPhase.ONTOLOGY,
            progress_pct=0.0,
        )

        async def on_phase(phase: SimulationPhase, extra: dict) -> None:
            base_pct = {
                SimulationPhase.RESEARCH: 2,
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

        async def on_event(event_index: int, alive: int, total: int) -> None:
            denom = max(total_events, 1)
            sim_pct = 15 + (event_index / denom) * 65
            await repo.update_progress(
                run_id,
                current_event_index=event_index,
                alive_agents=alive,
                progress_pct=sim_pct,
            )

        async def checkpoint(event_index: int, agents, world) -> None:
            await repo.save_checkpoint(run_id, event_index, agents, world)

        async def on_pause() -> None:
            await repo.update_progress(run_id, status=SimulationStatus.PAUSED)

        async def on_resume() -> None:
            await repo.update_progress(run_id, status=SimulationStatus.RUNNING)

        result = await orchestrator.run(
            run_id,
            simulation_input,
            on_phase=on_phase,
            on_event=on_event,
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


@router.post("/refine", response_model=RefinedProposal)
async def refine_simulation_input(req: RefineRequest) -> RefinedProposal:
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="LLM API key is not configured. Set OPENAI_API_KEY or DEEPSEEK_API_KEY in .env.",
        )
    if not req.background.strip() or not req.goal.strip():
        raise HTTPException(status_code=422, detail="background and goal are required")
    llm = get_llm_client()
    try:
        return await refine_user_input(llm, req)
    except Exception as exc:
        logger.exception("Input refinement failed")
        raise HTTPException(status_code=502, detail=f"Refinement failed: {exc}") from exc


@router.post("", response_model=dict)
async def create_simulation(
    simulation_input: SimulationInput,
    background_tasks: BackgroundTasks,
) -> dict:
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="LLM API key is not configured. Set OPENAI_API_KEY or DEEPSEEK_API_KEY in .env.",
        )
    repo = get_repo()
    run_id = await repo.create_run(simulation_input)
    background_tasks.add_task(_run_simulation, run_id, simulation_input)
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

    settings = get_settings()

    # Graphiti backend: read the live, episode-driven graph straight from Neo4j so
    # the visualization reflects growth while the simulation is still running.
    if settings.resolved_graph_backend() == "graphiti":
        store = get_graphiti_store()
        if store.available:
            data = await store.get_graph_data(simulation_id)
            if data and data.get("nodes"):
                summary = ""
                if progress.status == SimulationStatus.COMPLETED:
                    result = await repo.get_result(simulation_id)
                    if result:
                        summary = result.world_background.summary
                return {
                    "simulation_id": simulation_id,
                    "knowledge_graph": {"nodes": data["nodes"], "edges": data["edges"]},
                    "graph_source": "graphiti",
                    "building": progress.status != SimulationStatus.COMPLETED,
                    "world_background": {
                        "summary": summary,
                        "graph_source": "graphiti",
                        "neo4j_persisted": True,
                    },
                }

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
        "graph_source": result.world_background.graph_source,
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
