import logging
from collections.abc import Awaitable, Callable
from typing import Any

from prds.agents.factory import create_agents
from prds.analysis.distribution import build_outcome_distribution
from prds.analysis.patterns import build_data_driven_counterfactuals, build_data_driven_synthesis
from prds.analysis.scoring import rank_agents
from prds.analysis.trajectory import build_agent_decision_paths, build_champion_timeline, build_period_comparisons_from_agents
from prds.config import get_settings
from prds.graph.dynamic import extract_domain_facts
from prds.graph.episodic import create_episodic_session
from prds.graph.graphrag import GraphRAGIndexer, compose_document
from prds.graph.neo4j_store import get_neo4j_store
from prds.llm.client import LLMClient
from prds.models.domain import (
    AgentState,
    BackgroundReport,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    WorldBackground,
    WorldState,
)
from prds.research import generate_background_report
from prds.simulation.loop import run_simulation_loop
from prds.world.event_planner import plan_event_timeline
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
        initial_resources = current_state.resources.model_copy()
        goal = simulation_input.goal.model_copy(update={"baseline_snapshot": initial_resources})

        async def phase(p: SimulationPhase, extra: dict[str, Any] | None = None) -> None:
            if on_phase:
                await on_phase(p, extra or {})

        settings = get_settings()

        # Phase 0: Industry background research (step ②)
        await phase(SimulationPhase.RESEARCH)
        report: BackgroundReport | None = None
        try:
            report = await generate_background_report(
                self.llm,
                background=current_state.background,
                goal=goal.description,
                constraints=list(current_state.constraints),
                domain_id=config.domain_id,
                settings=settings,
            )
            logger.info(
                "Background report ready (provider=%s, %d chars, %d citations)",
                report.provider,
                len(report.report),
                len(report.citations),
            )
        except Exception as exc:
            logger.warning("Background research skipped due to error: %s", exc)
            report = None

        # Phase 1: GraphRAG ontology + knowledge graph (grounded in the report)
        await phase(SimulationPhase.ONTOLOGY)
        indexer = GraphRAGIndexer(self.llm, use_graphrag=settings.prds_use_graphrag)
        ontology, kg_data, world_background = await indexer.index(
            simulation_id, current_state, goal, report=report
        )

        # Phase 2: World init
        await phase(SimulationPhase.WORLD_INIT)
        world = initialize_world(
            ontology, current_state, goal, config.periods, world_background=world_background
        )

        # Phase 4: Agent spawn
        await phase(SimulationPhase.AGENT_SPAWN, {"agent_count": config.agent_count})
        agents = create_agents(config.agent_count, initial_resources, seed=config.seed)

        event_calendar = await plan_event_timeline(
            self.llm,
            current_state,
            goal,
            config,
            world_background=world_background,
            ontology=ontology,
            report=report,
        )

        # Steps ③-⑤: seed agents' grounding from the ontology graph, then grow the
        # knowledge graph incrementally during the run (events/agents enter the graph
        # period by period — "hop by hop" — rather than being dumped up front).
        domain_brief = (report.key_findings[:6] if report else []) or world_background.community_summaries[:3]
        world = world.model_copy(
            update={
                "domain_brief": list(domain_brief),
                "domain_facts": extract_domain_facts(kg_data),
            }
        )
        # Episode-driven graph growth: Graphiti+Neo4j when configured, else builtin.
        graph_session = await create_episodic_session(
            self.llm,
            simulation_id,
            kg_data,
            world_summary=world_background.summary,
            model=config.llm_model or self.llm.default_model,
            settings=settings,
        )
        if graph_session.backend == "graphiti":
            world_background.graph_source = "graphiti"
        try:
            await graph_session.seed(compose_document(current_state, goal, report))
        except Exception as exc:
            logger.warning("Graph seed episode failed: %s", exc)
        try:
            await graph_session.register_agents(agents, goal_description=goal.description)
        except Exception as exc:
            logger.warning("Agent ontology registration failed: %s", exc)

        async def _refresh_world_kg(current_world: WorldState) -> WorldState:
            snap = await graph_session.graph_data()
            if not snap:
                return current_world
            return current_world.model_copy(
                update={
                    "knowledge_graph": snap,
                    "domain_facts": extract_domain_facts(snap),
                }
            )

        world = await _refresh_world_kg(world)
        neo4j = get_neo4j_store()

        # Phase 5-6: Simulation loop (primary replication, with checkpoints/callbacks)
        await phase(SimulationPhase.SIMULATION)

        async def period_callback(
            period: int, alive: int, total: int, current_agents: list[AgentState], current_world: WorldState
        ) -> None:
            if on_period:
                await on_period(period, alive, total)

        async def prepare_world(
            period: int, events, current_agents: list[AgentState], current_world: WorldState
        ) -> WorldState:
            return await _refresh_world_kg(current_world)

        async def grow_graph(period: int, events, current_agents: list[AgentState]) -> None:
            try:
                await graph_session.ingest_period(period, events, current_agents)
            except Exception as exc:
                logger.warning("Graph period ingest failed (period %s): %s", period, exc)

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
            planned_events=event_calendar,
            on_period_prepare=prepare_world,
            on_period_graph=grow_graph,
        )

        # Finalize the evolved graph. Graphiti already persists to Neo4j itself;
        # the builtin backend is mirrored into our own Neo4j store when available.
        evolved = await graph_session.graph_data()
        if evolved is not None and evolved.nodes:
            kg_data = evolved
        if graph_session.backend == "graphiti":
            world_background.neo4j_persisted = bool(evolved and evolved.nodes)
        elif neo4j.available:
            try:
                persisted = await neo4j.save_simulation_graph(simulation_id, kg_data, world_background)
                world_background.neo4j_persisted = persisted
            except Exception as exc:
                logger.warning("Failed to persist grown graph to Neo4j: %s", exc)

        # Extra replications with different seeds -> wider uncertainty sample.
        pooled_agents: list[AgentState] = list(agents)
        base_seed = config.seed if config.seed is not None else 0
        for rep in range(1, config.replications):
            rep_agents = create_agents(
                config.agent_count, initial_resources, seed=base_seed + rep * 1000 + 1
            )
            rep_agents, _ = await run_simulation_loop(
                self.llm,
                rep_agents,
                world,
                goal,
                simulation_input,
                run_id=None,
                world_background=world_background,
                planned_events=event_calendar,
            )
            pooled_agents.extend(rep_agents)

        # Phase 7: Scoring (display ranking on primary replication for stable IDs)
        await phase(SimulationPhase.SCORING)
        all_ranked = rank_agents(agents, goal, initial_resources, top_n=len(agents), domain_id=config.domain_id)
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

        # Uncertainty: aggregate the full pool into distributions, not a single point.
        distribution = build_outcome_distribution(
            pooled_agents,
            goal,
            domain_id=config.domain_id,
            replications=config.replications,
            param_overrides=config.param_overrides,
        )

        # Phase 9: Counterfactual (data-driven from the pooled paths)
        await phase(SimulationPhase.COUNTERFACTUAL)
        counterfactuals = build_data_driven_counterfactuals(
            pooled_agents, goal, domain_id=config.domain_id
        )

        # Phase 10: Synthesis (data-driven statistics, not free-form LLM)
        await phase(SimulationPhase.SYNTHESIS)
        synthesis = build_data_driven_synthesis(
            pooled_agents, goal, distribution, domain_id=config.domain_id
        )

        await phase(SimulationPhase.COMPLETED)

        return SimulationResult(
            simulation_id=simulation_id,
            domain_id=config.domain_id,
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
            outcome_distribution=distribution,
        )
