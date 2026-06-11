"""Derive conclusions (roadmap, turning points, counterfactuals) from simulation
statistics instead of free-form LLM generation, so they are traceable to data."""

from collections import Counter, defaultdict

from prds.models.domain import (
    AgentState,
    CounterfactualComparison,
    OutcomeDistribution,
    StrategySynthesis,
    TargetGoal,
)
from prds.simulation.elimination import compute_goal_status

ACTION_LABELS = {
    "startup": {
        "hire": "招聘", "layoff": "裁员", "fundraise": "融资", "product_dev": "产品研发",
        "marketing": "市场推广", "strategic_pivot": "战略转型", "partnership": "合作",
        "acquisition": "并购", "cost_cut": "削减成本", "hold": "观望",
    },
}


def _label(domain_id: str, action: str) -> str:
    return ACTION_LABELS.get(domain_id, {}).get(action, action)


def _progress(agent: AgentState, goal: TargetGoal, domain_id: str) -> float:
    return compute_goal_status(agent.resources, goal, domain_id=domain_id).progress


def _action_freq(agents: list[AgentState]) -> Counter:
    c: Counter = Counter()
    for a in agents:
        for entry in a.timeline:
            c[str(entry.action)] += 1
    return c


def _normalized(freq: Counter) -> dict[str, float]:
    total = sum(freq.values()) or 1
    return {k: v / total for k, v in freq.items()}


