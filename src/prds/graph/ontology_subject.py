"""Ontology subject as the central node in the world knowledge graph.

The user's organization / decision-maker is registered as an ``ontology`` node
at graph seed time.  Each period, the subject's representative actions and their
outcomes are written into the graph alongside exogenous events.  Isolated nodes
(with no edges) are pruned as structurally unimportant.
"""

from __future__ import annotations

import uuid
from collections import deque

from prds.models.domain import (
    AgentState,
    BackgroundReport,
    CurrentState,
    Event,
    KnowledgeGraphData,
    OntologyGraph,
    TargetGoal,
)

SUBJECT_NODE_ID = "ontology_subject"

# Node types that must never be removed by pruning even if temporarily isolated.
_PROTECTED_TYPES = frozenset({"ontology", "event", "agent"})

_RELATION_LABELS: dict[str, str] = {
    "operates_in": "运行于",
    "pursues": "追求",
    "responds_to": "应对",
    "undertakes": "采取",
    "results_in": "产生结果",
    "influences": "影响",
    "aware_of": "关注",
    "delegates_to": "委托",
    "related_to": "关联",
}


def subject_display_name(current_state: CurrentState, goal: TargetGoal) -> str:
    org = current_state.organization or {}
    name = org.get("name") or org.get("title")
    if name:
        return str(name).strip()
    bg = (current_state.background or "").strip()
    if bg:
        first = bg.split("\n", 1)[0].strip()
        if len(first) > 40:
            return first[:37] + "…"
        return first or "决策主体"
    return goal.description[:40] if goal.description else "决策主体"


def inject_ontology_subject(
    kg: KnowledgeGraphData,
    *,
    current_state: CurrentState,
    goal: TargetGoal,
    ontology: OntologyGraph | None = None,
    report: BackgroundReport | None = None,
) -> KnowledgeGraphData:
    """Ensure the ontology subject node exists and is wired into the seed graph."""
    nodes = list(kg.nodes)
    edges = list(kg.edges)
    index = {n["id"]: n for n in nodes if n.get("id")}

    if SUBJECT_NODE_ID not in index:
        desc_parts = [f"目标：{goal.description[:200]}"]
        if report and report.key_findings:
            desc_parts.append(f"报告要点：{'; '.join(report.key_findings[:3])}")
        nodes.append(
            {
                "id": SUBJECT_NODE_ID,
                "entity_type": "ontology",
                "name": subject_display_name(current_state, goal),
                "first_seen_event": 0,
                "is_central": True,
                "description": " ".join(desc_parts),
                "goal": goal.description[:300],
            }
        )
        index[SUBJECT_NODE_ID] = nodes[-1]

    edge_keys = {
        (e.get("source"), e.get("target"), e.get("relation_type", ""))
        for e in edges
        if e.get("source") and e.get("target")
    }

    def _link(src: str, tgt: str, rel: str, *, description: str = "") -> None:
        if src not in index or tgt not in index or src == tgt:
            return
        key = (src, tgt, rel)
        if key in edge_keys:
            return
        edge: dict = {
            "source": src,
            "target": tgt,
            "relation_type": rel,
            "first_seen_event": 0,
        }
        if description:
            edge["description"] = description
        edges.append(edge)
        edge_keys.add(key)

    org_id = next(
        (n["id"] for n in nodes if n.get("entity_type") == "organization" and n.get("id")),
        None,
    )
    market_id = next(
        (n["id"] for n in nodes if n.get("entity_type") == "market" and n.get("id")),
        None,
    )
    if org_id:
        _link(SUBJECT_NODE_ID, org_id, "operates_in")
    if market_id:
        _link(SUBJECT_NODE_ID, market_id, "pursues", description=goal.description[:120])

    if ontology:
        for entity in ontology.entities[:8]:
            eid = entity.id
            if eid in index and eid != SUBJECT_NODE_ID:
                _link(SUBJECT_NODE_ID, eid, "aware_of")
        for relation in ontology.relations[:12]:
            if relation.source_id in index and relation.target_id in index:
                key = (relation.source_id, relation.target_id, relation.relation_type)
                if key not in edge_keys:
                    edges.append(
                        {
                            "source": relation.source_id,
                            "target": relation.target_id,
                            "relation_type": relation.relation_type,
                            "first_seen_event": 0,
                        }
                    )
                    edge_keys.add(key)

    return KnowledgeGraphData(nodes=nodes, edges=edges)


def prune_isolated_nodes(kg: KnowledgeGraphData) -> KnowledgeGraphData:
    """Remove nodes with zero incident edges (structurally unimportant)."""
    if not kg.nodes:
        return kg

    connected: set[str] = set()
    for edge in kg.edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src:
            connected.add(src)
        if tgt:
            connected.add(tgt)

    kept_nodes = []
    for node in kg.nodes:
        nid = node.get("id")
        if not nid:
            continue
        etype = node.get("entity_type", "")
        if nid in connected or etype in _PROTECTED_TYPES or node.get("is_central"):
            kept_nodes.append(node)

    kept_ids = {n["id"] for n in kept_nodes if n.get("id")}
    kept_edges = [
        e
        for e in kg.edges
        if e.get("source") in kept_ids and e.get("target") in kept_ids
    ]
    return KnowledgeGraphData(nodes=kept_nodes, edges=kept_edges)


