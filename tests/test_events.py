import pytest

from prds.models.domain import (
    ActionType,
    AgentAttributes,
    AgentState,
    EventCategory,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
    WorldState,
)
from prds.analysis.scoring import score_agent
from prds.simulation.actions import execute_action, randomize_attributes
from prds.simulation.elimination import compute_goal_progress, should_eliminate
from prds.world.events import EventGenerator


@pytest.fixture
def sample_agent() -> AgentState:
    return AgentState(
        agent_id="test_agent",
        strategy_type=StrategyType.BALANCED,
        attributes=AgentAttributes(execution_power=0.7),
        resources=ResourceSnapshot(cash=100, team_size=5, users=100),
    )


@pytest.fixture
def sample_world() -> WorldState:
    return WorldState(period=1, total_periods=12)


@pytest.fixture
def sample_goal() -> TargetGoal:
    return TargetGoal(description="Reach 100k users", success_metrics={"users": 100_000})


def test_event_generator_count():
    gen = EventGenerator(seed=42)
    events = gen.generate_period_events(1, count=5)
    assert len(events) == 5
    assert all(e.category in EventCategory for e in events)


def test_event_generator_random_count():
    gen = EventGenerator(seed=42)
    events = gen.generate_period_events(1)
    assert 1 <= len(events) <= 10


def test_apply_events_updates_world(sample_world):
    gen = EventGenerator(seed=1)
    events = gen.generate_period_events(1, count=3)
    updated = gen.apply_events_to_world(sample_world, events)
    assert updated.recent_events == events
    assert updated.period == sample_world.period


def test_execute_action_product_dev(sample_agent, sample_world):
    result = execute_action(
        sample_agent,
        sample_world,
        ActionType.PRODUCT_DEV,
        {"investment": 5.0},
    )
    assert result.success
    assert result.resource_change.product_maturity >= 0


def test_execute_action_insufficient_cash(sample_agent, sample_world):
    poor_agent = sample_agent.model_copy(
        update={"resources": ResourceSnapshot(cash=1, team_size=5)}
    )
    result = execute_action(
        poor_agent,
        sample_world,
        ActionType.ACQUISITION,
        {"cost": 30.0},
    )
    assert not result.success


def test_scoring_formula(sample_agent, sample_goal):
    initial = ResourceSnapshot(cash=100, team_size=5, users=5000)
    agent = sample_agent.model_copy(
        update={"resources": ResourceSnapshot(cash=80, team_size=8, users=50000, revenue=30)}
    )
    score = score_agent(agent, sample_goal, initial)
    assert 0 <= score.total_score <= 1.5
    assert score.goal_achievement >= 0


def test_elimination_cash_depleted(sample_agent, sample_goal, sample_world):
    broke = sample_agent.model_copy(
        update={"resources": ResourceSnapshot(cash=0, team_size=5)}
    )
    eliminate, reason = should_eliminate(broke, sample_goal, sample_world)
    assert eliminate
    assert reason == "资金耗尽"


def test_goal_progress_with_metrics(sample_goal):
    resources = ResourceSnapshot(users=50_000)
    progress = compute_goal_progress(resources, sample_goal)
    assert progress == pytest.approx(0.5)


def test_randomize_attributes_conservative():
    import random
    rng = random.Random(0)
    attrs = randomize_attributes(rng, "ConservativeAgent")
    assert attrs.risk_preference <= 0.5


def test_strategy_types_count():
    assert len(StrategyType) == 10
