from prds.models.domain import AgentState, ResourceSnapshot, TargetGoal, WorldState


def compute_goal_progress(resources: ResourceSnapshot, goal: TargetGoal) -> float:
    if not goal.success_metrics:
        score_parts = [
            min(1.0, resources.revenue / 100.0),
            min(1.0, resources.users / 100_000.0),
            min(1.0, resources.market_share / 0.2),
            resources.product_maturity,
        ]
        return sum(score_parts) / len(score_parts)

    progress_values: list[float] = []
    resource_map = resources.model_dump()
    for metric, target in goal.success_metrics.items():
        current = resource_map.get(metric, 0.0)
        if target <= 0:
            progress_values.append(1.0 if current >= target else 0.0)
        else:
            progress_values.append(min(1.0, current / target))
    return sum(progress_values) / len(progress_values) if progress_values else 0.0


def should_eliminate(agent: AgentState, goal: TargetGoal, world: WorldState) -> tuple[bool, str | None]:
    if agent.resources.cash <= 0:
        return True, "资金耗尽"
    if agent.resources.team_size < 1:
        return True, "无法维持组织运转"
    progress = compute_goal_progress(agent.resources, goal)
    if world.period > world.total_periods * 0.5 and progress < 0.05 and agent.risk_exposure > 0.8:
        return True, "明显偏离目标且风险过高"
    if agent.resources.cash < -10:
        return True, "严重资不抵债"
    return False, None


def apply_elimination(agents: list[AgentState], goal: TargetGoal, world: WorldState) -> list[AgentState]:
    updated: list[AgentState] = []
    for agent in agents:
        if agent.eliminated:
            updated.append(agent)
            continue
        progress = compute_goal_progress(agent.resources, goal)
        agent = agent.model_copy(update={"goal_progress": progress})
        eliminate, reason = should_eliminate(agent, goal, world)
        if eliminate:
            agent = agent.model_copy(update={"eliminated": True, "elimination_reason": reason})
        updated.append(agent)
    return updated
