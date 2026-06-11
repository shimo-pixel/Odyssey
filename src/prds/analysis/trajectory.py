from prds.models.domain import (
    ActionFinancials,
    AgentDecisionPath,
    AgentScore,
    AgentState,
    DecisionStep,
    Event,
    EventAgentDecision,
    EventComparison,
    EventSummary,
    TimelineEntry,
)


def _event_label(event_index: int, event: Event | None) -> str:
    if event:
        name = event.event_type.replace("_", " ")
        return f"#{event_index} · {name}"
    return f"事件 #{event_index}"


def _step_from_entry(entry) -> DecisionStep:
    events = [e.event_type for e in entry.events] if entry.events else []
    return DecisionStep(
        event_index=entry.event_index,
        trigger_event_id=entry.trigger_event_id,
        world_summary=entry.world_state.narrative_summary or "",
        events=events,
        action=entry.action,
        decision=entry.decision,
        reasoning=entry.reasoning,
        outcome=entry.result.narrative if entry.result else "",
        success=entry.result.success if entry.result else True,
        financials=entry.result.financials if entry.result else ActionFinancials(),
        action_summary=entry.result.action_summary if entry.result else {},
        goal_status=entry.goal_status,
    )


def build_champion_timeline(champion: AgentState) -> list[TimelineEntry]:
    timeline: list[TimelineEntry] = []
    for entry in champion.timeline:
        timeline.append(
            TimelineEntry(
                event_index=entry.event_index,
                trigger_event_id=entry.trigger_event_id,
                world_state=entry.world_state,
                agent_thought=entry.thought,
                decision=entry.decision,
                action=entry.action,
                result=entry.result,
                resources_after=entry.resources_after,
                goal_status=entry.goal_status,
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


def build_event_comparisons(
    paths: list[AgentDecisionPath],
    *,
    planned_events: list[Event] | None = None,
) -> list[EventComparison]:
    if not paths:
        return []

    event_indices = sorted({step.event_index for path in paths for step in path.steps})
    event_by_index = {i + 1: e for i, e in enumerate(planned_events or [])}
    comparisons: list[EventComparison] = []

    for event_index in event_indices:
        ref_step: DecisionStep | None = None
        agents_at_event: list[EventAgentDecision] = []

        for path in paths:
            step = next((s for s in path.steps if s.event_index == event_index), None)
            if not step:
                continue
            if ref_step is None:
                ref_step = step
            agents_at_event.append(
                EventAgentDecision(
                    agent_id=path.agent_id,
                    rank=path.rank,
                    action=step.action,
                    decision=step.decision,
                    reasoning=step.reasoning,
                    outcome=step.outcome,
                    success=step.success,
                    financials=step.financials,
                    action_summary=step.action_summary,
                    goal_status=step.goal_status,
                )
            )

        if not agents_at_event or ref_step is None:
            continue

        planned = event_by_index.get(event_index)
        agents_at_event.sort(key=lambda item: item.rank)
        comparisons.append(
            EventComparison(
                event_index=event_index,
                event_id=planned.event_id if planned else ref_step.trigger_event_id,
                event_label=_event_label(event_index, planned),
                world_summary=ref_step.world_summary,
                events=list(ref_step.events),
                agents=agents_at_event,
            )
        )

    return comparisons


def build_event_comparisons_from_agents(
    agents: list[AgentState],
    rank_by_id: dict[str, int] | None = None,
    *,
    planned_events: list[Event] | None = None,
) -> list[EventComparison]:
    rank_by_id = rank_by_id or {}
    event_indices = sorted({entry.event_index for agent in agents for entry in agent.timeline})
    event_by_index = {i + 1: e for i, e in enumerate(planned_events or [])}
    comparisons: list[EventComparison] = []

    for event_index in event_indices:
        ref_entry = None
        agents_at_event: list[EventAgentDecision] = []

        for agent in agents:
            entry = next((e for e in agent.timeline if e.event_index == event_index), None)
            if not entry:
                continue
            if ref_entry is None:
                ref_entry = entry
            agents_at_event.append(
                EventAgentDecision(
                    agent_id=agent.agent_id,
                    rank=rank_by_id.get(agent.agent_id, 0),
                    action=entry.action,
                    decision=entry.decision,
                    reasoning=entry.reasoning,
                    outcome=entry.result.narrative if entry.result else "",
                    success=entry.result.success if entry.result else True,
                    financials=entry.result.financials if entry.result else ActionFinancials(),
                    action_summary=entry.result.action_summary if entry.result else {},
                    goal_status=entry.goal_status,
                )
            )

        if ref_entry is None or not agents_at_event:
            continue

        event_objs = ref_entry.events or []
        planned = event_by_index.get(event_index)
        agents_at_event.sort(key=lambda item: (item.rank == 0, item.rank, item.agent_id))
        comparisons.append(
            EventComparison(
                event_index=event_index,
                event_id=planned.event_id if planned else ref_entry.trigger_event_id,
                event_label=_event_label(event_index, planned or (event_objs[0] if event_objs else None)),
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
                agents=agents_at_event,
            )
        )

    return comparisons
