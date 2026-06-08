import json
import logging
import uuid
from collections import defaultdict

from prds.llm.client import LLMClient
from prds.llm.schemas import EventTimelinePlan, PlannedEventDraft
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

EVENT_TIMELINE_SYSTEM = """You are a simulation event planner for a strategic decision system.
Given the user's situation, goal, and an industry background report, design a timeline of the
external events that are CHARACTERISTIC and HIGH-PROBABILITY for THIS domain — not random shocks.

What "domain-likely" means:
- Prefer events that experienced practitioners in this industry routinely encounter
  (seasonal demand swings, platform/policy rule changes, supplier price moves, hiring/turnover,
  competitive promotions, funding-window shifts, regulatory checks, etc.).
- Ground every event in the background report and the listed risks/opportunities/entities.
- Reserve rare black-swan events for at most one low-probability entry, if any.
- `probability` should reflect real likelihood in this domain: recurring/typical events get
  HIGH probability (0.6-0.9); unusual events get LOW probability (0.1-0.3).

Realism:
- Most organizations face headwinds; do not assume a smooth path to the goal.
- Early periods: validation friction, demand uncertainty, onboarding/setup issues.
- Mid periods: competition, churn, funding windows, talent/supplier dynamics.
- Late periods: consolidation, macro/seasonal shifts, deadline pressure.

Rules:
- Events are exogenous (macro, market, org, resource) — not the player's own decisions.
- Spread events across the full timeline; reflect the domain's natural cadence/seasonality.
- Use category values exactly: macro, market, org, resource.
- event_type: short snake_case identifier (e.g. seasonal_demand_peak, platform_fee_increase).
- impact: signed effect direction/strength in [-1, 1]; negative = adverse.
- severity: how disruptive in [0.1, 1.0].
- probability: real-world likelihood in this domain in [0, 1] (typical events are high).
- description: one concise Chinese sentence explaining what happens and why it matters.
- Do not assign more than 3 events to the same period unless the horizon is very short.
- Return valid JSON only."""


def target_event_count(periods: int) -> int:
    return min(50, max(8, periods // 4))


def _build_planner_payload(
    current_state: CurrentState,
    goal: TargetGoal,
    config: SimulationConfig,
    *,
    world_background: WorldBackground | None = None,
    ontology: OntologyGraph | None = None,
    report: BackgroundReport | None = None,
) -> dict:
    time_label = f"{config.period_time_length} {config.period_time_unit}(s) per period"
    payload = {
        "simulation_horizon": {
            "total_periods": config.periods,
            "period_time_unit": config.period_time_unit,
            "period_time_length": config.period_time_length,
            "time_label": time_label,
            "start_date": config.simulation_start_date,
        },
        "target_event_count": target_event_count(config.periods),
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
            "deadline_periods": goal.deadline_periods or config.periods,
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
            "key_findings": report.key_findings[:8],
            "excerpt": report.report[:2500],
        }
    return payload


def _draft_to_event(draft: PlannedEventDraft, period: int) -> Event:
    return Event(
        event_id=f"evt_{period}_{uuid.uuid4().hex[:8]}",
        event_type=draft.event_type.strip().replace(" ", "_").lower(),
        category=draft.category,
        impact=max(-1.0, min(1.0, draft.impact)),
        probability=max(0.0, min(1.0, draft.probability)),
        severity=max(0.1, min(1.0, draft.severity)),
        description=draft.description.strip(),
    )


def plan_to_calendar(plan: EventTimelinePlan, total_periods: int) -> dict[int, list[Event]]:
    calendar: dict[int, list[Event]] = defaultdict(list)
    for draft in plan.events:
        period = max(1, min(total_periods, draft.period))
        calendar[period].append(_draft_to_event(draft, period))
    return dict(calendar)


async def plan_event_timeline(
    llm: LLMClient,
    current_state: CurrentState,
    goal: TargetGoal,
    config: SimulationConfig,
    *,
    world_background: WorldBackground | None = None,
    ontology: OntologyGraph | None = None,
    report: BackgroundReport | None = None,
) -> dict[int, list[Event]]:
    """Build a period-indexed event calendar from current state and goal."""
    payload = _build_planner_payload(
        current_state,
        goal,
        config,
        world_background=world_background,
        ontology=ontology,
        report=report,
    )
    user = (
        "Plan exogenous simulation events for the horizon below. "
        f"Return roughly {payload['target_event_count']} events.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    plan = await llm.structured_complete(
        EVENT_TIMELINE_SYSTEM,
        user,
        EventTimelinePlan,
        model=llm.analysis_model,
    )
    calendar = plan_to_calendar(plan, config.periods)
    if not calendar:
        raise ValueError("LLM returned empty event timeline")
    logger.info(
        "Planned %d LLM events across %d periods (arc: %s)",
        sum(len(v) for v in calendar.values()),
        len(calendar),
        (plan.narrative_arc or "")[:80],
    )
    return calendar
