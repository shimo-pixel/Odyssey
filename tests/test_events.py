import pytest

from prds.models.domain import (
    ActionType,
    AgentAttributes,
    AgentState,
    Event,
    EventCategory,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
    WorldState,
)
from prds.analysis.scoring import score_agent
from prds.llm.schemas import EventTimelinePlan
from prds.simulation.actions import apply_result_resources, execute_action, randomize_attributes
from prds.simulation.elimination import compute_goal_progress, compute_goal_status, should_eliminate
from prds.world.event_planner import plan_event_timeline, plan_to_calendar
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


def test_execute_action_product_dev(sample_agent, sample_world, sample_goal):
    result = execute_action(
        sample_agent,
        sample_world,
        ActionType.PRODUCT_DEV,
        {"investment": 5.0},
    )
    assert result.success
    assert result.financials.total_expense > 0
    assert result.financials.operating_burn > 0
    new_resources = apply_result_resources(sample_agent, result)
    goal_status = compute_goal_status(new_resources, sample_goal)
    assert 0 <= goal_status.progress <= 1
    assert goal_status.distance == pytest.approx(1 - goal_status.progress)


def test_goal_status_metric_gaps(sample_goal):
    resources = ResourceSnapshot(users=50_000)
    status = compute_goal_status(resources, sample_goal)
    assert status.metric_progress["users"] == pytest.approx(0.5)
    assert status.metric_gaps["users"] == pytest.approx(50_000)
    assert status.progress == pytest.approx(0.5)
    assert status.distance == pytest.approx(0.5)


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


def test_events_for_period_uses_planned_calendar():
    planned = {
        2: [
            Event(
                event_id="evt_2_test",
                event_type="policy_support",
                category=EventCategory.MACRO,
                impact=0.3,
                probability=0.7,
                severity=0.5,
                description="测试事件",
            )
        ]
    }
    gen = EventGenerator(seed=1, planned_by_period=planned)
    assert len(gen.events_for_period(2)) == 1
    assert gen.events_for_period(1) == []


def test_plan_to_calendar_clamps_period():
    plan = EventTimelinePlan(
        events=[
            {
                "period": 999,
                "event_type": "late_event",
                "category": "market",
                "impact": 0.2,
                "severity": 0.5,
                "description": "晚期事件",
            }
        ]
    )
    calendar = plan_to_calendar(plan, total_periods=12)
    assert 12 in calendar
    assert 999 not in calendar


@pytest.mark.asyncio
async def test_plan_event_timeline(sample_goal):
    from prds.llm.client import LLMClient
    from prds.models.domain import CurrentState, SimulationConfig

    llm = LLMClient()
    state = CurrentState(background="AI startup in early stage")
    config = SimulationConfig(periods=12)
    calendar = await plan_event_timeline(llm, state, sample_goal, config)
    assert len(calendar) >= 1
    total_events = sum(len(v) for v in calendar.values())
    assert total_events >= 2
