import pytest

from prds.graph.incremental import IncrementalGraphBuilder
from prds.models.domain import (
    AgentAttributes,
    AgentState,
    Event,
    EventCategory,
    KnowledgeGraphData,
    DecisionLogEntry,
    ResourceSnapshot,
    StrategyType,
    WorldState,
)


def _base_graph() -> KnowledgeGraphData:
    return KnowledgeGraphData(
        nodes=[
            {"id": "org1", "entity_type": "organization", "name": "Acme"},
            {"id": "mkt1", "entity_type": "market", "name": "Market"},
        ],
        edges=[{"source": "org1", "target": "mkt1", "relation_type": "competes"}],
    )


def _event(period: int) -> Event:
    return Event(
        event_id=f"ev_{period}",
        event_type="competitor_entry",
        category=EventCategory.MARKET,
        impact=-0.2,
        probability=0.8,
        severity=0.5,
        description="新竞争对手进入",
    )


def _agent(active: bool) -> AgentState:
    return AgentState(
        agent_id="a1",
        strategy_type=StrategyType.AGGRESSIVE,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=100),
        timeline=[
            DecisionLogEntry(
                event_index=1,
                world_state=WorldState(),
                action="product_dev" if active else "hold",
                reasoning="加速产品迭代",
            )
        ],
    )


class _DummyLLM:
    analysis_model = "dummy"
    default_model = "dummy"

    async def complete(self, *, system, user, model=None):
        raise RuntimeError("no llm in this test")


@pytest.mark.asyncio
async def test_seed_nodes_tagged_period_zero():
    builder = IncrementalGraphBuilder(_DummyLLM(), _base_graph(), enabled=False)
    snap = builder.snapshot()
    assert all(n["first_seen_event"] == 0 for n in snap.nodes)


@pytest.mark.asyncio
async def test_events_added_with_period_tag_and_temporal_chain():
    builder = IncrementalGraphBuilder(_DummyLLM(), _base_graph(), enabled=False)
    await builder.ingest_event(1, [_event(1)], [_agent(True)])
    await builder.ingest_event(2, [_event(2)], [_agent(True)])
    snap = builder.snapshot()

    ev1 = next(n for n in snap.nodes if n["id"] == "ev_1")
    ev2 = next(n for n in snap.nodes if n["id"] == "ev_2")
    assert ev1["first_seen_event"] == 1
    assert ev2["first_seen_event"] == 2

    # temporal backbone: ev_1 precedes ev_2
    assert any(
        e["source"] == "ev_1" and e["target"] == "ev_2" and e["relation_type"] == "precedes"
        for e in snap.edges
    )
    # event influences a market entity
    assert any(e["source"] == "ev_1" and e["target"] == "mkt1" for e in snap.edges)


@pytest.mark.asyncio
async def test_register_agents_at_spawn_period_zero():
    builder = IncrementalGraphBuilder(_DummyLLM(), _base_graph(), enabled=False)
    builder.register_agents([_agent(True)])
    snap = builder.snapshot()
    agent_nodes = [n for n in snap.nodes if n.get("entity_type") == "agent"]
    assert len(agent_nodes) == 1
    assert agent_nodes[0]["id"] == "a1"
    assert agent_nodes[0]["first_seen_event"] == 0
    assert any(
        e["source"] == "a1" and e["target"] == "org1" and e["relation_type"] == "operates_in"
        for e in snap.edges
    )


@pytest.mark.asyncio
async def test_responds_to_edge_after_period_ingest():
    builder = IncrementalGraphBuilder(_DummyLLM(), _base_graph(), enabled=False)
    builder.register_agents([_agent(True)])
    await builder.ingest_event(1, [_event(1)], [_agent(True)])
    snap = builder.snapshot()
    assert any(
        e["source"] == "a1"
        and e["target"] == "ev_1"
        and e["relation_type"] == "responds_to"
        for e in snap.edges
    )


@pytest.mark.asyncio
async def test_holding_agent_no_responds_to_edge():
    builder = IncrementalGraphBuilder(_DummyLLM(), _base_graph(), enabled=False)
    builder.register_agents([_agent(False)])
    await builder.ingest_event(1, [_event(1)], [_agent(False)])
    snap = builder.snapshot()
    assert [n for n in snap.nodes if n.get("entity_type") == "agent"]
    assert not any(e["relation_type"] == "responds_to" for e in snap.edges)
