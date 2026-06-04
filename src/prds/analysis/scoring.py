from prds.models.domain import AgentScore, AgentState, ResourceSnapshot, StrategyType, TargetGoal
from prds.simulation.elimination import compute_goal_progress


def _resource_efficiency(agent: AgentState, initial: ResourceSnapshot) -> float:
    if initial.cash <= 0:
        return 0.5
    final_value = (
        agent.resources.cash
        + agent.resources.revenue * 2
        + agent.resources.users * 0.01
        + agent.resources.market_share * 100
    )
    initial_value = (
        initial.cash
        + initial.revenue * 2
        + initial.users * 0.01
        + initial.market_share * 100
    )
    if initial_value <= 0:
        return min(1.0, final_value / 100.0)
    ratio = final_value / initial_value
    return max(0.0, min(1.0, ratio / 3.0))


def score_agent(
    agent: AgentState,
    goal: TargetGoal,
    initial_resources: ResourceSnapshot,
) -> AgentScore:
    goal_achievement = compute_goal_progress(agent.resources, goal)
    resource_efficiency = _resource_efficiency(agent, initial_resources)
    risk_control = max(0.0, 1.0 - agent.risk_exposure)
    execution_quality = agent.execution_score
    adaptability = agent.adaptability_score

    total = (
        goal_achievement * 0.40
        + resource_efficiency * 0.20
        + risk_control * 0.15
        + execution_quality * 0.15
        + adaptability * 0.10
    )

    return AgentScore(
        agent_id=agent.agent_id,
        strategy_type=agent.strategy_type,
        total_score=round(total, 4),
        goal_achievement=round(goal_achievement, 4),
        resource_efficiency=round(resource_efficiency, 4),
        risk_control=round(risk_control, 4),
        execution_quality=round(execution_quality, 4),
        adaptability=round(adaptability, 4),
        final_resources=agent.resources,
    )


def rank_agents(
    agents: list[AgentState],
    goal: TargetGoal,
    initial_resources: ResourceSnapshot,
    top_n: int = 10,
) -> list[AgentScore]:
    scores = [score_agent(a, goal, initial_resources) for a in agents if not a.eliminated]
    if not scores:
        scores = [score_agent(a, goal, initial_resources) for a in agents]
    scores.sort(key=lambda s: s.total_score, reverse=True)
    return scores[:top_n]
