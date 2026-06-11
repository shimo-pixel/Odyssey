from prds.models.domain import AgentState, GoalStatus, ResourceSnapshot, TargetGoal, WorldState
from prds.simulation.realism import MONTHLY_BURN_PER_HEAD, consecutive_negative_cashflow, runway_months

# ResourceSnapshot fields that can be used as goal metrics.
GOAL_METRIC_FIELDS = frozenset(
    {"cash", "revenue", "users", "product_maturity", "brand_awareness", "market_share"}
)

DEFAULT_GOAL_METRICS: dict[str, float] = {
    "revenue": 100.0,
    "users": 100_000.0,
    "market_share": 0.2,
    "product_maturity": 1.0,
}


def _metric_progress(current: float, target: float, baseline: float = 0.0) -> tuple[float, float]:
    """Progress from baseline toward target (0 at baseline, 1 at/above target)."""
    if target <= baseline:
        progress = 1.0 if current >= target else 0.0
        gap = max(0.0, target - current) if current < target else 0.0
        return progress, gap

    span = target - baseline
    progress = min(1.0, max(0.0, (current - baseline) / span))
    gap = max(0.0, target - current)
    return progress, gap


def _resolve_goal_metrics(goal: TargetGoal) -> dict[str, float]:
    if goal.success_metrics:
        filtered = {
            k: float(v)
            for k, v in goal.success_metrics.items()
            if k in GOAL_METRIC_FIELDS and float(v) > 0
        }
        if filtered:
            return filtered
    return dict(DEFAULT_GOAL_METRICS)


def compute_goal_status(
    resources: ResourceSnapshot,
    goal: TargetGoal,
    *,
    domain_id: str = "startup",
) -> GoalStatus:
    resource_map = resources.model_dump()
    metrics = _resolve_goal_metrics(goal)
    baseline_map = goal.baseline_snapshot.model_dump() if goal.baseline_snapshot else {}

    metric_progress: dict[str, float] = {}
    metric_gaps: dict[str, float] = {}
    # Only metrics with real headroom (target above baseline) carry a progress signal;
    # metrics already satisfied at baseline would otherwise inflate the average to ~100%.
    scored: list[float] = []
    for metric, target in metrics.items():
        current = float(resource_map.get(metric, 0.0))
        baseline = float(baseline_map.get(metric, 0.0))
        progress, gap = _metric_progress(current, target, baseline)
        metric_progress[metric] = progress
        metric_gaps[metric] = gap
        if target > baseline:
            scored.append(progress)

    if scored:
        overall = sum(scored) / len(scored)
    elif metric_progress:
        overall = sum(metric_progress.values()) / len(metric_progress)
    else:
        overall = 0.0
    return GoalStatus(
        progress=overall,
        distance=max(0.0, 1.0 - overall),
        metric_progress=metric_progress,
        metric_gaps=metric_gaps,
    )


def compute_goal_progress(
    resources: ResourceSnapshot,
    goal: TargetGoal,
    *,
    domain_id: str = "startup",
) -> float:
    return compute_goal_status(resources, goal, domain_id=domain_id).progress


def should_eliminate(
    agent: AgentState,
    goal: TargetGoal,
    world: WorldState,
    *,
    domain_id: str = "startup",
) -> tuple[bool, str | None]:
    runway = runway_months(agent.resources)

    if agent.resources.cash <= 0:
        return True, "资金耗尽"
    if runway < 0.5:
        return True, "runway 不足两周"
    if runway < 1.0 and consecutive_negative_cashflow(agent, 2):
        return True, "runway 少于 1 个月且持续失血"
    if agent.resources.team_size < 1:
        return True, "无法维持组织运转"
    if consecutive_negative_cashflow(agent, 4) and agent.resources.cash < MONTHLY_BURN_PER_HEAD * agent.resources.team_size * 2:
        return True, "长期失血导致现金见底"
    progress = compute_goal_progress(agent.resources, goal)
    if world.total_events > 0 and world.event_index > world.total_events * 0.6 and progress < 0.03 and runway < 2.0:
        return True, "事件过半仍远离目标且 runway 紧张"
    if agent.resources.cash < -10:
        return True, "严重资不抵债"
    return False, None


def apply_elimination(
    agents: list[AgentState],
    goal: TargetGoal,
    world: WorldState,
    *,
    domain_id: str = "startup",
) -> list[AgentState]:
    updated: list[AgentState] = []
    for agent in agents:
        if agent.eliminated:
            updated.append(agent)
            continue
        goal_status = compute_goal_status(agent.resources, goal, domain_id=domain_id)
        agent = agent.model_copy(update={"goal_progress": goal_status.progress})
        eliminate, reason = should_eliminate(agent, goal, world, domain_id=domain_id)
        if eliminate:
            agent = agent.model_copy(update={"eliminated": True, "elimination_reason": reason})
        updated.append(agent)
    return updated
