"""Grounded event planning: derive a restrained, evidence-backed timeline.

The goal is the prompt; the knowledge base is the only allowed source of facts.
Long timelines additionally receive a few low-probability, high-impact shocks
("black swans") placed deterministically from the run seed.
"""

from __future__ import annotations

import json
import logging
import math
import random
import uuid

from pydantic import BaseModel, Field

from prds.config import Settings
from prds.kbsim.intake import IntakeBrief
from prds.kbsim.prompts import BLACK_SWAN_SYSTEM, EVENT_PLAN_SYSTEM
from prds.llm.client import LLMClient
from prds.models.domain import Event, EventCategory, SimulationConfig, TargetGoal

logger = logging.getLogger(__name__)

MIN_EVENT_PROBABILITY = 0.35
_CATEGORY_VALUES = {c.value for c in EventCategory}


class EventDraft(BaseModel):
    event_type: str = Field(default="situation_shift")
    category: str = Field(default="market")
    description: str = Field(default="", description="独立于分支决策的客观处境变化；只写发生了什么，不写应对策略、建议或策略执行结果")
    impact: float = 0.0
    probability: float = 0.5
    severity: float = 0.5
    evidence: list[str] = Field(default_factory=list)


class EventPlan(BaseModel):
    events: list[EventDraft] = Field(default_factory=list)
    timeline_note: str = ""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _slug(text: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text.strip().lower())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:48] or fallback


def _draft_to_event(draft: EventDraft, index: int, *, black_swan: bool = False) -> Event:
    category = draft.category if draft.category in _CATEGORY_VALUES else EventCategory.MARKET.value
    return Event(
        event_id=f"evt_{index:03d}_{uuid.uuid4().hex[:6]}",
        event_type=_slug(draft.event_type, f"event_{index}"),
        category=EventCategory(category),
        impact=_clamp(draft.impact, -1.0, 1.0),
        probability=_clamp(draft.probability, 0.0, 1.0),
        severity=_clamp(draft.severity, 0.0, 1.0),
        description=draft.description.strip(),
        evidence=[e.strip() for e in draft.evidence if e and e.strip()][:3],
        is_black_swan=black_swan,
    )


def black_swan_quota(total_events: int, settings: Settings) -> int:
    """How many black swans a timeline of this length should carry."""
    if total_events < settings.prds_kbsim_black_swan_min_events:
        return 0
    quota = int(round(total_events * settings.prds_kbsim_black_swan_ratio))
    return max(1, min(settings.prds_kbsim_max_black_swans, quota))


def black_swan_slots(total_events: int, quota: int, seed: int | None) -> list[int]:
    """Deterministic 1-based positions for black swans, in the back 60% of the run."""
    if quota <= 0 or total_events <= 0:
        return []
    first = max(2, int(math.ceil(total_events * 0.4)))
    candidates = list(range(first, total_events + 1))
    if not candidates:
        return []
    rng = random.Random(seed if seed is not None else 0)
    quota = min(quota, len(candidates))
    return sorted(rng.sample(candidates, quota))


def _plan_payload(
    *,
    goal: TargetGoal,
    brief: IntakeBrief,
    kb_context: str,
    count: int,
) -> str:
    payload = {
        "final_goal": goal.description,
        "background": brief.background,
        "constraints": brief.constraints,
        "risks": brief.risks,
        "opportunities": brief.opportunities,
        "metrics_being_tracked": [spec.model_dump() for spec in brief.metric_specs],
        "event_count_required": count,
        "knowledge_base_retrieval": kb_context[:8000] or "(知识库为空)",
    }
    return (
        f"请基于知识库构造 {count} 个按时间推进的事件。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


async def plan_events(
    llm: LLMClient,
    *,
    goal: TargetGoal,
    brief: IntakeBrief,
    config: SimulationConfig,
    kb_context: str,
    settings: Settings,
) -> list[Event]:
    """Plan the event timeline, injecting black swans on long runs."""
    total = config.max_events
    swan_quota = black_swan_quota(total, settings)
    normal_needed = total - swan_quota

    plan = await llm.structured_complete(
        EVENT_PLAN_SYSTEM,
        _plan_payload(goal=goal, brief=brief, kb_context=kb_context, count=normal_needed),
        EventPlan,
        model=llm.analysis_model,
    )
    drafts = [
        d
        for d in plan.events
        if d.description.strip() and d.probability >= MIN_EVENT_PROBABILITY
    ][:normal_needed]
    if not drafts:
        raise ValueError(
            "事件规划未产出任何可用事件。请确认知识库中有与目标相关的资料，或稍后重试。"
        )

    swan_drafts: list[EventDraft] = []
    if swan_quota:
        swan_plan = await llm.structured_complete(
            BLACK_SWAN_SYSTEM,
            _plan_payload(
                goal=goal, brief=brief, kb_context=kb_context, count=swan_quota
            ),
            EventPlan,
            model=llm.analysis_model,
        )
        swan_drafts = [d for d in swan_plan.events if d.description.strip()][:swan_quota]

    slots = set(black_swan_slots(len(drafts) + len(swan_drafts), len(swan_drafts), config.seed))
    events: list[Event] = []
    normal_iter = iter(drafts)
    swan_iter = iter(swan_drafts)
    position = 0
    total_planned = len(drafts) + len(swan_drafts)
    while len(events) < total_planned:
        position += 1
        if position in slots:
            draft = next(swan_iter, None)
            if draft is not None:
                draft.probability = _clamp(draft.probability or 0.12, 0.05, 0.2)
                draft.severity = max(draft.severity, 0.7)
                events.append(_draft_to_event(draft, position, black_swan=True))
                continue
        draft = next(normal_iter, None)
        if draft is None:
            draft = next(swan_iter, None)
            if draft is None:
                break
            events.append(_draft_to_event(draft, position, black_swan=True))
            continue
        events.append(_draft_to_event(draft, position))

    logger.info(
        "Planned %d events (%d black swans) for goal=%r",
        len(events),
        sum(1 for e in events if e.is_black_swan),
        goal.description[:60],
    )
    return events


def event_keywords(event: Event, brief: IntakeBrief) -> tuple[list[str], list[str]]:
    """Keywords reused across every branch query for this event.

    Supplying these lets LightRAG skip its own keyword-extraction LLM call on
    each of the N per-branch retrievals.
    """
    high = [event.event_type.replace("_", " ")]
    high += [spec.name for spec in brief.metric_specs][:3]
    low = [e[:40] for e in event.evidence][:3]
    if event.description:
        low.append(event.description[:60])
    return (
        [k for k in dict.fromkeys(h.strip() for h in high) if k],
        [k for k in dict.fromkeys(l.strip() for l in low) if k],
    )
