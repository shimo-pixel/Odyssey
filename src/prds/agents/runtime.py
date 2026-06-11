import asyncio
import logging

from prds.llm.client import LLMClient, LLMStructuredOutputError
from prds.models.domain import (
    ActionType,
    AgentDecision,
    AgentState,
    DecisionLogEntry,
    Event,
    TargetGoal,
    WorldState,
)
from prds.simulation.actions import apply_result_resources, execute_action, update_agent_from_result
from prds.simulation.elimination import compute_goal_status

logger = logging.getLogger(__name__)


def _hold_decision(reason: str) -> AgentDecision:
    return AgentDecision(
        thought="Could not obtain a valid LLM decision for this event.",
        reasoning=reason,
        decision="Hold and reassess after the next event",
        action=ActionType.HOLD.value,
        action_params={},
    )


async def observe_and_decide(
    llm: LLMClient,
    agent: AgentState,
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
    *,
    domain_id: str = "startup",
) -> AgentDecision:
    try:
        return await llm.decide(agent, world, goal, model=model, domain_id=domain_id)
    except LLMStructuredOutputError as exc:
        logger.warning(
            "Agent %s decision failed, defaulting to hold: %s",
            agent.agent_id,
            exc,
        )
        return _hold_decision(f"LLM output error: {exc}. Defaulting to hold to preserve runway.")


async def run_agent_turn(
    llm: LLMClient,
    agent: AgentState,
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
    *,
    domain_id: str = "startup",
    param_overrides: dict | None = None,
    trigger_event: Event | None = None,
) -> AgentState:
    decision = await observe_and_decide(llm, agent, world, goal, model=model, domain_id=domain_id)
    result = execute_action(
        agent,
        world,
        decision.action,
        decision.action_params,
        domain_id=domain_id,
        param_overrides=param_overrides,
    )
    new_resources = apply_result_resources(agent, result)
    goal_status = compute_goal_status(new_resources, goal, domain_id=domain_id)
    updated = update_agent_from_result(agent, result, new_resources)
    updated = updated.model_copy(update={"goal_progress": goal_status.progress})

    primary = trigger_event or (world.recent_events[0] if world.recent_events else None)
    log_entry = DecisionLogEntry(
        event_index=world.event_index,
        trigger_event_id=primary.event_id if primary else "",
        world_state=world,
        thought=decision.thought,
        reasoning=decision.reasoning,
        decision=decision.decision,
        action=decision.action,
        action_params=decision.action_params,
        result=result,
        events=list(world.recent_events),
        resources_after=new_resources,
        goal_status=goal_status,
    )
    updated.timeline.append(log_entry)
    return updated


async def run_agents_parallel(
    llm: LLMClient,
    agents: list[AgentState],
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
    *,
    domain_id: str = "startup",
    param_overrides: dict | None = None,
    trigger_event: Event | None = None,
) -> list[AgentState]:
    active = [a for a in agents if not a.eliminated]
    tasks = [
        run_agent_turn(
            llm,
            agent,
            world,
            goal,
            model,
            domain_id=domain_id,
            param_overrides=param_overrides,
            trigger_event=trigger_event,
        )
        for agent in active
    ]
    results = await asyncio.gather(*tasks)

    result_map = {a.agent_id: a for a in results}
    updated_agents: list[AgentState] = []
    for agent in agents:
        if agent.eliminated:
            updated_agents.append(agent)
        else:
            updated_agents.append(result_map[agent.agent_id])
    return updated_agents
