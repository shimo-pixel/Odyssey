"""State prediction: retrieval-augmented generation of each branch's next state.

The prediction is written back into the branch's own knowledge base as a
snapshot document, so the next event's retrieval sees the evolved world.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field, ConfigDict, create_model, model_validator

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
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(..., min_length=1)
    value: float
    reason: str = Field(..., min_length=1)


class StatePrediction(BaseModel):
    narrative: str = Field(..., min_length=1)
    metrics: list[MetricPrediction] = Field(..., min_length=1)
    risks: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)
    success: bool


def compute_goal_status(
    metrics: list[MetricReading], specs: list[MetricSpec]
) -> GoalStatus:
    """Aggregate per-metric progress into an overall goal completion ratio."""
    by_name = {spec.name: spec for spec in specs}
    progress: dict[str, float] = {}
    for reading in metrics:
        spec = by_name.get(reading.name)
        if spec is None:
            continue
        progress[reading.name] = round(spec.progress(reading.value), 4)
    overall = round(sum(progress.values()) / len(progress), 4) if progress else 0.0
    return GoalStatus(
        progress=overall,
        metric_progress=progress,
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
    extra_events: list[Event] | None = None,
) -> BranchStateUpdate:
    previous_by_name = {m.name: m.value for m in previous.metrics}
    payload = {
        "final_goal": goal.description,
        "events": [e.model_dump() for e in [event, *(extra_events or [])]],
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
        "metrics 必须逐一包含 metrics_to_predict 中的全部指标，name 原样复制，不得遗漏、重复或改名；"
        "narrative 和每项 reason 不得为空白。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    from prds.simulation.errors import SimulationFailure

    # Validate against this run's metrics inside structured_complete, so an
    # otherwise valid JSON response can be corrected by its retry loop.
    def require_complete_state(prediction):
        names = [p.name for p in prediction.metrics]
        if len(names) != len(specs) or set(names) != {s.name for s in specs}:
            raise ValueError("Return every requested metric exactly once using its exact name")
        if not prediction.narrative.strip() or any(not p.reason.strip() for p in prediction.metrics):
            raise ValueError("Narrative and metric reasons must contain text")
        return prediction

    required_prediction = create_model(
        "StatePrediction",
        __base__=StatePrediction,
        __validators__={"require_complete_state": model_validator(mode="after")(require_complete_state)},
    )

    try:
        prediction = await llm.structured_complete(STATE_SYSTEM, user, required_prediction, model=model)
        predicted = {p.name: p for p in prediction.metrics if p.name}
        if not prediction.narrative.strip() or len(prediction.metrics) != len(specs) or set(predicted) != {s.name for s in specs}:
            raise ValueError("All metric predictions and narrative are required")
        if any(not p.reason.strip() for p in prediction.metrics):
            raise ValueError("Metric prediction reasons are required")
    except Exception as exc:
        # Only exception types are safe to log: provider messages may contain
        # credentials, prompt contents, or other private data.
        cause = exc.__cause__
        logger.error(
            "State prediction failed: branch=%s event=%s error_type=%s cause_type=%s",
            branch.branch_id, event_index, type(exc).__name__,
            type(cause).__name__ if cause else "none",
        )
        raise SimulationFailure("prediction", branch_id=branch.branch_id, event_index=event_index) from exc

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
    extra_events: list[Event] | None = None,
) -> str:
    """Markdown snapshot fed back into the branch KB (kept small on purpose)."""
    lines = [
        f"# 当前状态快照（{branch.label}）",
        "",
        f"- 推演目标：{goal.description}",
        f"- 最近事件（第 {event_index} 个，{event.event_id}）：{event.description}（impact={event.impact}, severity={event.severity}）",
        f"- 采取的应对：{strategy.title}",
    ]
    for injected in extra_events or []:
        lines.append(f"- 注入事件 {injected.event_id}：{injected.description}（impact={injected.impact}, severity={injected.severity}）")
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
