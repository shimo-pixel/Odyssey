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
    branch_id: str = ""
    title: str = ""
    action_label: str = ""
    detail: str = ""
    rationale: str = ""
    rationality: str = "rational"


class StrategyBatch(BaseModel):
    strategies: list[StrategyDraft] = Field(default_factory=list)


def _fallback_strategy(branch: BranchProfile, event: Event) -> StrategyOption:
    return StrategyOption(
        branch_id=branch.branch_id,
        title=f"按{branch.label}的既有方式应对：{event.description[:40]}",
        action_label="维持现状",
        detail="沿用当前做法，观察事件后续影响。",
        rationale="策略生成失败，退回到保守的观察式应对。",
        rationality=branch.rationality,
    )


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
) -> dict[str, StrategyOption]:
    """Produce exactly one strategy per branch, honouring each branch's profile."""
    payload = {
        "final_goal": goal.description,
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

    drafts: list[StrategyDraft] = []
    try:
        batch = await llm.structured_complete(
            STRATEGY_SYSTEM, user, StrategyBatch, model=model
        )
        drafts = batch.strategies
    except Exception as exc:
        logger.warning("Strategy generation failed for event %d: %s", event_index, exc)

    by_id = {d.branch_id: d for d in drafts if d.branch_id}
    leftovers = [d for d in drafts if d.branch_id not in {b.branch_id for b in branches}]

    result: dict[str, StrategyOption] = {}
    for position, branch in enumerate(branches):
        draft = by_id.get(branch.branch_id)
        if draft is None and position < len(leftovers):
            draft = leftovers[position]
        if draft is None or not (draft.title or draft.detail).strip():
            result[branch.branch_id] = _fallback_strategy(branch, event)
            continue
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
