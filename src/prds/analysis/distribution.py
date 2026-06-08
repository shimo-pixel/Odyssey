"""Aggregate many parallel agents/seeds into honest distributions, not single points."""

from statistics import mean

from prds.models.domain import (
    AgentState,
    MetricBand,
    OutcomeDistribution,
    ParamAssumption,
    PeriodProgressBand,
    TargetGoal,
)
from prds.simulation.elimination import compute_goal_status

_STARTUP_METRIC_LABELS = {
    "cash": "现金",
    "revenue": "营收",
    "users": "用户数",
    "market_share": "市场份额",
    "product_maturity": "产品成熟度",
}
def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _band(metric: str, label: str, values: list[float]) -> MetricBand:
    s = sorted(values)
    return MetricBand(
        metric=metric,
        label=label,
        p10=_percentile(s, 0.10),
        p25=_percentile(s, 0.25),
        median=_percentile(s, 0.50),
        p75=_percentile(s, 0.75),
        p90=_percentile(s, 0.90),
        mean=mean(s) if s else 0.0,
    )


def _final_goal_status(agent: AgentState, goal: TargetGoal, domain_id: str):
    """Prefer the agent's last recorded period status; fall back to recomputing."""
    if agent.timeline and agent.timeline[-1].goal_status is not None:
        return agent.timeline[-1].goal_status
    return compute_goal_status(agent.resources, goal, domain_id=domain_id)


def _all_metrics_met(status, threshold: float = 0.999) -> bool:
    mp = status.metric_progress or {}
    if not mp:
        return status.progress >= threshold
    return all(p >= threshold for p in mp.values())


def _metric_value(agent: AgentState, metric: str) -> float:
    dm = agent.resources.domain_metrics or {}
    if metric in dm:
        return float(dm[metric])
    return float(getattr(agent.resources, metric, 0.0))


def _param_assumptions(domain_id: str, overrides: dict | None) -> list[ParamAssumption]:
    from prds.simulation.parameters import StartupParams, resolve_params

    base = StartupParams()
    resolved = resolve_params(base, overrides)
    return [
        ParamAssumption(
            key=spec.key,
            label=spec.label,
            value=round(spec.value, 5),
            min=spec.min,
            max=spec.max,
            group=spec.group,
        )
        for spec in resolved.specs()
    ]


def build_outcome_distribution(
    agents: list[AgentState],
    goal: TargetGoal,
    *,
    domain_id: str = "startup",
    replications: int = 1,
    param_overrides: dict | None = None,
    success_threshold: float = 0.9,
    near_threshold: float = 0.7,
) -> OutcomeDistribution:
    if not agents:
        return OutcomeDistribution(
            replications=replications,
            param_assumptions=_param_assumptions(domain_id, param_overrides),
        )

    # Use each agent's final goal status so the distribution matches exactly what the
    # overview matrix shows for the last period (single source of truth).
    statuses = [_final_goal_status(a, goal, domain_id) for a in agents]
    progresses = [s.progress for s in statuses]
    n = len(agents)
    success = sum(1 for p in progresses if p >= success_threshold)
    near = sum(1 for p in progresses if p >= near_threshold)
    achieved = sum(1 for s in statuses if _all_metrics_met(s))
    eliminated = sum(1 for a in agents if a.eliminated)

    labels = _STARTUP_METRIC_LABELS
    metric_keys = list((goal.success_metrics or {}).keys()) or list(labels.keys())
    metric_bands = [
        _band(m, labels.get(m, m), [_metric_value(a, m) for a in agents]) for m in metric_keys
    ]

    # Per-period progress band across agents (uses recorded goal_status per timeline entry).
    max_periods = max((len(a.timeline) for a in agents), default=0)
    trajectory: list[PeriodProgressBand] = []
    for idx in range(max_periods):
        vals = [
            a.timeline[idx].goal_status.progress
            for a in agents
            if idx < len(a.timeline)
        ]
        if not vals:
            continue
        s = sorted(vals)
        period = next(
            (a.timeline[idx].period for a in agents if idx < len(a.timeline)), idx + 1
        )
        trajectory.append(
            PeriodProgressBand(
                period=period,
                p25=_percentile(s, 0.25),
                median=_percentile(s, 0.50),
                p75=_percentile(s, 0.75),
            )
        )

    reasons: dict[str, int] = {}
    for a in agents:
        if a.eliminated and a.elimination_reason:
            reasons[a.elimination_reason] = reasons.get(a.elimination_reason, 0) + 1

    return OutcomeDistribution(
        sample_size=n,
        replications=replications,
        success_threshold=success_threshold,
        success_rate=round(success / n, 4),
        near_success_rate=round(near / n, 4),
        achieved_rate=round(achieved / n, 4),
        elimination_rate=round(eliminated / n, 4),
        goal_progress=_band("goal_progress", "目标完成度", progresses),
        metric_bands=metric_bands,
        progress_trajectory=trajectory,
        elimination_reasons=dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        param_assumptions=_param_assumptions(domain_id, param_overrides),
    )
