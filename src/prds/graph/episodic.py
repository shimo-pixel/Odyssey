"""Unified episode-driven graph session."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from prds.config import Settings, get_settings
from prds.graph.agent_ontology import build_agents_registry_episode
from prds.graph.graphiti_store import GraphitiStore, get_graphiti_store
from prds.graph.incremental import IncrementalGraphBuilder
from prds.graph.ontology_subject import SUBJECT_NODE_ID
from prds.llm.client import LLMClient
from prds.models.domain import AgentState, Event, KnowledgeGraphData

logger = logging.getLogger(__name__)


def build_event_episode(
    event_index: int,
    events: list[Event],
    agents: list[AgentState],
    *,
    world_summary: str = "",
    max_reactions: int = 5,
) -> str:
    primary = events[0] if events else None
    label = primary.event_type if primary else "unknown"
    lines = [f"事件 #{event_index}（{label}）：外生冲击与各类主体的应对。"]
    lines.append(f"本体决策主体（{SUBJECT_NODE_ID}）观察此次事件并做出战略应对。")
    for event in events:
        desc = event.description or event.event_type
        direction = "利好" if event.impact >= 0 else "冲击"
        lines.append(
            f"事件「{event.event_type}」（{event.category.value}，对行业构成{direction}）：{desc}。"
        )

    seen: set[str] = set()
    reactions = 0
    for agent in agents:
        if agent.eliminated or not agent.timeline:
            continue
        if agent.agent_id in seen:
            continue
        entry = agent.timeline[-1]
        if entry.event_index != event_index or entry.action in ("", "hold"):
            continue
        seen.add(agent.agent_id)
        strat = agent.strategy_type.value
        reason = (entry.reasoning or entry.decision or "").strip()
        sentence = f"主体 {agent.agent_id}（{strat}）选择了「{entry.action}」"
        if reason:
            sentence += f"，理由是{reason[:140]}"
        lines.append(sentence + "。")
        reactions += 1
        if reactions >= max_reactions:
            break

    if world_summary:
        lines.append(f"行业背景：{world_summary[:500]}")
    return "\n".join(lines)


class EpisodicGraphSession:
    backend: str = "builtin"

    async def seed(self, document: str) -> None:
        raise NotImplementedError

    async def register_agents(
        self, agents: list[AgentState], *, goal_description: str = ""
    ) -> None:
        raise NotImplementedError

    async def ingest_event(
        self, event_index: int, events: list[Event], agents: list[AgentState]
    ) -> None:
        raise NotImplementedError

    async def graph_data(self) -> KnowledgeGraphData | None:
        raise NotImplementedError


class BuiltinEpisodicGraph(EpisodicGraphSession):
    backend = "builtin"

    def __init__(self, builder: IncrementalGraphBuilder) -> None:
        self._builder = builder

    async def seed(self, document: str) -> None:
        return None

    async def register_agents(
        self, agents: list[AgentState], *, goal_description: str = ""
    ) -> None:
        self._builder.register_agents(agents)

    async def ingest_event(
        self, event_index: int, events: list[Event], agents: list[AgentState]
    ) -> None:
        await self._builder.ingest_event(event_index, events, agents)

    async def graph_data(self) -> KnowledgeGraphData | None:
        return self._builder.snapshot()


class GraphitiEpisodicGraph(EpisodicGraphSession):
    backend = "graphiti"

    def __init__(
        self,
        store: GraphitiStore,
        group_id: str,
        *,
        world_summary: str = "",
    ) -> None:
        self._store = store
        self._group_id = group_id
        self._world_summary = world_summary
        self._goal_description = ""

    async def seed(self, document: str) -> None:
        await self._store.add_episode(
            self._group_id,
            document,
            name=f"seed_{self._group_id}",
            source_description="odyssey_seed_document",
        )

    async def register_agents(
        self, agents: list[AgentState], *, goal_description: str = ""
    ) -> None:
        self._goal_description = goal_description
        body = build_agents_registry_episode(agents, goal_description)
        await self._store.add_episode(
            self._group_id,
            body,
            name=f"agents_{self._group_id}",
            source_description="odyssey_agent_registry",
        )

    async def ingest_event(
        self, event_index: int, events: list[Event], agents: list[AgentState]
    ) -> None:
        has_action = any(
            not a.eliminated
            and a.timeline
            and a.timeline[-1].event_index == event_index
            and a.timeline[-1].action not in ("", "hold")
            for a in agents
        )
        if not events and not has_action:
            return
        body = build_event_episode(
            event_index, events, agents, world_summary=self._world_summary
        )
        await self._store.add_episode(
            self._group_id,
            body,
            name=f"event_{event_index}_{self._group_id}",
            source_description=f"odyssey_event_{event_index}",
            reference_time=datetime.now(timezone.utc),
        )

    async def graph_data(self) -> KnowledgeGraphData | None:
        data = await self._store.get_graph_data(self._group_id)
        if not data:
            return None
        nodes = []
        for n in data.get("nodes", []):
            if not n.get("uuid"):
                continue
            labels = n.get("labels") or []
            entity_type = _primary_label(labels)
            attrs = n.get("attributes") or {}
            node_id = attrs.get("agent_id") or n["uuid"]
            if entity_type == "entity" and attrs.get("agent_id"):
                entity_type = "agent"
            name = n.get("name") or node_id
            if name.startswith("agent_") and entity_type == "entity":
                entity_type = "agent"
                node_id = name
            nodes.append(
                {
                    "id": node_id,
                    "uuid": n["uuid"],
                    "entity_type": entity_type,
                    "name": name,
                    "summary": n.get("summary", ""),
                    **attrs,
                }
            )
        edges = [
            {
                "source": e["source_node_uuid"],
                "target": e["target_node_uuid"],
                "relation_type": e.get("name", "related"),
                "fact": e.get("fact", ""),
            }
            for e in data.get("edges", [])
            if e.get("source_node_uuid") and e.get("target_node_uuid")
        ]
        return KnowledgeGraphData(nodes=nodes, edges=edges)


def _primary_label(labels: list[str] | None) -> str:
    for label in labels or []:
        if label and label != "Entity":
            return label
    return "entity"


async def create_episodic_session(
    llm: LLMClient,
    simulation_id: str,
    base_graph: KnowledgeGraphData,
    *,
    world_summary: str = "",
    model: str | None = None,
    settings: Settings | None = None,
) -> EpisodicGraphSession:
    settings = settings or get_settings()
    backend = settings.resolved_graph_backend()

    if backend == "graphiti":
        store = get_graphiti_store()
        if store.available:
            session = GraphitiEpisodicGraph(store, simulation_id, world_summary=world_summary)
            try:
                await store.delete_graph(simulation_id)
            except Exception:
                pass
            return session
        logger.info("Graphiti requested but unavailable; using builtin graph backend.")

    builder = IncrementalGraphBuilder(
        llm,
        base_graph,
        model=model,
        world_summary=world_summary,
        enabled=settings.prds_dynamic_graph,
    )
    return BuiltinEpisodicGraph(builder)
