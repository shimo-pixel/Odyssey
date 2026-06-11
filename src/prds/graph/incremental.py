"""Grow the world knowledge graph one period at a time (MiroFish-style episodes).

Instead of dumping every planned event into the graph up front, this builder
ingests each simulation period as an "episode" (the events that actually fired
plus how representative agents reacted) and:

- adds the period's events as `event` nodes, chained to the previous period's
  events (a temporal backbone) and linked to the entities they influence;
- runs an LLM extraction over the episode narrative and merges any newly
  surfaced entities/relations into the graph, attaching them to existing nodes
  by name — this is the "hop by hop" growth;
- adds a small, representative set of agents as `agent` actor nodes wired to the
  events they responded to.

Every node and edge is tagged with ``first_seen_event`` so the frontend can
replay how the graph emerged over time.
"""

from __future__ import annotations

import logging
import re

from prds.graph.agent_ontology import agent_node, link_agent_event_actions
from prds.graph.graphrag import CHUNK_EXTRACT_PROMPT, _slug_id
from prds.graph.ontology_subject import (
    SUBJECT_NODE_ID,
    link_subject_event_actions,
    prune_isolated_nodes,
)
from prds.llm.client import LLMClient
from prds.models.domain import AgentState, Event, EventCategory, KnowledgeGraphData
from prds.ontology.builder import _parse_json_response

logger = logging.getLogger(__name__)

_ENTITY_TYPES = {
    "organization",
    "person",
    "product",
    "capital",
    "market",
    "technology",
    "time",
    "event",
    "agent",
    "risk",
    "ontology",
    "outcome",
}

# Which entity types an event of a given category most plausibly influences.
_CATEGORY_TARGETS: dict[EventCategory, tuple[str, ...]] = {
    EventCategory.MACRO: ("market", "technology", "time", "capital"),
    EventCategory.MARKET: ("market", "product", "organization"),
    EventCategory.ORG: ("person", "organization"),
    EventCategory.RESOURCE: ("capital", "organization", "product"),
}


