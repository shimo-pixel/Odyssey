"""Agent nodes as first-class ontology actors + per-agent subgraph retrieval.

Every spawned agent is registered once (stable ``agent_id`` node) and linked to
the anchor organization.  After each period, ``responds_to`` edges connect agents
to the events they reacted to.  At decision time, ``extract_agent_subgraph``
walks 1–2 hops from the agent node and returns compact facts for the LLM.
"""

from __future__ import annotations

from collections import deque

from prds.models.domain import AgentState, Event, KnowledgeGraphData

# Edge types that are most useful when explaining an agent's situation.
_AGENT_CONTEXT_RELATIONS = frozenset(
    {
        "responds_to",
        "competes",
        "operates_in",
        "influences",
        "depends_on",
        "surfaces",
        "pursues",
        "related_to",
    }
)

_RELATION_LABELS: dict[str, str] = {
    "responds_to": "应对",
    "competes": "竞争",
    "operates_in": "运行于",
    "influences": "影响",
    "depends_on": "依赖",
    "surfaces": "揭示",
    "pursues": "追求",
    "precedes": "之后发生",
    "related_to": "关联",
}


def agent_node(agent: AgentState, *, period: int = 0) -> dict:
    """Stable ontology node payload for one agent."""
    attrs = agent.attributes
    return {
        "id": agent.agent_id,
        "entity_type": "agent",
        "name": agent.strategy_type.value,
        "strategy": agent.strategy_type.value,
        "risk_preference": round(attrs.risk_preference, 2),
        "execution_power": round(attrs.execution_power, 2),
        "first_seen_period": period,
        "description": (
            f"{agent.strategy_type.value} 型决策主体，"
            f"风险偏好 {attrs.risk_preference:.1f}，执行力 {attrs.execution_power:.1f}"
        ),
    }


def build_agents_registry_episode(agents: list[AgentState], goal_description: str = "") -> str:
    """Natural-language episode that seeds all agents into Graphiti."""
    lines = ["本推演中的决策主体（智能体）注册："]
    if goal_description:
        lines.append(f"共同目标：{goal_description[:300]}")
    for agent in agents:
        attrs = agent.attributes
        lines.append(
            f"- 主体 {agent.agent_id}（{agent.strategy_type.value}）："
            f"风险偏好 {attrs.risk_preference:.1f}，"
            f"执行力 {attrs.execution_power:.1f}，"
            f"当前现金 {agent.resources.cash:.0f}，团队 {agent.resources.team_size} 人"
        )
    lines.append("以上主体将在该行业环境中独立决策并相互竞争。")
    return "\n".join(lines)


def register_agents_in_kg(
    kg: KnowledgeGraphData,
    agents: list[AgentState],
    *,
    anchor_org_id: str | None = None,
) -> KnowledgeGraphData:
    """Register every agent as an ontology node (idempotent)."""
    nodes = list(kg.nodes)
    edges = list(kg.edges)
    existing = {n.get("id") for n in nodes if n.get("id")}
    edge_keys = {
        (e.get("source"), e.get("target"), e.get("relation_type", ""))
        for e in edges
        if e.get("source") and e.get("target")
    }

    if anchor_org_id is None:
        anchor_org_id = next(
            (n["id"] for n in nodes if n.get("entity_type") == "organization" and n.get("id")),
            None,
        )
    market_id = next(
        (n["id"] for n in nodes if n.get("entity_type") == "market" and n.get("id")),
        None,
    )

    for agent in agents:
        if agent.agent_id in existing:
            continue
        nodes.append(agent_node(agent, period=0))
        existing.add(agent.agent_id)
        if anchor_org_id and anchor_org_id != agent.agent_id:
            key = (agent.agent_id, anchor_org_id, "operates_in")
            if key not in edge_keys:
                edges.append(
                    {
                        "source": agent.agent_id,
                        "target": anchor_org_id,
                        "relation_type": "operates_in",
                        "first_seen_period": 0,
                    }
                )
                edge_keys.add(key)
        if market_id and market_id != agent.agent_id:
            key = (agent.agent_id, market_id, "competes")
            if key not in edge_keys:
                edges.append(
                    {
                        "source": agent.agent_id,
                        "target": market_id,
                        "relation_type": "competes",
                        "first_seen_period": 0,
                    }
                )
                edge_keys.add(key)

    return KnowledgeGraphData(nodes=nodes, edges=edges)


