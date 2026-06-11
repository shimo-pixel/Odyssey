"""Tests for stable agent ontology nodes and per-agent subgraph retrieval."""

from prds.graph.agent_ontology import (
    extract_agent_subgraph,
    link_agent_event_actions,
    register_agents_in_kg,
    resolve_agent_node_id,
)
from prds.models.domain import (
    AgentAttributes,
    AgentState,
    Event,
    EventCategory,
    KnowledgeGraphData,
    DecisionLogEntry,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
    WorldState,
)
from prds.simulation.realism import build_decision_context


def _base_graph() -> KnowledgeGraphData:
    return KnowledgeGraphData(
        nodes=[
            {"id": "org1", "entity_type": "organization", "name": "Acme"},
            {"id": "mkt1", "entity_type": "market", "name": "Market"},
        ],
        edges=[{"source": "org1", "target": "mkt1", "relation_type": "competes"}],
    )


def _agent(agent_id: str = "a1") -> AgentState:
    return AgentState(
        agent_id=agent_id,
        strategy_type=StrategyType.AGGRESSIVE,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=100),
    )


def _event(period: int = 1) -> Event:
    return Event(
        event_id=f"ev_{period}",
        event_type="competitor_entry",
        category=EventCategory.MARKET,
        impact=-0.2,
        probability=0.8,
        severity=0.5,
        description="新竞争对手进入",
    )


def test_register_agents_creates_stable_nodes_and_links():
    kg = register_agents_in_kg(_base_graph(), [_agent("a1"), _agent("a2")])
    agent_nodes = [n for n in kg.nodes if n.get("entity_type") == "agent"]
    assert len(agent_nodes) == 2
    assert all(n["first_seen_event"] == 0 for n in agent_nodes)
    assert any(
        e["source"] == "a1" and e["target"] == "org1" and e["relation_type"] == "operates_in"
        for e in kg.edges
    )
    assert any(
        e["source"] == "a1" and e["target"] == "mkt1" and e["relation_type"] == "competes"
        for e in kg.edges
    )


def test_register_agents_is_idempotent():
    kg1 = register_agents_in_kg(_base_graph(), [_agent()])
    kg2 = register_agents_in_kg(kg1, [_agent()])
    assert len([n for n in kg2.nodes if n.get("entity_type") == "agent"]) == 1


def test_link_agent_event_actions_wires_responds_to():
    kg = register_agents_in_kg(_base_graph(), [_agent()])
    kg = KnowledgeGraphData(
        nodes=kg.nodes
        + [
            {
                "id": "ev_1",
                "entity_type": "event",
                "name": "competitor_entry",
                "first_seen_event": 1,
            }
        ],
        edges=kg.edges,
    )
    agent = _agent()
    agent.timeline.append(
        DecisionLogEntry(
            event_index=1,
            world_state=WorldState(),
            action="product_dev",
            reasoning="加速迭代",
        )
    )
    linked = link_agent_event_actions(kg, [agent], [_event(1)], event_index=1)
    assert any(
        e["source"] == "a1"
        and e["target"] == "ev_1"
        and e["relation_type"] == "responds_to"
        and e.get("action") == "product_dev"
        for e in linked.edges
    )


def test_extract_agent_subgraph_returns_nl_facts():
    kg = register_agents_in_kg(_base_graph(), [_agent()])
    kg = KnowledgeGraphData(
        nodes=kg.nodes
        + [
            {
                "id": "ev_1",
                "entity_type": "event",
                "name": "competitor_entry",
                "first_seen_event": 1,
            }
        ],
        edges=kg.edges
        + [
            {
                "source": "a1",
                "target": "ev_1",
                "relation_type": "responds_to",
                "action": "product_dev",
            }
        ],
    )
    facts = extract_agent_subgraph(kg, "a1")
    assert facts
    assert any("本主体" in f for f in facts)
    assert any("competitor_entry" in f or "应对" in f for f in facts)


def test_resolve_agent_node_id_by_agent_id():
    kg = register_agents_in_kg(_base_graph(), [_agent()])
    assert resolve_agent_node_id(kg, _agent()) == "a1"


def test_build_decision_context_includes_agent_graph_context():
    kg = register_agents_in_kg(_base_graph(), [_agent()])
    world = WorldState(knowledge_graph=kg)
    goal = TargetGoal(description="test")
    ctx = build_decision_context(_agent(), world, goal)
    assert "agent_graph_context" in ctx
    assert any("本主体" in line for line in ctx["agent_graph_context"])
