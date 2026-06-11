import json

from prds.llm.client import LLMClient
from prds.llm.schemas import CounterfactualBatch
from prds.models.domain import AgentState, CounterfactualComparison


COUNTERFACTUAL_SYSTEM = """You are a counterfactual analysis engine.
Given a champion agent's decision timeline, identify 2-4 key decision nodes
and compare the actual decision vs a plausible alternative.
Return JSON: {"comparisons": [{"event_index": 1, "decision_a": "...", "outcome_a": "...", "decision_b": "...", "outcome_b": "...", "difference": "..."}]}"""


def _identify_key_events(champion: AgentState) -> list[int]:
    """Heuristic: periods with large resource changes or action shifts."""
    key_events: list[int] = []
    for entry in champion.timeline:
        action = str(entry.action)
        delta = abs(entry.result.resource_change.cash) + abs(entry.result.resource_change.users) * 0.001
        if delta > 5 or action in ("fundraise", "strategic_pivot", "acquisition"):
            key_events.append(entry.event_index)
    if not key_events and champion.timeline:
        key_events = [champion.timeline[0].event_index, champion.timeline[-1].period]
    return sorted(set(key_events))[:4]


async def analyze_counterfactuals(
    llm: LLMClient,
    champion: AgentState,
    goal_description: str,
) -> list[CounterfactualComparison]:
    key_events = _identify_key_events(champion)
    timeline_data = [
        {
            "event_index": e.event_index,
            "decision": e.decision,
            "action": str(e.action),
            "result": e.result.model_dump(),
            "world_summary": e.world_state.narrative_summary,
        }
        for e in champion.timeline
        if e.event_index in key_events
    ]

    if not timeline_data:
        raise ValueError("Champion timeline has no key events for counterfactual analysis")

    user = json.dumps(
        {"goal": goal_description, "key_events": key_events, "timeline": timeline_data},
        ensure_ascii=False,
        indent=2,
    )

    batch = await llm.structured_complete(
        COUNTERFACTUAL_SYSTEM,
        user,
        CounterfactualBatch,
        model=llm.analysis_model,
    )
    return batch.comparisons
