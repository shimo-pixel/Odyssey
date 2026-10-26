"""Strategy generation: one batched call produces every branch's response.

Batching keeps the N strategies distinct (the model sees them all at once) and
turns N LLM calls per event into one.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from prds.kbsim.prompts import STRATEGY_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import (
    BranchProfile,
    BranchStateUpdate,
    Event,
    MetricSpec,
    Rationality,
    StrategyOption,
    TargetGoal,
)

logger = logging.getLogger(__name__)


class StrategyDraft(BaseModel):
    branch_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    action_label: str = ""
    detail: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    rationality: str = "rational"


class StrategyBatch(BaseModel):
    strategies: list[StrategyDraft] = Field(default_factory=list)


async def generate_strategies(
    llm: LLMClient,
    *,
    event: Event,
    event_index: int,
    total_events: int,
    goal: TargetGoal,
    branches: list[BranchProfile],
    metric_specs: list[MetricSpec],
    contexts: dict[str, str],
    last_states: dict[str, BranchStateUpdate],
    model: str | None = None,
    extra_events: list[Event] | None = None,
) -> dict[str, StrategyOption]:
    """Produce exactly one strategy per branch, honouring each branch's profile."""
    payload = {
        "final_goal": goal.description,
        "events": [e.model_dump() for e in [event, *(extra_events or [])]],
        "event": {
            "index": event_index,
            "total": total_events,
            "type": event.event_type,
            "description": event.description,
            "impact": event.impact,
            "severity": event.severity,
            "is_black_swan": event.is_black_swan,
            "evidence": event.evidence,
        },
        "metrics_being_tracked": [spec.model_dump() for spec in metric_specs],
        "branches": [
            {
                "branch_id": b.branch_id,
                "label": b.label,
                "rationality": b.rationality.value,
                "persona": b.persona,
                "current_state": (
                    last_states[b.branch_id].narrative
                    if b.branch_id in last_states
                    else "(尚未发生变化，处于初始状态)"
                ),
                "knowledge_base_retrieval": (contexts.get(b.branch_id) or "")[:2500],
            }
            for b in branches
        ],
    }
    user = (
        f"为下面 {len(branches)} 条平行世界各生成 1 条互不重复的应对策略。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    from prds.simulation.errors import SimulationFailure
    try:
        batch = await llm.structured_complete(STRATEGY_SYSTEM, user, StrategyBatch, model=model)
    except Exception as exc:
        raise SimulationFailure("strategy", event_index=event_index) from exc
    expected = {b.branch_id for b in branches}
    if len(batch.strategies) != len(branches) or {d.branch_id for d in batch.strategies} != expected:
        raise SimulationFailure("strategy", event_index=event_index, code="invalid_output")
    by_id = {d.branch_id: d for d in batch.strategies}
    result: dict[str, StrategyOption] = {}
    for branch in branches:
        draft = by_id[branch.branch_id]
        if not all(v.strip() for v in (draft.title, draft.detail, draft.rationale)):
            from prds.simulation.errors import SimulationFailure
            raise SimulationFailure("strategy", branch_id=branch.branch_id, event_index=event_index,
                                    code="invalid_output")
        result[branch.branch_id] = StrategyOption(
            branch_id=branch.branch_id,
            title=draft.title.strip() or draft.detail.strip()[:60],
            action_label=(draft.action_label.strip() or draft.title.strip())[:12],
            detail=draft.detail.strip(),
            rationale=draft.rationale.strip(),
            # The branch profile is authoritative: it guarantees the
            # rational-majority / irrational-minority mix.
            rationality=branch.rationality,
        )
    return result


def rationality_counts(branches: list[BranchProfile]) -> tuple[int, int]:
    rational = sum(1 for b in branches if b.rationality is Rationality.RATIONAL)
    return rational, len(branches) - rational