def link_agent_period_actions(
    kg: KnowledgeGraphData,
    agents: list[AgentState],
    events: list[Event],
    *,
    period: int,
) -> KnowledgeGraphData:
    """Wire ``responds_to`` edges from agents that acted this period to its events."""
    nodes = list(kg.nodes)
    edges = list(kg.edges)
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    edge_keys = {
        (e.get("source"), e.get("target"), e.get("relation_type", ""))
        for e in edges
        if e.get("source") and e.get("target")
    }
    event_ids = [e.event_id for e in events if e.event_id in node_ids]

    for agent in agents:
        if agent.agent_id not in node_ids or not agent.timeline:
            continue
        entry = agent.timeline[-1]
        if entry.period != period or entry.action in ("", "hold"):
            continue
        for eid in event_ids:
            key = (agent.agent_id, eid, "responds_to")
            if key in edge_keys:
                continue
            edges.append(
                {
                    "source": agent.agent_id,
                    "target": eid,
                    "relation_type": "responds_to",
                    "first_seen_period": period,
                    "action": entry.action,
                }
            )
            edge_keys.add(key)

    return KnowledgeGraphData(nodes=nodes, edges=edges)


def _node_index(kg: KnowledgeGraphData) -> dict[str, dict]:
    return {n["id"]: n for n in kg.nodes if n.get("id")}


def _rel_label(rel: str) -> str:
    return _RELATION_LABELS.get(rel, rel)


def resolve_agent_node_id(kg: KnowledgeGraphData, agent: AgentState) -> str | None:
    """Find the graph node id for an agent (builtin uses agent_id; Graphiti may use uuid)."""
    index = _node_index(kg)
    if agent.agent_id in index:
        return agent.agent_id
    strat = agent.strategy_type.value
    for node in kg.nodes:
        nid = node.get("id") or node.get("uuid")
        if not nid:
            continue
        if node.get("entity_type") == "agent" and node.get("name") == strat:
            return nid
        if node.get("name") == strat and "agent" in (node.get("entity_type") or "").lower():
            return nid
    return None


def extract_agent_subgraph(
    kg: KnowledgeGraphData,
    agent_id: str,
    *,
    max_hops: int = 2,
    limit: int = 10,
) -> list[str]:
    """BFS subgraph around *agent_id*, returned as compact NL facts for the LLM."""
    if not kg.nodes or not agent_id:
        return []

    index = _node_index(kg)
    if agent_id not in index:
        return []

    # Build undirected adjacency for traversal, but keep directed edge metadata.
    adj: dict[str, list[dict]] = {}
    for edge in kg.edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt or src not in index or tgt not in index:
            continue
        adj.setdefault(src, []).append(edge)
        adj.setdefault(tgt, []).append({**edge, "_reversed": True})

    visited: set[str] = {agent_id}
    queue: deque[tuple[str, int]] = deque([(agent_id, 0)])
    collected_edges: list[dict] = []

    while queue and len(collected_edges) < limit * 3:
        nid, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in adj.get(nid, []):
            reversed_edge = edge.get("_reversed")
            src = edge["target"] if reversed_edge else edge["source"]
            tgt = edge["source"] if reversed_edge else edge["target"]
            rel = edge.get("relation_type", "related_to")
            if rel not in _AGENT_CONTEXT_RELATIONS and rel != "precedes":
                continue
            collected_edges.append({"source": src, "target": tgt, "relation_type": rel, **edge})
            for neighbor in (src, tgt):
                if neighbor not in visited and depth + 1 < max_hops:
                    visited.add(neighbor)
                    queue.append((neighbor, depth + 1))

    # Prioritise edges that touch the requesting agent, then events, then org/market.
    def _priority(e: dict) -> tuple[int, int]:
        touches_agent = agent_id in (e["source"], e["target"])
        src = index.get(e["source"], {})
        tgt = index.get(e["target"], {})
        has_event = src.get("entity_type") == "event" or tgt.get("entity_type") == "event"
        return (0 if touches_agent else 1, 0 if has_event else 1)

    collected_edges.sort(key=_priority)

    facts: list[str] = []
    seen: set[str] = set()
    agent_node_data = index[agent_id]
    agent_intro = (
        f"【本主体】{agent_node_data.get('name', agent_id)}"
        f"（{agent_node_data.get('strategy', '')}）"
    )
    if agent_node_data.get("description"):
        agent_intro += f"：{agent_node_data['description']}"
    facts.append(agent_intro)
    seen.add(agent_intro)

    for edge in collected_edges:
        if len(facts) >= limit + 1:  # +1 for intro line
            break
        src = index.get(edge["source"], {})
        tgt = index.get(edge["target"], {})
        rel = _rel_label(edge.get("relation_type", "related_to"))
        line = f"{src.get('name', edge['source'])} —{rel}→ {tgt.get('name', edge['target'])}"
        if edge.get("action"):
            line += f"（行动：{edge['action']}）"
        if line in seen:
            continue
        seen.add(line)
        facts.append(line)

    return facts
