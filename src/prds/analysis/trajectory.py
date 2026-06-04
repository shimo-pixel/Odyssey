from prds.models.domain import (
    AgentDecisionPath,
    AgentScore,
    AgentState,
    DecisionStep,
    EventSummary,
    PeriodAgentDecision,
    PeriodComparison,
    TimelineEntry,
)
from prds.utils.time_labels import compute_period_label


def _step_from_entry(entry) -> DecisionStep:
    events = [e.event_type for e in entry.events] if entry.events else []
    return DecisionStep(
        period=entry.period,
        world_summary=entry.world_state.narrative_summary or "",
        events=events,
        action=entry.action,
        decision=entry.decision,
        reasoning=entry.reasoning,
        outcome=entry.result.narrative if entry.result else "",
        success=entry.result.success if entry.result else True,
    )


def build_champion_timeline(champion: AgentState) -> list[TimelineEntry]:
    timeline: list[TimelineEntry] = []
    for entry in champion.timeline:
        timeline.append(
            TimelineEntry(
                period=entry.period,
                world_state=entry.world_state,
                agent_thought=entry.thought,
                decision=entry.decision,
                action=entry.action,
                result=entry.result,
            )
        )
    return timeline


def build_agent_decision_paths(
    agents: list[AgentState],
    top_scores: list[AgentScore],
    *,
    limit: int = 10,
) -> list[AgentDecisionPath]:
    agent_map = {a.agent_id: a for a in agents}
    paths: list[AgentDecisionPath] = []

    for rank, score in enumerate(top_scores[:limit], start=1):
        agent = agent_map.get(score.agent_id)
        if not agent:
            continue
        paths.append(
            AgentDecisionPath(
                agent_id=agent.agent_id,
                rank=rank,
                total_score=score.total_score,
                eliminated=agent.eliminated,
                elimination_reason=agent.elimination_reason,
                steps=[_step_from_entry(e) for e in agent.timeline],
            )
        )
    return paths


def build_period_comparisons(
    paths: list[AgentDecisionPath],
    *,
    unit: str = "month",
    length: int = 1,
    start_date: str | None = None,
) -> list[PeriodComparison]:
    if not paths:
        return []

    periods = sorted({step.period for path in paths for step in path.steps})
    comparisons: list[PeriodComparison] = []

    for period in periods:
        ref_step: DecisionStep | None = None
        agents_at_period: list[PeriodAgentDecision] = []

        for path in paths:
            step = next((s for s in path.steps if s.period == period), None)
            if not step:
                continue
            if ref_step is None:
                ref_step = step
            agents_at_period.append(
                PeriodAgentDecision(
                    agent_id=path.agent_id,
                    rank=path.rank,
                    action=step.action,
                    decision=step.decision,
                    reasoning=step.reasoning,
                    outcome=step.outcome,
                    success=step.success,
                )
            )

        if not agents_at_period or ref_step is None:
            continue

        agents_at_period.sort(key=lambda item: item.rank)
        comparisons.append(
            PeriodComparison(
                period=period,
                period_label=compute_period_label(
                    period, unit=unit, length=length, start_date=start_date
                ),
                world_summary=ref_step.world_summary,
                events=list(ref_step.events),
                agents=agents_at_period,
            )
        )

    return comparisons


def build_period_comparisons_from_agents(
    agents: list[AgentState],
    rank_by_id: dict[str, int] | None = None,
    *,
    unit: str = "month",
    length: int = 1,
    start_date: str | None = None,
) -> list[PeriodComparison]:
    rank_by_id = rank_by_id or {}
    periods = sorted({entry.period for agent in agents for entry in agent.timeline})
    comparisons: list[PeriodComparison] = []

    for period in periods:
        ref_entry = None
        agents_at_period: list[PeriodAgentDecision] = []

        for agent in agents:
            entry = next((e for e in agent.timeline if e.period == period), None)
            if not entry:
                continue
            if ref_entry is None:
                ref_entry = entry
            agents_at_period.append(
                PeriodAgentDecision(
                    agent_id=agent.agent_id,
                    rank=rank_by_id.get(agent.agent_id, 0),
                    action=entry.action,
                    decision=entry.decision,
                    reasoning=entry.reasoning,
                    outcome=entry.result.narrative if entry.result else "",
                    success=entry.result.success if entry.result else True,
                )
            )

        if ref_entry is None or not agents_at_period:
            continue

        event_objs = ref_entry.events or []
        agents_at_period.sort(key=lambda item: (item.rank == 0, item.rank, item.agent_id))
        comparisons.append(
            PeriodComparison(
                period=period,
                period_label=compute_period_label(
                    period, unit=unit, length=length, start_date=start_date
                ),
                world_summary=ref_entry.world_state.narrative_summary or "",
                events=[e.event_type for e in event_objs],
                event_summaries=[
                    EventSummary(
                        event_type=e.event_type,
                        description=e.description or e.event_type.replace("_", " "),
                        impact=e.impact,
                    )
                    for e in event_objs
                ],
                agents=agents_at_period,
            )
        )

    return comparisons
