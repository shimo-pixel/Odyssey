"""Post-run analysis: ranking, spread, counterfactuals and roadmap."""

from __future__ import annotations

import json
import logging
import statistics

from pydantic import BaseModel, Field

from prds.kbsim.prompts import SYNTHESIS_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import (
    BranchProfile,
    BranchStateUpdate,
    BranchSummary,
    CounterfactualComparison,
    MetricBand,
    MetricSpec,
    OutcomeDistribution,
    StateTraceEntry,
    StrategySynthesis,
    TargetGoal,
)

logger = logging.getLogger(__name__)


class CounterfactualDraft(BaseModel):
    event_index: int = 1
    decision_a: str = ""
    outcome_a: str = ""
    decision_b: str = ""
    outcome_b: str = ""
    difference: str = ""


class SynthesisDraft(BaseModel):
    principles: list[str] = Field(default_factory=list)
    key_turning_points: list[str] = Field(default_factory=list)
    success_factors: list[str] = Field(default_factory=list)
    failure_avoidance_factors: list[str] = Field(default_factory=list)
    recommended_roadmap: list[str] = Field(default_factory=list)
    counterfactuals: list[CounterfactualDraft] = Field(default_factory=list)


def rank_branches(
    branches: list[BranchProfile], states: dict[str, BranchStateUpdate]
) -> list[BranchSummary]:
    """Rank branches by final goal progress (ties broken by confidence)."""

    def sort_key(branch: BranchProfile) -> tuple[float, float]:
        state = states.get(branch.branch_id)
        if state is None:
            return (0.0, 0.0)
        return (state.goal_status.progress, state.confidence)

    ordered = sorted(branches, key=sort_key, reverse=True)
    summaries: list[BranchSummary] = []
    for rank, branch in enumerate(ordered, start=1):
        state = states.get(branch.branch_id)
        summaries.append(
            BranchSummary(
                branch_id=branch.branch_id,
                label=branch.label,
                rationality=branch.rationality,
                persona=branch.persona,
                rank=rank,
                final_progress=state.goal_status.progress if state else 0.0,
                final_metrics=(
                    {m.name: m.value for m in state.metrics} if state else {}
                ),
                final_narrative=state.narrative if state else "",
                workspaces=list(branch.workspaces),
            )
        )
    return summaries


def _band(metric: str, label: str, values: list[float]) -> MetricBand:
    if not values:
        return MetricBand(metric=metric, label=label)
    ordered = sorted(values)

    def pct(p: float) -> float:
        if len(ordered) == 1:
            return round(ordered[0], 4)
        position = p * (len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        weight = position - low
        return round(ordered[low] * (1 - weight) + ordered[high] * weight, 4)

    return MetricBand(
        metric=metric,
        label=label,
        p10=pct(0.1),
        p25=pct(0.25),
        median=round(statistics.median(ordered), 4),
        p75=pct(0.75),
        p90=pct(0.9),
        mean=round(statistics.fmean(ordered), 4),
    )


def build_distribution(
    states: dict[str, BranchStateUpdate], specs: list[MetricSpec]
) -> OutcomeDistribution:
    progresses = [s.goal_status.progress for s in states.values()]
    if not progresses:
        return OutcomeDistribution()
    bands = []
    for spec in specs:
        values = [
            m.value for s in states.values() for m in s.metrics if m.name == spec.name
        ]
        if values:
            bands.append(_band(spec.name, spec.unit, values))
    return OutcomeDistribution(
        sample_size=len(progresses),
        success_rate=round(
            sum(1 for p in progresses if p >= 0.9) / len(progresses), 4
        ),
        near_success_rate=round(
            sum(1 for p in progresses if p >= 0.6) / len(progresses), 4
        ),
        goal_progress=_band("goal_progress", "目标进度", progresses),
        metric_bands=bands,
    )


def _fallback_counterfactuals(
    trace: list[StateTraceEntry], summaries: list[BranchSummary]
) -> list[CounterfactualComparison]:
    """Contrast best and worst branch at the events where they diverged most."""
    if len(summaries) < 2:
        return []
    best, worst = summaries[0].branch_id, summaries[-1].branch_id
    by_event: dict[int, dict[str, StateTraceEntry]] = {}
    for entry in trace:
        by_event.setdefault(entry.event_index, {})[entry.branch_id] = entry

    scored: list[tuple[float, int]] = []
    for index, entries in by_event.items():
        if best in entries and worst in entries:
            gap = abs(
                entries[best].state.goal_status.progress
                - entries[worst].state.goal_status.progress
            )
            scored.append((gap, index))
    scored.sort(reverse=True)

    out: list[CounterfactualComparison] = []
    for gap, index in scored[:3]:
        entries = by_event[index]
        out.append(
            CounterfactualComparison(
                event_index=index,
                decision_a=entries[best].strategy.title,
                outcome_a=entries[best].state.narrative[:280],
                decision_b=entries[worst].strategy.title,
                outcome_b=entries[worst].state.narrative[:280],
                difference=f"目标进度相差 {gap:.0%}",
            )
        )
    return out


async def build_synthesis(
    llm: LLMClient,
    *,
    goal: TargetGoal,
    trace: list[StateTraceEntry],
    summaries: list[BranchSummary],
    specs: list[MetricSpec],
    model: str | None = None,
) -> tuple[StrategySynthesis, list[CounterfactualComparison]]:
    payload = {
        "final_goal": goal.description,
        "metrics": [spec.model_dump() for spec in specs],
        "branch_ranking": [
            {
                "branch_id": s.branch_id,
                "label": s.label,
                "rationality": s.rationality.value,
                "rank": s.rank,
                "final_progress": s.final_progress,
                "final_metrics": s.final_metrics,
            }
            for s in summaries
        ],
        "trace": [
            {
                "event_index": e.event_index,
                "events": [event.model_dump() for event in e.events],
                "branch_id": e.branch_id,
                "strategy": e.strategy.title,
                "rationality": e.strategy.rationality.value,
                "progress": e.state.goal_status.progress,
                "metrics": {m.name: m.value for m in e.state.metrics},
                "state": e.state.narrative[:200],
            }
            for e in trace
        ],
    }
    user = "基于完整推演轨迹做复盘。\n\n" + json.dumps(
        payload, ensure_ascii=False, indent=2
    )

    draft = await llm.structured_complete(SYNTHESIS_SYSTEM, user, SynthesisDraft, model=model)
    if not draft.recommended_roadmap or not draft.principles:
        raise ValueError("Synthesis requires principles and roadmap")

    counterfactuals = [
        CounterfactualComparison(
            event_index=max(1, c.event_index),
            decision_a=c.decision_a,
            outcome_a=c.outcome_a,
            decision_b=c.decision_b,
            outcome_b=c.outcome_b,
            difference=c.difference,
        )
        for c in draft.counterfactuals
        if c.decision_a.strip() and c.decision_b.strip()
    ]
    if not counterfactuals:
        counterfactuals = _fallback_counterfactuals(trace, summaries)

    synthesis = StrategySynthesis(
        principles=draft.principles,
        key_turning_points=draft.key_turning_points,
        success_factors=draft.success_factors,
        failure_avoidance_factors=draft.failure_avoidance_factors,
        recommended_roadmap=draft.recommended_roadmap,
    )
    return synthesis, counterfactuals
