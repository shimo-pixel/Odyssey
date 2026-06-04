import logging
from collections.abc import Awaitable, Callable
from typing import Any

from prds.agents.factory import create_agents
from prds.analysis.counterfactual import analyze_counterfactuals
from prds.analysis.scoring import rank_agents
from prds.analysis.synthesis import synthesize_strategy
from prds.analysis.trajectory import build_agent_decision_paths, build_champion_timeline, build_period_comparisons_from_agents
from prds.config import get_settings
from prds.graph.graphrag import GraphRAGIndexer
from prds.llm.client import LLMClient
from prds.models.domain import (
    AgentState,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    WorldBackground,
    WorldState,
)
from prds.simulation.loop import run_simulation_loop
from prds.world.initializer import initialize_world

logger = logging.getLogger(__name__)

PhaseCallback = Callable[[SimulationPhase, dict[str, Any]], Awaitable[None]]


class SimulationOrchestrator:
    """Runs all 10 PRDS phases in sequence."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(
        self,
        simulation_id: str,
        simulation_input: SimulationInput,
        *,
        on_phase: PhaseCallback | None = None,
        on_period: Callable[[int, int, int], Awaitable[None]] | None = None,
        checkpoint: Callable[[int, list[AgentState], WorldState], Awaitable[None]] | None = None,
        on_pause: Callable[[], Awaitable[None]] | None = None,
        on_resume: Callable[[], Awaitable[None]] | None = None,
    ) -> SimulationResult:
        config = simulation_input.config
        current_state = simulation_input.current_state
        goal = simulation_input.goal
        initial_resources = current_state.resources.model_copy()

        async def phase(p: SimulationPhase, extra: dict[str, Any] | None = None) -> None:
            if on_phase:
                await on_phase(p, extra or {})

        # Phase 1: GraphRAG ontology + knowledge graph
        await phase(SimulationPhase.ONTOLOGY)
        settings = get_settings()
        indexer = GraphRAGIndexer(self.llm, use_graphrag=settings.prds_use_graphrag)
        ontology, kg_data, world_background = await indexer.index(
            simulation_id, current_state, goal
        )

        # Phase 2: World init
        await phase(SimulationPhase.WORLD_INIT)
        world = initialize_world(
            ontology, current_state, goal, config.periods, world_background=world_background
        )

        # Phase 4: Agent spawn
        await phase(SimulationPhase.AGENT_SPAWN, {"agent_count": config.agent_count})
        agents = create_agents(config.agent_count, initial_resources, seed=config.seed)

        # Phase 5-6: Simulation loop
        await phase(SimulationPhase.SIMULATION)

        async def period_callback(
            period: int, alive: int, total: int, current_agents: list[AgentState], current_world: WorldState
        ) -> None:
            if on_period:
                await on_period(period, alive, total)

        agents, final_world = await run_simulation_loop(
            self.llm,
            agents,
            world,
            goal,
            simulation_input,
            run_id=simulation_id,
            on_period_complete=period_callback,
            on_pause=on_pause,
            on_resume=on_resume,
            checkpoint_interval=config.checkpoint_interval,
            on_checkpoint=checkpoint,
            world_background=world_background,
        )

        # Phase 7: Scoring
        await phase(SimulationPhase.SCORING)
        all_ranked = rank_agents(agents, goal, initial_resources, top_n=len(agents))
        top_agents = all_ranked[:20]
        rank_by_id = {score.agent_id: rank for rank, score in enumerate(all_ranked, start=1)}
        champion_id = top_agents[0].agent_id if top_agents else agents[0].agent_id
        champion = next(a for a in agents if a.agent_id == champion_id)

        # Phase 8: Trajectory
        await phase(SimulationPhase.TRAJECTORY)
        champion_timeline = build_champion_timeline(champion)
        agent_paths = build_agent_decision_paths(agents, top_agents, limit=20)
        period_comparisons = build_period_comparisons_from_agents(
            agents,
            rank_by_id=rank_by_id,
            unit=config.period_time_unit,
            length=config.period_time_length,
            start_date=config.simulation_start_date,
        )

        # Phase 9: Counterfactual
        await phase(SimulationPhase.COUNTERFACTUAL)
        counterfactuals = await analyze_counterfactuals(self.llm, champion, goal.description)

        # Phase 10: Synthesis
        await phase(SimulationPhase.SYNTHESIS)
        synthesis = await synthesize_strategy(
            self.llm, champion, top_agents, goal, config.agent_count
        )

        await phase(SimulationPhase.COMPLETED)

        return SimulationResult(
            simulation_id=simulation_id,
            agent_count=config.agent_count,
            periods_simulated=config.periods,
            period_time_unit=config.period_time_unit,
            period_time_length=config.period_time_length,
            simulation_start_date=config.simulation_start_date,
            ontology=ontology,
            knowledge_graph=kg_data,
            top_agents=top_agents,
            champion_agent_id=champion.agent_id,
            champion_strategy=champion.strategy_type,
            champion_timeline=champion_timeline,
            agent_paths=agent_paths,
            period_comparisons=period_comparisons,
            world_background=world_background,
            counterfactuals=counterfactuals,
            synthesis=synthesis,
        )
