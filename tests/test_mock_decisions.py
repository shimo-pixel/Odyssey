from prds.llm.mock_decisions import build_mock_decision
from prds.models.domain import (
    ActionType,
    AgentAttributes,
    AgentState,
    PeriodLogEntry,
    ResourceSnapshot,
    StrategyType,
    WorldState,
)


def _agent(strategy: StrategyType, *, cash: float = 100.0, timeline: list | None = None) -> AgentState:
    return AgentState(
        agent_id=f"agent_test_{strategy.value}",
        strategy_type=strategy,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=cash, team_size=5, users=50),
        timeline=timeline or [],
    )


def test_aggressive_agent_does_not_default_to_fundraise():
    agent = _agent(StrategyType.AGGRESSIVE)
    world = WorldState(period=1, total_periods=6)
    decision = build_mock_decision(agent, world, "Reach 1000 users")
    assert decision.action != ActionType.FUNDRAISE
    assert decision.action in (
        ActionType.MARKETING,
        ActionType.HIRE,
        ActionType.PRODUCT_DEV,
        ActionType.STRATEGIC_PIVOT,
    )


def test_agents_get_different_actions_same_period():
    world = WorldState(period=1, total_periods=6)
    goal = "Reach 1000 users"
    actions = {
        build_mock_decision(_agent(s), world, goal).action
        for s in StrategyType
    }
    assert len(actions) > 1


def test_no_consecutive_fundraise():
    agent = _agent(
        StrategyType.FINANCIAL,
        cash=15.0,
        timeline=[
            PeriodLogEntry(
                period=1,
                world_state=WorldState(period=1),
                action=ActionType.FUNDRAISE,
            )
        ],
    )
    world = WorldState(period=2, total_periods=6)
    decision = build_mock_decision(agent, world, "Extend runway")
    assert decision.action != ActionType.FUNDRAISE
