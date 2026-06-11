import logging
from collections.abc import Awaitable, Callable
from typing import Any

from prds.agents.factory import create_agents
from prds.analysis.distribution import build_outcome_distribution
from prds.analysis.patterns import build_data_driven_counterfactuals, build_data_driven_synthesis
from prds.analysis.scoring import rank_agents
from prds.analysis.trajectory import (
    build_agent_decision_paths,
    build_champion_timeline,
    build_event_comparisons_from_agents,
)
from prds.config import get_settings
from prds.graph.dynamic import extract_domain_facts
from prds.graph.episodic import create_episodic_session
from prds.graph.graphrag import GraphRAGIndexer, compose_document
from prds.graph.neo4j_store import get_neo4j_store
from prds.graph.ontology_subject import prune_isolated_nodes
from prds.llm.client import LLMClient
from prds.models.domain import (
    AgentState,
    BackgroundReport,
    Event,
    SimulationInput,
    SimulationPhase,
    SimulationResult,
    WorldBackground,
    WorldState,
)
from prds.research import generate_background_report
from prds.simulation.loop import run_simulation_loop
from prds.world.event_planner import plan_events
from prds.world.initializer import initialize_world

logger = logging.getLogger(__name__)

PhaseCallback = Callable[[SimulationPhase, dict[str, Any]], Awaitable[None]]


class SimulationOrchestrator:
    """Runs all PRDS phases in sequence (event-driven simulation)."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def run(
        self,
        simulation_id: str,
        simulation_input: SimulationInput,
        *,
        on_phase: PhaseCallback | None = None,
        on_event: Callable[[int, int, int], Awaitable[None]] | None = None,
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
        except Exception as exc:
            logger.warning("Background research skipped due to error: %s", exc)
            report = None

        await phase(SimulationPhase.ONTOLOGY)
        indexer = GraphRAGIndexer(self.llm, use_graphrag=settings.prds_use_graphrag)
        ontology, kg_data, world_background = await indexer.index(
            simulation_id, current_state, goal, report=report
        )

        planned = await plan_events(
            self.llm,
            current_state,
            goal,
            config,
            world_background=world_background,
            ontology=ontology,
            report=report,
        )

        await phase(SimulationPhase.WORLD_INIT)
        world = initialize_world(
            ontology, current_state, goal, len(planned), world_background=world_background
        )

        await phase(SimulationPhase.AGENT_SPAWN, {"agent_count": config.agent_count})
        agents = create_agents(config.agent_count, initial_resources, seed=config.seed)

        domain_brief = (report.key_findings[:6] if report else []) or world_background.community_summaries[:3]
        world = world.model_copy(
            update={
                "domain_brief": list(domain_brief),
                "domain_facts": extract_domain_facts(kg_data),
            }
        )

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

        await phase(SimulationPhase.SIMULATION)

        async def event_callback(
            event_index: int, alive: int, total: int, current_agents: list[AgentState], current_world: WorldState
        ) -> None:
            if on_event:
                await on_event(event_index, alive, total)

        async def prepare_world(
            event_index: int, event: Event, current_agents: list[AgentState], current_world: WorldState
        ) -> WorldState:
            return await _refresh_world_kg(current_world)

        async def grow_graph(event_index: int, event: Event, current_agents: list[AgentState]) -> None:
            try:
                await graph_session.ingest_event(event_index, [event], current_agents)
            except Exception as exc:
                logger.warning("Graph event ingest failed (event %s): %s", event_index, exc)

        agents, final_world = await run_simulation_loop(
            self.llm,
            agents,
            world,
            goal,
            simulation_input,
            run_id=simulation_id,
            on_event_complete=event_callback,
            on_pause=on_pause,
            on_resume=on_resume,
            on_checkpoint=checkpoint,
            world_background=world_background,
            planned_events=planned,
            on_event_prepare=prepare_world,
            on_event_graph=grow_graph,
        )

        evolved = await graph_session.graph_data()
        if evolved is not None and evolved.nodes:
            kg_data = prune_isolated_nodes(evolved)
        if graph_session.backend == "graphiti":
            world_background.neo4j_persisted = bool(evolved and evolved.nodes)
        elif neo4j.available:
            try:
                persisted = await neo4j.save_simulation_graph(simulation_id, kg_data, world_background)
                world_background.neo4j_persisted = persisted
            except Exception as exc:
                logger.warning("Failed to persist grown graph to Neo4j: %s", exc)

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
                planned_events=planned,
            )
            pooled_agents.extend(rep_agents)

        await phase(SimulationPhase.SCORING)
        all_ranked = rank_agents(agents, goal, initial_resources, top_n=len(agents), domain_id=config.domain_id)
        top_agents = all_ranked[:20]
        rank_by_id = {score.agent_id: rank for rank, score in enumerate(all_ranked, start=1)}
        champion_id = top_agents[0].agent_id if top_agents else agents[0].agent_id
        champion = next(a for a in agents if a.agent_id == champion_id)

        await phase(SimulationPhase.TRAJECTORY)
        champion_timeline = build_champion_timeline(champion)
        agent_paths = build_agent_decision_paths(agents, top_agents, limit=20)
        event_comparisons = build_event_comparisons_from_agents(agents, rank_by_id=rank_by_id, planned_events=planned)

        distribution = build_outcome_distribution(
            pooled_agents,
            goal,
            domain_id=config.domain_id,
            replications=config.replications,
            param_overrides=config.param_overrides,
        )

        await phase(SimulationPhase.COUNTERFACTUAL)
        counterfactuals = build_data_driven_counterfactuals(
            pooled_agents, goal, domain_id=config.domain_id
        )

        await phase(SimulationPhase.SYNTHESIS)
        synthesis = build_data_driven_synthesis(
            pooled_agents, goal, distribution, domain_id=config.domain_id
        )

        await phase(SimulationPhase.COMPLETED)

        events_simulated = final_world.event_index

        return SimulationResult(
            simulation_id=simulation_id,
            domain_id=config.domain_id,
            agent_count=config.agent_count,
            events_simulated=events_simulated,
            ontology=ontology,
            knowledge_graph=kg_data,
            top_agents=top_agents,
            champion_agent_id=champion.agent_id,
            champion_strategy=champion.strategy_type,
            champion_timeline=champion_timeline,
            agent_paths=agent_paths,
            event_comparisons=event_comparisons,
            planned_events=planned,
            world_background=world_background,
            counterfactuals=counterfactuals,
            synthesis=synthesis,
            outcome_distribution=distribution,
        )