def extract_subject_subgraph(
    kg: KnowledgeGraphData,
    *,
    max_hops: int = 2,
    limit: int = 12,
) -> list[str]:
    """BFS around the ontology subject; compact NL facts for LLM context."""
    if not kg.nodes:
        return []

    index = {n["id"]: n for n in kg.nodes if n.get("id")}
    subject_id = SUBJECT_NODE_ID if SUBJECT_NODE_ID in index else None
    if not subject_id:
        for node in kg.nodes:
            if node.get("entity_type") == "ontology" and node.get("is_central"):
                subject_id = node["id"]
                break
    if not subject_id:
        return []

    adj: dict[str, list[dict]] = {}
    for edge in kg.edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt or src not in index or tgt not in index:
            continue
        adj.setdefault(src, []).append(edge)
        adj.setdefault(tgt, []).append({**edge, "_reversed": True})

    visited: set[str] = {subject_id}
    queue: deque[tuple[str, int]] = deque([(subject_id, 0)])
    collected: list[dict] = []

    while queue and len(collected) < limit * 3:
        nid, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in adj.get(nid, []):
            reversed_edge = edge.get("_reversed")
            src = edge["target"] if reversed_edge else edge["source"]
            tgt = edge["source"] if reversed_edge else edge["target"]
            collected.append({"source": src, "target": tgt, **edge})
            for neighbor in (src, tgt):
                if neighbor not in visited and depth + 1 < max_hops:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

    subject = index[subject_id]
    facts = [
        f"【本体主体】{subject.get('name', subject_id)}"
        + (f"：{subject['description'][:120]}" if subject.get("description") else "")
    ]
    seen: set[str] = set(facts[0])

    def _priority(e: dict) -> tuple[int, int]:
        touches = subject_id in (e["source"], e["target"])
        src = index.get(e["source"], {})
        tgt = index.get(e["target"], {})
        is_event = src.get("entity_type") == "event" or tgt.get("entity_type") == "event"
        return (0 if touches else 1, 0 if is_event else 1)

    collected.sort(key=_priority)
    for edge in collected:
        if len(facts) >= limit + 1:
            break
        src = index.get(edge["source"], {})
        tgt = index.get(edge["target"], {})
        rel = _RELATION_LABELS.get(edge.get("relation_type", ""), edge.get("relation_type", "关联"))
        line = f"{src.get('name', edge['source'])} —{rel}→ {tgt.get('name', edge['target'])}"
        if edge.get("action"):
            line += f"（行动：{edge['action']}）"
        if edge.get("description"):
            line += f"（{edge['description'][:80]}）"
        if line in seen:
            continue
        seen.add(line)
        facts.append(line)
    return facts


def _representative_action(agents: list[AgentState], event_index: int) -> tuple[str, str, str] | None:
    """Return (action, reasoning, strategy) for the first non-hold agent this period."""
    for agent in agents:
        if agent.eliminated or not agent.timeline:
            continue
        entry = agent.timeline[-1]
        if entry.event_index != event_index or entry.action in ("", "hold"):
            continue
        reason = (entry.reasoning or entry.decision or "").strip()
        return entry.action, reason, agent.strategy_type.value
    return None


def link_subject_event_actions(
    kg: KnowledgeGraphData,
    agents: list[AgentState],
    events: list[Event],
    *,
    event_index: int,
) -> KnowledgeGraphData:
    """Wire subject node to events it responds to and outcomes from its actions."""
    if SUBJECT_NODE_ID not in {n.get("id") for n in kg.nodes}:
        return kg

    nodes = list(kg.nodes)
    edges = list(kg.edges)
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    edge_keys = {
        (e.get("source"), e.get("target"), e.get("relation_type", ""))
        for e in edges
        if e.get("source") and e.get("target")
    }

    def _add(src: str, tgt: str, rel: str, **extra: object) -> None:
        key = (src, tgt, rel)
        if key in edge_keys or src not in node_ids or tgt not in node_ids:
            return
        edge = {"source": src, "target": tgt, "relation_type": rel, "first_seen_event": event_index, **extra}
        edges.append(edge)
        edge_keys.add(key)

    event_ids = [e.event_id for e in events if e.event_id in node_ids]
    for eid in event_ids:
        _add(SUBJECT_NODE_ID, eid, "responds_to", event_index_tag=event_index)

    action_info = _representative_action(agents, event_index)
    if action_info:
        action, reason, strategy = action_info
        outcome_id = f"outcome_{event_index}_{uuid.uuid4().hex[:6]}"
        outcome_desc = f"事件 #{event_index}采取「{action}」"
        if reason:
            outcome_desc += f"：{reason[:160]}"
        nodes.append(
            {
                "id": outcome_id,
                "entity_type": "outcome",
                "name": action,
                "strategy": strategy,
                "event_index": event_index,
                "first_seen_event": event_index,
                "description": outcome_desc,
            }
        )
        node_ids.add(outcome_id)
        _add(SUBJECT_NODE_ID, outcome_id, "results_in", action=action, description=reason[:200])
        for eid in event_ids:
            _add(outcome_id, eid, "influences", description=f"应对事件后的行动结果")

    return KnowledgeGraphData(nodes=nodes, edges=edges)
