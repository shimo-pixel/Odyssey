"""Tests for ontology subject node and graph pruning."""

from prds.graph.ontology_subject import (
    SUBJECT_NODE_ID,
    inject_ontology_subject,
    link_subject_event_actions,
    prune_isolated_nodes,
)
from prds.models.domain import (
    AgentAttributes,
    AgentState,
    CurrentState,
    Event,
    EventCategory,
    KnowledgeGraphData,
    DecisionLogEntry,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
    WorldState,
)


def test_inject_ontology_subject_links_to_org():
    kg = KnowledgeGraphData(
        nodes=[{"id": "org1", "entity_type": "organization", "name": "Acme"}],
        edges=[],
    )
    state = CurrentState(background="AI startup", organization={"name": "Acme Inc"})
    goal = TargetGoal(description="Reach product-market fit")
    result = inject_ontology_subject(kg, current_state=state, goal=goal)
    ids = {n["id"] for n in result.nodes}
    assert SUBJECT_NODE_ID in ids
    subject = next(n for n in result.nodes if n["id"] == SUBJECT_NODE_ID)
    assert subject["entity_type"] == "ontology"
    assert subject.get("is_central")
    assert any(
        e["source"] == SUBJECT_NODE_ID and e["target"] == "org1" for e in result.edges
    )


def test_prune_isolated_nodes_removes_orphans():
    kg = KnowledgeGraphData(
        nodes=[
            {"id": "a", "entity_type": "organization", "name": "A"},
            {"id": "b", "entity_type": "entity", "name": "Orphan"},
            {"id": SUBJECT_NODE_ID, "entity_type": "ontology", "name": "Subject", "is_central": True},
        ],
        edges=[{"source": "a", "target": SUBJECT_NODE_ID, "relation_type": "related_to"}],
    )
    pruned = prune_isolated_nodes(kg)
    ids = {n["id"] for n in pruned.nodes}
    assert "b" not in ids
    assert SUBJECT_NODE_ID in ids
    assert "a" in ids


def test_link_subject_event_actions_creates_outcome():
    kg = KnowledgeGraphData(
        nodes=[
            {"id": SUBJECT_NODE_ID, "entity_type": "ontology", "name": "Subject"},
            {"id": "ev_1", "entity_type": "event", "name": "market_shift"},
        ],
        edges=[],
    )
    event = Event(
        event_id="ev_1",
        event_type="market_shift",
        category=EventCategory.MARKET,
        impact=-0.2,
        probability=0.7,
        severity=0.5,
        description="需求下滑",
    )
    agent = AgentState(
        agent_id="a1",
        strategy_type=StrategyType.BALANCED,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=100),
        timeline=[
            DecisionLogEntry(
                event_index=1,
                world_state=WorldState(),
                action="product_dev",
                reasoning="加速迭代应对市场变化",
            )
        ],
    )
    result = link_subject_event_actions(kg, [agent], [event], event_index=1)
    assert any(
        e["source"] == SUBJECT_NODE_ID and e["target"] == "ev_1" and e["relation_type"] == "responds_to"
        for e in result.edges
    )
    outcomes = [n for n in result.nodes if n.get("entity_type") == "outcome"]
    assert len(outcomes) == 1
    assert any(e["relation_type"] == "results_in" for e in result.edges)
