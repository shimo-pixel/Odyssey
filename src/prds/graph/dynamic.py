"""Dynamically grow the world knowledge graph during a simulation (steps ③–⑤).

- Generated events are added as `event` nodes, linked to the domain entities they
  influence, so the graph reflects what is happening in the world over time.
- Spawned agents are added as `agent` nodes (ontology actors), so their reasoning
  is grounded in, and traceable through, the same graph.
- `extract_domain_facts` turns the graph into compact natural-language facts that
  are injected into each agent's decision context as background understanding.
"""

from prds.models.domain import AgentState, Event, EventCategory, KnowledgeGraphData

# Which entity types an event of a given category most plausibly influences.
_CATEGORY_TARGETS: dict[EventCategory, tuple[str, ...]] = {
    EventCategory.MACRO: ("market", "technology", "time", "capital"),
    EventCategory.MARKET: ("market", "product", "organization"),
    EventCategory.ORG: ("person", "organization"),
    EventCategory.RESOURCE: ("capital", "organization", "product"),
}

_MAX_AGENT_NODES = 30


def _node_index(kg_data: KnowledgeGraphData) -> dict[str, dict]:
    return {n.get("id"): n for n in kg_data.nodes if n.get("id")}


def _pick_targets(kg_data: KnowledgeGraphData, category: EventCategory, limit: int = 2) -> list[str]:
    wanted = _CATEGORY_TARGETS.get(category, ())
    matches = [n["id"] for n in kg_data.nodes if n.get("entity_type") in wanted and n.get("id")]
    if not matches:
        matches = [n["id"] for n in kg_data.nodes if n.get("id") and n.get("entity_type") != "event"]
    return matches[:limit]


def add_events_to_kg(
    kg_data: KnowledgeGraphData, calendar: dict[int, list[Event]]
) -> KnowledgeGraphData:
    """Append event nodes (and influence edges) for every planned event."""
    nodes = list(kg_data.nodes)
    edges = list(kg_data.edges)
    existing = {n.get("id") for n in nodes}

    for period in sorted(calendar):
        for event in calendar[period]:
            if event.event_id in existing:
                continue
            nodes.append(
                {
                    "id": event.event_id,
                    "entity_type": "event",
                    "name": event.event_type,
                    "category": event.category.value,
                    "impact": event.impact,
                    "probability": event.probability,
                    "severity": event.severity,
                    "period": period,
                    "description": event.description,
                }
            )
            existing.add(event.event_id)
            for target in _pick_targets(kg_data, event.category):
                edges.append(
                    {
                        "source": event.event_id,
                        "target": target,
                        "relation_type": "influences",
                    }
                )
    return KnowledgeGraphData(nodes=nodes, edges=edges)


def add_agents_to_kg(kg_data: KnowledgeGraphData, agents: list[AgentState]) -> KnowledgeGraphData:
    """Append a representative set of agent nodes as ontology actors."""
    nodes = list(kg_data.nodes)
    edges = list(kg_data.edges)
    existing = {n.get("id") for n in nodes}

    anchor = next(
        (n["id"] for n in kg_data.nodes if n.get("entity_type") == "organization" and n.get("id")),
        next((n["id"] for n in kg_data.nodes if n.get("id") and n.get("entity_type") != "event"), None),
    )

    for agent in agents[:_MAX_AGENT_NODES]:
        if agent.agent_id in existing:
            continue
        nodes.append(
            {
                "id": agent.agent_id,
                "entity_type": "agent",
                "name": agent.strategy_type.value,
                "strategy": agent.strategy_type.value,
            }
        )
        existing.add(agent.agent_id)
        if anchor and anchor != agent.agent_id:
            edges.append(
                {"source": agent.agent_id, "target": anchor, "relation_type": "competes"}
            )
    return KnowledgeGraphData(nodes=nodes, edges=edges)


def extract_domain_facts(kg_data: KnowledgeGraphData, limit: int = 12) -> list[str]:
    """Turn graph relationships into compact NL facts for agent context."""
    index = _node_index(kg_data)
    facts: list[str] = []
    for edge in kg_data.edges:
        src = index.get(edge.get("source"))
        tgt = index.get(edge.get("target"))
        if not src or not tgt:
            continue
        # Skip per-agent edges (noise for reasoning); keep entity/event relations.
        if src.get("entity_type") == "agent":
            continue
        rel = edge.get("relation_type", "influences")
        facts.append(f"{src.get('name', src.get('id'))} —{rel}→ {tgt.get('name', tgt.get('id'))}")
        if len(facts) >= limit:
            break
    return facts
