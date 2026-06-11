import json
import logging
import uuid

from prds.llm.client import LLMClient
from prds.llm.schemas import EventPlan, PlannedEventDraft
from prds.models.domain import (
    BackgroundReport,
    CurrentState,
    Event,
    EventCategory,
    OntologyGraph,
    SimulationConfig,
    TargetGoal,
    WorldBackground,
)

logger = logging.getLogger(__name__)

MIN_EVENT_PROBABILITY = 0.4

EVENT_PLAN_SYSTEM = """You are a simulation event planner for a strategic decision system.

Your job is to produce an ORDERED list of exogenous events that are LIKELY given the
industry report, user's current state, and goal. Events are the ONLY driver of the
simulation — there is no separate time grid or period schedule.

Rules:
1. Read the industry report and infer which external shocks / shifts are probable.
2. Order events causally: earlier events should plausibly precede later ones.
3. Include ONLY events grounded in the report, risks, opportunities, or ontology.
4. Exogenous only (macro, market, org, resource) — never the player's own decisions.
5. `probability` reflects report-backed likelihood (typical 0.6–0.9; rare 0.1–0.35).
6. `rationale`: one Chinese sentence citing WHY the report makes this likely at this point.
7. `description`: one concise Chinese sentence of what happens and why it matters.
8. Use category values exactly: macro, market, org, resource.
9. event_type: short snake_case identifier.
10. Do NOT pad the list — high-signal events only.
11. Return valid JSON only."""


def _build_planner_payload(
    current_state: CurrentState,
    goal: TargetGoal,
    config: SimulationConfig,
    *,
    world_background: WorldBackground | None = None,
    ontology: OntologyGraph | None = None,
    report: BackgroundReport | None = None,
) -> dict:
    payload = {
        "max_events": config.max_events,
        "planning_mode": "report_driven_event_sequence",
        "current_state": {
            "background": current_state.background,
            "resources": current_state.resources.model_dump(),
            "constraints": current_state.constraints,
            "risks": current_state.risks,
            "opportunities": current_state.opportunities,
            "organization": current_state.organization,
            "market_info": current_state.market_info,
            "financials": current_state.financials,
        },
        "goal": {
            "description": goal.description,
            "success_metrics": goal.success_metrics,
        },
    }
    if world_background:
        payload["world_background"] = {
            "summary": world_background.summary,
            "risks": world_background.risks,
            "opportunities": world_background.opportunities,
            "community_summaries": world_background.community_summaries[:5],
        }
    if ontology:
        payload["ontology"] = {
            "risks": ontology.risks,
            "opportunities": ontology.opportunities,
            "constraints": ontology.constraints,
            "entity_names": [e.name for e in ontology.entities[:15]],
        }
    if report and (report.report or report.key_findings):
        payload["industry_report"] = {
            "key_findings": report.key_findings[:10],
            "excerpt": report.report[:3500],
            "provider": report.provider,
        }
    else:
        payload["industry_report"] = {
            "note": "No formal report — infer from current_state and world_background only.",
        }
    return payload


def _draft_to_event(draft: PlannedEventDraft, index: int) -> Event:
    desc = draft.description.strip()
    if draft.rationale and draft.rationale not in desc:
        desc = f"{desc}（依据：{draft.rationale.strip()}）"
    return Event(
        event_id=f"evt_{index}_{uuid.uuid4().hex[:8]}",
        event_type=draft.event_type.strip().replace(" ", "_").lower(),
        category=draft.category,
        impact=max(-1.0, min(1.0, draft.impact)),
        probability=max(0.0, min(1.0, draft.probability)),
        severity=max(0.1, min(1.0, draft.severity)),
        description=desc,
    )


def plan_to_events(
    plan: EventPlan,
    *,
    min_probability: float = MIN_EVENT_PROBABILITY,
    max_events: int = 24,
) -> list[Event]:
    events: list[Event] = []
    for idx, draft in enumerate(plan.events, start=1):
        if draft.probability < min_probability:
            continue
        events.append(_draft_to_event(draft, idx))
        if len(events) >= max_events:
            break
    return events


async def plan_events(
    llm: LLMClient,
    current_state: CurrentState,
    goal: TargetGoal,
    config: SimulationConfig,
    *,
    world_background: WorldBackground | None = None,
    ontology: OntologyGraph | None = None,
    report: BackgroundReport | None = None,
) -> list[Event]:
    """Build an ordered list of report-driven exogenous events."""
    payload = _build_planner_payload(
        current_state,
        goal,
        config,
        world_background=world_background,
        ontology=ontology,
        report=report,
    )
    user = (
        "Based on the industry report and user context below, produce an ORDERED list of "
        f"exogenous events (max {payload['max_events']}). Each event triggers one decision round.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    plan = await llm.structured_complete(
        EVENT_PLAN_SYSTEM,
        user,
        EventPlan,
        model=llm.analysis_model,
    )
    events = plan_to_events(plan, max_events=config.max_events)
    if not events:
        raise ValueError("LLM returned no high-probability events")
    logger.info(
        "Report-driven event plan: %d events (arc: %s)",
        len(events),
        (plan.narrative_arc or "")[:80],
    )
    return events
