import pytest

from prds.analysis.scoring import rank_agents, score_agent
from prds.models.domain import (
    AgentState,
    AgentAttributes,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
)


def test_score_weights():
    goal = TargetGoal(description="test", success_metrics={"revenue": 100})
    initial = ResourceSnapshot(cash=100, revenue=0)
    agent = AgentState(
        agent_id="a1",
        strategy_type=StrategyType.GROWTH,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=50, revenue=80, users=1000),
        execution_score=0.8,
        adaptability_score=0.7,
        risk_exposure=0.2,
    )
    score = score_agent(agent, goal, initial)
    expected = (
        score.goal_achievement * 0.40
        + score.resource_efficiency * 0.20
        + score.risk_control * 0.15
        + score.execution_quality * 0.15
        + score.adaptability * 0.10
    )
    assert score.total_score == pytest.approx(expected, rel=1e-3)


def test_rank_agents_returns_top_n():
    goal = TargetGoal(description="grow users", success_metrics={"users": 1000})
    initial = ResourceSnapshot()
    agents = [
        AgentState(
            agent_id=f"a{i}",
            strategy_type=StrategyType.BALANCED,
            attributes=AgentAttributes(),
            resources=ResourceSnapshot(users=i * 100),
        )
        for i in range(15)
    ]
    top = rank_agents(agents, goal, initial, top_n=10)
    assert len(top) == 10
    assert top[0].total_score >= top[-1].total_score
