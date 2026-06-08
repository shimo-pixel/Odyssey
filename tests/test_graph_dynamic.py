from prds.agents.factory import create_agents
from prds.graph.dynamic import add_agents_to_kg, add_events_to_kg, extract_domain_facts
from prds.models.domain import (
    Event,
    EventCategory,
    KnowledgeGraphData,
    ResourceSnapshot,
)


def _sample_kg() -> KnowledgeGraphData:
    return KnowledgeGraphData(
        nodes=[
            {"id": "e1", "entity_type": "organization", "name": "面馆"},
            {"id": "e2", "entity_type": "market", "name": "本地餐饮市场"},
            {"id": "e3", "entity_type": "capital", "name": "启动资金"},
        ],
        edges=[{"source": "e1", "target": "e2", "relation_type": "competes"}],
    )


def test_add_events_to_kg_adds_event_nodes_and_edges():
    kg = _sample_kg()
    calendar = {
        1: [
            Event(
                event_id="evt_1_abc",
                event_type="seasonal_demand_peak",
                category=EventCategory.MARKET,
                impact=0.3,
                probability=0.8,
                severity=0.5,
                description="节假日带来季节性需求高峰",
            )
        ]
    }
    grown = add_events_to_kg(kg, calendar)
    event_nodes = [n for n in grown.nodes if n.get("entity_type") == "event"]
    assert len(event_nodes) == 1
    assert event_nodes[0]["id"] == "evt_1_abc"
    assert any(e["source"] == "evt_1_abc" for e in grown.edges)


def test_add_agents_to_kg_adds_agent_nodes():
    kg = _sample_kg()
    agents = create_agents(3, ResourceSnapshot(), seed=1)
    grown = add_agents_to_kg(kg, agents)
    agent_nodes = [n for n in grown.nodes if n.get("entity_type") == "agent"]
    assert len(agent_nodes) == 3


def test_extract_domain_facts_skips_agent_edges():
    kg = _sample_kg()
    agents = create_agents(2, ResourceSnapshot(), seed=1)
    grown = add_agents_to_kg(kg, agents)
    facts = extract_domain_facts(grown)
    assert facts
    assert all("competes" not in f or "面馆" in f for f in facts)
    # agent->org edges must not appear as facts
    assert not any(a.agent_id in " ".join(facts) for a in agents)
