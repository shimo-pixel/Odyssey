"""State prediction: retrieval-augmented generation of each branch's next state.

The prediction is written back into the branch's own knowledge base as a
snapshot document, so the next event's retrieval sees the evolved world.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from prds.kbsim.prompts import STATE_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import (
    BranchProfile,
    BranchStateUpdate,
    Event,
    GoalStatus,
    MetricReading,
    MetricSpec,
    StrategyOption,
    TargetGoal,
)

logger = logging.getLogger(__name__)


class MetricPrediction(BaseModel):
    name: str = ""
    value: float = 0.0
    reason: str = ""


class StatePrediction(BaseModel):
    narrative: str = ""
    metrics: list[MetricPrediction] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    success: bool = True


def compute_goal_status(
    metrics: list[MetricReading], specs: list[MetricSpec]
) -> GoalStatus:
    """Aggregate per-metric progress into an overall goal completion ratio."""
    by_name = {spec.name: spec for spec in specs}
    progress: dict[str, float] = {}
    gaps: dict[str, float] = {}
    for reading in metrics:
        spec = by_name.get(reading.name)
        if spec is None:
            continue
        progress[reading.name] = round(spec.progress(reading.value), 4)
        gaps[reading.name] = round(spec.target - reading.value, 4)
    overall = round(sum(progress.values()) / len(progress), 4) if progress else 0.0
    return GoalStatus(
        progress=overall,
        distance=round(1.0 - overall, 4),
        metric_progress=progress,
        metric_gaps=gaps,
    )


def baseline_state(
    branch: BranchProfile, specs: list[MetricSpec], background: str
) -> BranchStateUpdate:
    readings = [
        MetricReading(
            name=spec.name, value=spec.baseline, previous=spec.baseline, unit=spec.unit
        )
        for spec in specs
    ]
    return BranchStateUpdate(
        branch_id=branch.branch_id,
        narrative=background,
        metrics=readings,
        goal_status=compute_goal_status(readings, specs),
        confidence=1.0,
    )


async def predict_state(
    llm: LLMClient,
    *,
    branch: BranchProfile,
    event: Event,
    event_index: int,
    total_events: int,
    strategy: StrategyOption,
    previous: BranchStateUpdate,
    specs: list[MetricSpec],
    goal: TargetGoal,
    context: str,
    model: str | None = None,
) -> BranchStateUpdate:
    previous_by_name = {m.name: m.value for m in previous.metrics}
    payload = {
        "final_goal": goal.description,
        "branch": {
            "label": branch.label,
            "rationality": branch.rationality.value,
            "persona": branch.persona,
        },
        "event": {
            "index": event_index,
            "total": total_events,
            "description": event.description,
            "impact": event.impact,
            "severity": event.severity,
            "is_black_swan": event.is_black_swan,
        },
        "chosen_strategy": {
            "title": strategy.title,
            "detail": strategy.detail,
            "rationale": strategy.rationale,
            "rationality": strategy.rationality.value,
        },
        "state_before": {
            "narrative": previous.narrative,
            "metrics": previous_by_name,
        },
        "metrics_to_predict": [spec.model_dump() for spec in specs],
        "knowledge_base_retrieval": context[:6000] or "(检索结果为空)",
    }
    user = (
        "预测执行该策略之后这条平行世界的新状态。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    try:
        prediction = await llm.structured_complete(
            STATE_SYSTEM, user, StatePrediction, model=model
        )
    except Exception as exc:
        logger.warning(
            "State prediction failed (%s, event %d): %s", branch.branch_id, event_index, exc
        )
        prediction = StatePrediction(
            narrative=f"{strategy.title} 已执行，但本轮未能得到可靠的状态预测。",
            confidence=0.2,
            success=False,
        )

    predicted = {p.name: p for p in prediction.metrics if p.name}
    readings: list[MetricReading] = []
    for spec in specs:
        hit = predicted.get(spec.name)
        prev = previous_by_name.get(spec.name, spec.baseline)
        readings.append(
            MetricReading(
                name=spec.name,
                value=float(hit.value) if hit else prev,
                previous=prev,
                unit=spec.unit,
                reason=hit.reason.strip() if hit else "",
            )
        )

    return BranchStateUpdate(
        branch_id=branch.branch_id,
        narrative=prediction.narrative.strip(),
        metrics=readings,
        risks=[r.strip() for r in prediction.risks if r.strip()][:3],
        side_effects=[s.strip() for s in prediction.side_effects if s.strip()][:3],
        confidence=max(0.0, min(1.0, prediction.confidence)),
        success=prediction.success,
        goal_status=compute_goal_status(readings, specs),
    )


def render_state_snapshot(
    *,
    branch: BranchProfile,
    goal: TargetGoal,
    event: Event,
    event_index: int,
    strategy: StrategyOption,
    state: BranchStateUpdate,
) -> str:
    """Markdown snapshot fed back into the branch KB (kept small on purpose)."""
    lines = [
        f"# 当前状态快照（{branch.label}）",
        "",
        f"- 推演目标：{goal.description}",
        f"- 最近事件（第 {event_index} 个）：{event.description}",
        f"- 采取的应对：{strategy.title}",
    ]
    if strategy.detail:
        lines.append(f"- 具体做法：{strategy.detail}")
    lines += ["", "## 关键指标", ""]
    for reading in state.metrics:
        unit = f" {reading.unit}" if reading.unit else ""
        delta = reading.value - reading.previous
        arrow = "上升" if delta > 0 else ("下降" if delta < 0 else "持平")
        lines.append(
            f"- {reading.name}：{reading.value:g}{unit}"
            f"（此前 {reading.previous:g}{unit}，{arrow} {abs(delta):g}）"
            + (f"。原因：{reading.reason}" if reading.reason else "")
        )
    lines += ["", "## 当前处境", "", state.narrative or "（无描述）"]
    if state.risks:
        lines += ["", "## 需要注意的风险", ""] + [f"- {r}" for r in state.risks]
    if state.side_effects:
        lines += ["", "## 该做法的副作用", ""] + [f"- {s}" for s in state.side_effects]
    lines += [
        "",
        f"目标进度：{state.goal_status.progress:.0%}。",
        "本快照描述的是**当前**状态，取代之前的状态记录。",
    ]
    return "\n".join(lines)


def render_baseline_snapshot(
    *, goal: TargetGoal, background: str, specs: list[MetricSpec], constraints: list[str]
) -> str:
    lines = [
        "# 推演起点",
        "",
        f"- 最终目标：{goal.description}",
        "",
        "## 起始指标",
        "",
    ]
    for spec in specs:
        unit = f" {spec.unit}" if spec.unit else ""
        lines.append(f"- {spec.name}：当前 {spec.baseline:g}{unit}，目标 {spec.target:g}{unit}")
    if background:
        lines += ["", "## 起始处境", "", background]
    if constraints:
        lines += ["", "## 约束", ""] + [f"- {c}" for c in constraints]
    return "\n".join(lines)
