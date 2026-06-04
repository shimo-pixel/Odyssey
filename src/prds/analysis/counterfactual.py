import json

from prds.llm.client import LLMClient
from prds.llm.schemas import CounterfactualBatch
from prds.models.domain import AgentState, CounterfactualComparison


COUNTERFACTUAL_SYSTEM = """You are a counterfactual analysis engine.
Given a champion agent's decision timeline, identify 2-4 key decision nodes
and compare the actual decision vs a plausible alternative.
Return JSON: {"comparisons": [{"period": 1, "decision_a": "...", "outcome_a": "...", "decision_b": "...", "outcome_b": "...", "difference": "..."}]}"""


def _identify_key_periods(champion: AgentState) -> list[int]:
    """Heuristic: periods with large resource changes or action shifts."""
    key_periods: list[int] = []
    for entry in champion.timeline:
        delta = abs(entry.result.resource_change.cash) + abs(entry.result.resource_change.users) * 0.001
        if delta > 5 or entry.action.value in ("fundraise", "strategic_pivot", "acquisition"):
            key_periods.append(entry.period)
    if not key_periods and champion.timeline:
        key_periods = [champion.timeline[0].period, champion.timeline[-1].period]
    return sorted(set(key_periods))[:4]


def _fallback_counterfactuals(champion: AgentState) -> list[CounterfactualComparison]:
    comparisons: list[CounterfactualComparison] = []
    for entry in champion.timeline[:3]:
        comparisons.append(
            CounterfactualComparison(
                period=entry.period,
                decision_a=entry.decision,
                outcome_a=entry.result.narrative,
                decision_b=f"Instead of {entry.action.value}, choose hold",
                outcome_b="Slower progress but lower risk exposure",
                difference="Actual choice prioritized action over caution",
            )
        )
    return comparisons


async def analyze_counterfactuals(
    llm: LLMClient,
    champion: AgentState,
    goal_description: str,
) -> list[CounterfactualComparison]:
    key_periods = _identify_key_periods(champion)
    timeline_data = [
        {
            "period": e.period,
            "decision": e.decision,
            "action": e.action.value,
            "result": e.result.model_dump(),
            "world_summary": e.world_state.narrative_summary,
        }
        for e in champion.timeline
        if e.period in key_periods
    ]

    if not timeline_data:
        return _fallback_counterfactuals(champion)

    user = json.dumps(
        {"goal": goal_description, "key_periods": key_periods, "timeline": timeline_data},
        ensure_ascii=False,
        indent=2,
    )

    try:
        batch = await llm.structured_complete(
            COUNTERFACTUAL_SYSTEM,
            user,
            CounterfactualBatch,
            model=llm.analysis_model,
        )
        return batch.comparisons
    except Exception:
        return _fallback_counterfactuals(champion)
