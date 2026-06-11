from unittest.mock import MagicMock, patch

import pytest

from prds.config import Settings
from prds.graph.episodic import (
    BuiltinEpisodicGraph,
    build_event_episode,
    create_episodic_session,
)
from prds.models.domain import (
    AgentAttributes,
    AgentState,
    DecisionLogEntry,
    Event,
    EventCategory,
    KnowledgeGraphData,
    ResourceSnapshot,
    StrategyType,
    WorldState,
)


class _DummyLLM:
    analysis_model = "dummy"
    default_model = "dummy"

    async def complete(self, *, system, user, model=None):
        raise RuntimeError("no llm in this test")


def _event() -> Event:
    return Event(
        event_id="ev1",
        event_type="competitor_entry",
        category=EventCategory.MARKET,
        impact=-0.3,
        probability=0.8,
        severity=0.5,
        description="新竞争对手进入市场",
    )


def _agent() -> AgentState:
    return AgentState(
        agent_id="a1",
        strategy_type=StrategyType.AGGRESSIVE,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=100),
        timeline=[
            DecisionLogEntry(
                event_index=1,
                trigger_event_id="ev1",
                world_state=WorldState(),
                action="product_dev",
                reasoning="加速产品迭代以应对竞争",
            )
        ],
    )


def test_build_event_episode_includes_event_and_reaction():
    text = build_event_episode(1, [_event()], [_agent()], world_summary="行业竞争激烈")
    assert "competitor_entry" in text
    assert "新竞争对手进入市场" in text
    assert "product_dev" in text
    assert "AggressiveAgent" in text
    assert "a1" in text


@pytest.mark.asyncio
async def test_create_session_falls_back_to_builtin_when_graphiti_unavailable():
    settings = Settings(prds_graph_backend="graphiti", prds_dynamic_graph=False)
    base = KnowledgeGraphData(
        nodes=[{"id": "org1", "entity_type": "organization", "name": "Acme"}],
        edges=[],
    )
    mock_store = MagicMock()
    mock_store.available = False
    with patch("prds.graph.episodic.get_graphiti_store", return_value=mock_store):
        session = await create_episodic_session(
            _DummyLLM(), "sim_test", base, world_summary="bg", settings=settings
        )
    assert isinstance(session, BuiltinEpisodicGraph)
    assert session.backend == "builtin"


@pytest.mark.asyncio
async def test_builtin_session_seed_is_noop_and_snapshot_works():
    settings = Settings(prds_graph_backend="builtin", prds_dynamic_graph=False)
    base = KnowledgeGraphData(
        nodes=[{"id": "org1", "entity_type": "organization", "name": "Acme"}],
        edges=[],
    )
    session = await create_episodic_session(
        _DummyLLM(), "sim_test", base, settings=settings
    )
    await session.seed("doc")
    await session.register_agents([_agent()])
    await session.ingest_event(1, [_event()], [_agent()])
    data = await session.graph_data()
    assert data is not None
    assert any(n.get("entity_type") == "event" for n in data.nodes)
    assert any(n.get("entity_type") == "agent" and n.get("id") == "a1" for n in data.nodes)
