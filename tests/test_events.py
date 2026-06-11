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
from prds.llm.schemas import EventPlan
from prds.simulation.actions import apply_result_resources, execute_action, randomize_attributes
from prds.simulation.elimination import compute_goal_progress, compute_goal_status, should_eliminate
from prds.world.event_planner import plan_events, plan_to_events
from prds.world.events import EventProcessor


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
    return WorldState(event_index=1, total_events=12)


@pytest.fixture
def sample_goal() -> TargetGoal:
    return TargetGoal(description="Reach 100k users", success_metrics={"users": 100_000})


def test_event_processor_apply_events(sample_world):
    processor = EventProcessor()
    events = [
        Event(
            event_id="evt_1",
            event_type="policy_support",
            category=EventCategory.MACRO,
            impact=0.3,
            probability=0.7,
            severity=0.5,
            description="测试事件",
        )
    ]
    updated = processor.apply_events_to_world(sample_world, events, event_index=1)
    assert updated.recent_events == events
    assert updated.event_index == 1


def test_execute_action_product_dev(sample_agent, sample_world, sample_goal):
    result = execute_action(
        sample_agent,
        sample_world,
        ActionType.PRODUCT_DEV,
        {"investment": 5.0},
    )
    assert result.success
    assert result.financials.total_expense > 0


def test_plan_to_events_filters_low_probability():
    plan = EventPlan(
        events=[
            {
                "event_type": "rare_event",
                "category": "market",
                "impact": 0.2,
                "severity": 0.5,
                "probability": 0.1,
                "description": "低概率",
            },
            {
                "event_type": "likely_event",
                "category": "market",
                "impact": 0.2,
                "severity": 0.5,
                "probability": 0.8,
                "description": "高概率",
            },
        ]
    )
    events = plan_to_events(plan, max_events=10)
    assert len(events) == 1
    assert events[0].event_type == "likely_event"


@pytest.mark.asyncio
async def test_plan_events(sample_goal):
    from prds.llm.client import LLMClient
    from prds.models.domain import CurrentState, SimulationConfig

    llm = LLMClient()
    state = CurrentState(background="AI startup in early stage")
    config = SimulationConfig(max_events=12)
    events = await plan_events(llm, state, sample_goal, config)
    assert len(events) >= 1