def _norm(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


class IncrementalGraphBuilder:
    """Stateful, period-by-period knowledge-graph grower."""

    def __init__(
        self,
        llm: LLMClient,
        base: KnowledgeGraphData,
        *,
        model: str | None = None,
        world_summary: str = "",
        enabled: bool = True,
        max_targets: int = 2,
    ) -> None:
        self.llm = llm
        self.model = model
        self.world_summary = world_summary or ""
        self.enabled = enabled
        self.max_targets = max_targets

        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._edge_keys: set[tuple[str, str, str]] = set()
        self._name_to_id: dict[str, str] = {}
        self._counter = 0
        self._prev_event_ids: list[str] = []

        for raw in base.nodes:
            node = dict(raw)
            nid = node.get("id")
            if not nid:
                continue
            node.setdefault("first_seen_event", 0)
            self._nodes[nid] = node
            nm = _norm(node.get("name") or nid)
            if nm:
                self._name_to_id.setdefault(nm, nid)
        for raw in base.edges:
            self._add_edge(
                raw.get("source"),
                raw.get("target"),
                raw.get("relation_type", "related_to"),
                event_index=0,
                description=raw.get("description", ""),
            )

    # -- low level helpers -------------------------------------------------

    def _add_edge(
        self,
        source: str | None,
        target: str | None,
        relation_type: str,
        *,
        event_index: int,
        description: str = "",
    ) -> None:
        if not source or not target or source == target:
            return
        if source not in self._nodes or target not in self._nodes:
            return
        key = (source, target, relation_type)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        edge = {
            "source": source,
            "target": target,
            "relation_type": relation_type or "related_to",
            "first_seen_event": event_index,
        }
        if description:
            edge["description"] = description
        self._edges.append(edge)

    def _ensure_entity(
        self, name: str, entity_type: str, event_index: int, description: str = ""
    ) -> str | None:
        nm = _norm(name)
        if not nm:
            return None
        if nm in self._name_to_id:
            existing = self._nodes.get(self._name_to_id[nm])
            if existing and description and not existing.get("description"):
                existing["description"] = description
            return self._name_to_id[nm]
        self._counter += 1
        eid = _slug_id(name, 100_000 + self._counter)
        node = {
            "id": eid,
            "entity_type": entity_type if entity_type in _ENTITY_TYPES else "entity",
            "name": name.strip(),
            "first_seen_event": event_index,
        }
        if description:
            node["description"] = description
        self._nodes[eid] = node
        self._name_to_id[nm] = eid
        return eid

    def _pick_targets(self, category: EventCategory) -> list[str]:
        wanted = _CATEGORY_TARGETS.get(category, ())
        matches = [
            nid
            for nid, n in self._nodes.items()
            if n.get("entity_type") in wanted
        ]
        if not matches:
            matches = [
                nid
                for nid, n in self._nodes.items()
                if n.get("entity_type") not in {"event", "agent"}
            ]
        return matches[: self.max_targets]

    # -- public API --------------------------------------------------------

    def register_agents(self, agents: list[AgentState]) -> None:
        """Register every spawned agent as a stable ontology node at period 0."""
        anchor = next(
            (nid for nid, n in self._nodes.items() if n.get("entity_type") == "organization"),
            None,
        )
        market = next(
            (nid for nid, n in self._nodes.items() if n.get("entity_type") == "market"),
            None,
        )
        for agent in agents:
            if agent.agent_id in self._nodes:
                continue
            self._nodes[agent.agent_id] = agent_node(agent, event_index=0)
            if SUBJECT_NODE_ID in self._nodes:
                self._add_edge(agent.agent_id, SUBJECT_NODE_ID, "delegates_to", event_index=0)
            if anchor:
                self._add_edge(agent.agent_id, anchor, "operates_in", event_index=0)
            if market:
                self._add_edge(agent.agent_id, market, "competes", event_index=0)

    async def ingest_event(
        self, event_index: int, events: list[Event], agents: list[AgentState]
    ) -> None:
        """Fold one simulation period into the evolving graph."""
        event_ids: list[str] = []
        for event in events:
            eid = event.event_id
            if eid not in self._nodes:
                self._nodes[eid] = {
                    "id": eid,
                    "entity_type": "event",
                    "name": event.event_type,
                    "category": event.category.value,
                    "impact": event.impact,
                    "severity": event.severity,
                    "probability": event.probability,
                    "event_index": event_index,
                    "first_seen_event": event_index,
                    "description": event.description,
                }
            event_ids.append(eid)
            if SUBJECT_NODE_ID in self._nodes:
                self._add_edge(SUBJECT_NODE_ID, eid, "aware_of", event_index=event_index)
            for target in self._pick_targets(event.category):
                self._add_edge(eid, target, "influences", event_index=event_index)
            for prev in self._prev_event_ids:
                self._add_edge(prev, eid, "precedes", event_index=event_index)

        has_reactions = bool(self._representative_reactions(agents))
        if self.enabled and (events or has_reactions):
            try:
                await self._extract_episode(event_index, events, agents, event_ids)
            except Exception as exc:  # never let graph growth break a simulation
                logger.warning("Incremental episode extraction failed (event %s): %s", event_index, exc)

        snap = self.snapshot()
        linked = link_agent_event_actions(snap, agents, events, event_index=event_index)
        for edge in linked.edges:
            self._add_edge(
                edge.get("source"),
                edge.get("target"),
                edge.get("relation_type", "responds_to"),
                event_index=event_index,
                description=edge.get("action", ""),
            )

        subject_snap = link_subject_event_actions(
            self.snapshot(), agents, events, event_index=event_index
        )
        for node in subject_snap.nodes:
            nid = node.get("id")
            if nid and nid not in self._nodes:
                self._nodes[nid] = node
                nm = _norm(node.get("name") or nid)
                if nm:
                    self._name_to_id.setdefault(nm, nid)
        for edge in subject_snap.edges:
            self._add_edge(
                edge.get("source"),
                edge.get("target"),
                edge.get("relation_type", "related_to"),
                event_index=event_index,
                description=edge.get("description", "") or edge.get("action", ""),
            )

        pruned = prune_isolated_nodes(self.snapshot())
        self._nodes = {n["id"]: n for n in pruned.nodes if n.get("id")}
        self._edges = list(pruned.edges)
        self._edge_keys = {
            (e.get("source"), e.get("target"), e.get("relation_type", ""))
            for e in self._edges
            if e.get("source") and e.get("target")
        }
        self._name_to_id = {}
        for nid, node in self._nodes.items():
            nm = _norm(node.get("name") or nid)
            if nm:
                self._name_to_id.setdefault(nm, nid)

        if event_ids:
            self._prev_event_ids = event_ids

    def snapshot(self) -> KnowledgeGraphData:
        return KnowledgeGraphData(
            nodes=list(self._nodes.values()),
            edges=list(self._edges),
        )

    def domain_facts(self, limit: int = 12) -> list[str]:
        """Compact NL facts (excluding agent noise) for agent decision context."""
        facts: list[str] = []
        for edge in self._edges:
            src = self._nodes.get(edge.get("source"))
            tgt = self._nodes.get(edge.get("target"))
            if not src or not tgt:
                continue
            if src.get("entity_type") == "agent" or tgt.get("entity_type") == "agent":
                continue
            rel = edge.get("relation_type", "influences")
            facts.append(
                f"{src.get('name', src.get('id'))} —{rel}→ {tgt.get('name', tgt.get('id'))}"
            )
            if len(facts) >= limit:
                break
        return facts

    # -- internals ---------------------------------------------------------

    def _build_episode_text(
        self, event_index: int, events: list[Event], agents: list[AgentState]
    ) -> str:
        lines = [f"事件 #{event_index}世界动态："]
        for event in events:
            lines.append(
                f"- 事件「{event.event_type}」（{event.category.value}）：{event.description}"
                f"（影响强度 {event.impact:+.2f}）"
            )
        reactions = self._representative_reactions(agents)
        if reactions:
            lines.append("代表性主体的反应：")
            lines.extend(reactions)
        if self.world_summary:
            lines.append(f"世界背景参考：{self.world_summary[:600]}")
        return "\n".join(lines)

    def _representative_reactions(self, agents: list[AgentState], limit: int = 4) -> list[str]:
        out: list[str] = []
        seen_strategies: set[str] = set()
        for agent in agents:
            if agent.eliminated or not agent.timeline:
                continue
            strat = agent.strategy_type.value
            if strat in seen_strategies:
                continue
            entry = agent.timeline[-1]
            if entry.action in ("", "hold"):
                continue
            seen_strategies.add(strat)
            reason = (entry.reasoning or entry.decision or "").strip()
            text = f"- {strat} 型主体选择「{entry.action}」"
            if reason:
                text += f"：{reason[:120]}"
            out.append(text)
            if len(out) >= limit:
                break
        return out

    async def _extract_episode(
        self,
        event_index: int,
        events: list[Event],
        agents: list[AgentState],
        event_ids: list[str],
    ) -> None:
        episode = self._build_episode_text(event_index, events, agents)
        response = await self.llm.complete(
            system=CHUNK_EXTRACT_PROMPT,
            user=episode,
            model=self.model or self.llm.analysis_model,
        )
        data = _parse_json_response(response)

        new_entity_ids: list[str] = []
        for raw in data.get("entities", []):
            eid = self._ensure_entity(
                raw.get("name", ""),
                raw.get("entity_type", "entity"),
                event_index,
                raw.get("description", ""),
            )
            if eid:
                new_entity_ids.append(eid)

        for raw in data.get("relationships", []):
            src = self._ensure_entity(raw.get("source", ""), "entity", event_index)
            tgt = self._ensure_entity(raw.get("target", ""), "entity", event_index)
            self._add_edge(
                src,
                tgt,
                raw.get("relation_type", "influences"),
                event_index=event_index,
                description=raw.get("description", ""),
            )

        # Tie the entities surfaced this period back to the events that caused them.
        for eid in event_ids:
            for ent in new_entity_ids[:3]:
                self._add_edge(eid, ent, "surfaces", event_index=event_index)