def build_data_driven_synthesis(
    agents: list[AgentState],
    goal: TargetGoal,
    distribution: OutcomeDistribution,
    *,
    domain_id: str = "startup",
) -> StrategySynthesis:
    ranked = sorted(agents, key=lambda a: _progress(a, goal, domain_id), reverse=True)
    n = len(ranked)
    top = ranked[: max(1, n // 4)]
    bottom = ranked[-max(1, n // 4):] if n >= 2 else []
    eliminated = [a for a in agents if a.eliminated]

    top_norm = _normalized(_action_freq(top))
    bottom_norm = _normalized(_action_freq(bottom))
    elim_norm = _normalized(_action_freq(eliminated)) if eliminated else {}

    # Success factors: actions far more common among top performers than bottom.
    success_factors: list[str] = []
    for action, freq in sorted(top_norm.items(), key=lambda kv: -kv[1]):
        lift = freq - bottom_norm.get(action, 0.0)
        if lift > 0.03:
            success_factors.append(
                f"{_label(domain_id, action)}：在头部路径中占比 {freq:.0%}，比落后路径高 {lift*100:.0f} 个百分点"
            )
        if len(success_factors) >= 4:
            break

    failure_avoidance_factors: list[str] = []
    for action, freq in sorted(elim_norm.items(), key=lambda kv: -kv[1]):
        lift = freq - top_norm.get(action, 0.0)
        if lift > 0.03:
            failure_avoidance_factors.append(
                f"{_label(domain_id, action)}：在被淘汰路径中占比 {freq:.0%}，偏高 {lift*100:.0f} 个百分点"
            )
        if len(failure_avoidance_factors) >= 4:
            break
    if not failure_avoidance_factors and distribution.elimination_reasons:
        for reason, count in list(distribution.elimination_reasons.items())[:3]:
            failure_avoidance_factors.append(f"{reason}（{count} 条路径因此出局）")

    # Roadmap: most common action among top performers each period (with support %).
    per_event_top: dict[int, Counter] = defaultdict(Counter)
    for a in top:
        for entry in a.timeline:
            per_event_top[entry.event_index][str(entry.action)] += 1
    recommended_roadmap: list[str] = []
    for event_index in sorted(per_event_top):
        counter = per_event_top[event_index]
        action, count = counter.most_common(1)[0]
        share = count / sum(counter.values())
        recommended_roadmap.append(
            f"事件 #{event_index}：头部路径最常选择「{_label(domain_id, action)}」（{share:.0%}）"
        )

    # Turning points: periods where top vs bottom median progress diverged most.
    turning: list[tuple[int, float]] = []
    max_p = max((len(a.timeline) for a in agents), default=0)
    for idx in range(max_p):
        top_vals = [a.timeline[idx].goal_status.progress for a in top if idx < len(a.timeline)]
        bot_vals = [a.timeline[idx].goal_status.progress for a in bottom if idx < len(a.timeline)]
        if not top_vals or not bot_vals:
            continue
        event_index = next((a.timeline[idx].event_index for a in top if idx < len(a.timeline)), idx + 1)
        gap = (sum(top_vals) / len(top_vals)) - (sum(bot_vals) / len(bot_vals))
        turning.append((event_index, gap))
    turning.sort(key=lambda kv: -kv[1])
    key_turning_points = [
        f"事件 #{event_index}：头部与落后路径的目标进度差距达 {gap*100:.0f} 个百分点"
        for event_index, gap in turning[:3]
        if gap > 0.01
    ]

    principles = [
        f"在 {distribution.sample_size} 条平行路径中，目标完成度中位数为 {distribution.goal_progress.median:.0%}"
        f"（区间 {distribution.goal_progress.p25:.0%}–{distribution.goal_progress.p75:.0%}）",
        f"达到目标（≥{distribution.success_threshold:.0%}）的比例约 {distribution.success_rate:.0%}，"
        f"出局比例约 {distribution.elimination_rate:.0%}",
    ]
    if success_factors:
        principles.append("头部路径的共性集中在：" + "、".join(
            f.split("：")[0] for f in success_factors[:3]
        ))

    return StrategySynthesis(
        principles=principles,
        key_turning_points=key_turning_points or ["各期头部与落后路径差距平稳，无显著拐点"],
        success_factors=success_factors or ["头部路径动作分布与整体接近，无显著差异化因素"],
        failure_avoidance_factors=failure_avoidance_factors or ["未观察到明显导致出局的高频动作"],
        recommended_roadmap=recommended_roadmap or ["样本不足以提取分期路线"],
        disclaimer=(
            f"以上结论由 {distribution.sample_size} 条平行世界路径的统计分布提取，"
            "非 LLM 自由生成，亦非直接建议；参数未经真实数据校准。"
        ),
    )


def build_data_driven_counterfactuals(
    agents: list[AgentState],
    goal: TargetGoal,
    *,
    domain_id: str = "startup",
    max_nodes: int = 4,
) -> list[CounterfactualComparison]:
    """At each period, compare the outcome of the most common action choice vs the
    alternative that led to the best median final progress."""
    final_progress = {a.agent_id: _progress(a, goal, domain_id) for a in agents}

    # period -> action -> list of final progresses of agents who took it that period
    per_event: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for a in agents:
        for entry in a.timeline:
            per_event[entry.event_index][str(entry.action)].append(final_progress[a.agent_id])

    scored: list[tuple[int, float, str, float, str, float]] = []
    for event_index, action_map in per_event.items():
        usable = {act: vals for act, vals in action_map.items() if len(vals) >= 2}
        if len(usable) < 2:
            continue
        medians = {act: sorted(vals)[len(vals) // 2] for act, vals in usable.items()}
        best = max(medians, key=medians.get)
        worst = min(medians, key=medians.get)
        if best == worst:
            continue
        spread = medians[best] - medians[worst]
        scored.append((event_index, spread, best, medians[best], worst, medians[worst]))

    scored.sort(key=lambda x: -x[1])
    comparisons: list[CounterfactualComparison] = []
    for event_index, spread, best, best_med, worst, worst_med in scored[:max_nodes]:
        comparisons.append(
            CounterfactualComparison(
                event_index=event_index,
                decision_a=_label(domain_id, best),
                outcome_a=f"该期选此动作的路径，最终目标完成度中位数 {best_med:.0%}",
                decision_b=_label(domain_id, worst),
                outcome_b=f"该期选此动作的路径，最终目标完成度中位数 {worst_med:.0%}",
                difference=f"两类选择最终差距约 {spread*100:.0f} 个百分点（基于平行路径统计）",
            )
        )
    if not comparisons:
        comparisons.append(
            CounterfactualComparison(
                event_index=1,
                decision_a="样本不足",
                outcome_a="本次推演的路径分化不足以提取可靠反事实对比",
                decision_b="—",
                outcome_b="—",
                difference="建议增加平行路径数量或推演周期",
            )
        )
    return comparisons
