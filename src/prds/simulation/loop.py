import asyncio
from collections.abc import Awaitable, Callable

from prds.agents.runtime import run_agents_parallel
from prds.llm.client import LLMClient
from prds.models.domain import AgentState, Event, SimulationInput, TargetGoal, WorldBackground, WorldState
from prds.simulation.control import get_control
from prds.simulation.elimination import apply_elimination
from prds.world.events import EventGenerator


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
    planned_events: dict[int, list[Event]] | None = None,
    on_period_complete: ProgressCallback | None = None,
    on_pause: PauseCallback | None = None,
    on_resume: PauseCallback | None = None,
    checkpoint_interval: int = 5,
    on_checkpoint: Callable[[int, list[AgentState], WorldState], Awaitable[None]] | None = None,
    world_background: WorldBackground | None = None,
    on_period_graph: Callable[[int, list[Event], list[AgentState]], Awaitable[None]] | None = None,
    on_period_prepare: Callable[[int, list[Event], list[AgentState], WorldState], Awaitable[WorldState]] | None = None,
) -> tuple[list[AgentState], WorldState]:
    config = simulation_input.config
    bg = world_background
    event_gen = EventGenerator(
        seed=config.seed,
        world_background=(bg.summary if bg else "") or world.world_background_summary,
        entity_hints=world.graph_entity_hints,
        risks=bg.risks if bg else [],
        opportunities=bg.opportunities if bg else [],
        planned_by_period=planned_events,
    )
    model = config.llm_model or llm.default_model
    control = get_control()

    current_world = world.model_copy(update={"period": 0})

    for period in range(1, config.periods + 1):
        user_events = control.pop_events_for_period(run_id, period) if run_id else []
        generated = event_gen.events_for_period(period)
        events = user_events + generated
        current_world = event_gen.apply_events_to_world(
            current_world.model_copy(update={"period": period}),
            events,
        )

        if on_period_prepare:
            current_world = await on_period_prepare(period, events, agents, current_world)

        agents = await run_agents_parallel(
            llm,
            agents,
            current_world,
            goal,
            model=model,
            domain_id=config.domain_id,
            param_overrides=config.param_overrides,
        )
        agents = apply_elimination(agents, goal, current_world, domain_id=config.domain_id)

        if on_period_graph:
            await on_period_graph(period, events, agents)

        alive = sum(1 for a in agents if not a.eliminated)
        if on_period_complete:
            await on_period_complete(period, alive, len(agents), agents, current_world)
        if on_checkpoint and period % checkpoint_interval == 0:
            await on_checkpoint(period, agents, current_world)

        if alive == 0:
            break

        if run_id and period < config.periods:
            async def _on_paused() -> None:
                if on_pause:
                    await on_pause()

            async def _on_resumed() -> None:
                if on_resume:
                    await on_resume()

            await control.maybe_pause_after_period(run_id, on_paused=_on_paused, on_resumed=_on_resumed)

    return agents, current_world
