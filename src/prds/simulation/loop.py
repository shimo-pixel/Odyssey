import asyncio
from collections.abc import Awaitable, Callable

from prds.agents.runtime import run_agents_parallel
from prds.llm.client import LLMClient
from prds.models.domain import AgentState, Event, SimulationInput, TargetGoal, WorldBackground, WorldState
from prds.simulation.control import get_control
from prds.simulation.elimination import apply_elimination
from prds.world.events import EventProcessor


ProgressCallback = Callable[[int, int, int, list[AgentState], WorldState], Awaitable[None]]
PauseCallback = Callable[[], Awaitable[None]]


async def run_simulation_loop(
    llm: LLMClient,
    agents: list[AgentState],
    world: WorldState,
    goal: TargetGoal,
    simulation_input: SimulationInput,
    *,
    run_id: str | None = None,
    planned_events: list[Event] | None = None,
    on_event_complete: ProgressCallback | None = None,
    on_pause: PauseCallback | None = None,
    on_resume: PauseCallback | None = None,
    on_checkpoint: Callable[[int, list[AgentState], WorldState], Awaitable[None]] | None = None,
    world_background: WorldBackground | None = None,
    on_event_graph: Callable[[int, Event, list[AgentState]], Awaitable[None]] | None = None,
    on_event_prepare: Callable[[int, Event, list[AgentState], WorldState], Awaitable[WorldState]] | None = None,
) -> tuple[list[AgentState], WorldState]:
    config = simulation_input.config
    bg = world_background
    processor = EventProcessor(
        world_background=(bg.summary if bg else "") or world.world_background_summary,
        entity_hints=world.graph_entity_hints,
        risks=bg.risks if bg else [],
        opportunities=bg.opportunities if bg else [],
    )
    model = config.llm_model or llm.default_model
    control = get_control()

    queue = list(planned_events or [])
    total = len(queue)
    current_world = world.model_copy(update={"event_index": 0, "total_events": total})

    for idx, primary_event in enumerate(queue, start=1):
        user_events = control.pop_user_events(run_id, idx) if run_id else []
        batch = [primary_event, *user_events]

        current_world = processor.apply_events_to_world(
            current_world,
            batch,
            event_index=idx,
        )

        if on_event_prepare:
            current_world = await on_event_prepare(idx, primary_event, agents, current_world)

        agents = await run_agents_parallel(
            llm,
            agents,
            current_world,
            goal,
            model=model,
            domain_id=config.domain_id,
            param_overrides=config.param_overrides,
            trigger_event=primary_event,
        )
        agents = apply_elimination(agents, goal, current_world, domain_id=config.domain_id)

        if on_event_graph:
            await on_event_graph(idx, primary_event, agents)

        alive = sum(1 for a in agents if not a.eliminated)
        if on_event_complete:
            await on_event_complete(idx, alive, len(agents), agents, current_world)
        if on_checkpoint and idx % 5 == 0:
            await on_checkpoint(idx, agents, current_world)

        if alive == 0:
            break

        if run_id and idx < total:
            async def _on_paused() -> None:
                if on_pause:
                    await on_pause()

            async def _on_resumed() -> None:
                if on_resume:
                    await on_resume()

            await control.maybe_pause_after_event(run_id, on_paused=_on_paused, on_resumed=_on_resumed)

    return agents, current_world
