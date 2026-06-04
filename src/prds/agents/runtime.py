import asyncio

from prds.llm.client import LLMClient
from prds.models.domain import (
    AgentDecision,
    AgentState,
    PeriodLogEntry,
    TargetGoal,
    WorldState,
)
from prds.simulation.actions import apply_result_resources, execute_action, update_agent_from_result


async def observe_and_decide(
    llm: LLMClient,
    agent: AgentState,
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
) -> AgentDecision:
    return await llm.decide(agent, world, goal.description, model=model)


async def run_agent_turn(
    llm: LLMClient,
    agent: AgentState,
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
) -> AgentState:
    decision = await observe_and_decide(llm, agent, world, goal, model=model)
    result = execute_action(agent, world, decision.action, decision.action_params)
    new_resources = apply_result_resources(agent, result)
    updated = update_agent_from_result(agent, result, new_resources)

    log_entry = PeriodLogEntry(
        period=world.period,
        world_state=world,
        thought=decision.thought,
        reasoning=decision.reasoning,
        decision=decision.decision,
        action=decision.action,
        action_params=decision.action_params,
        result=result,
        events=list(world.recent_events),
    )
    updated.timeline.append(log_entry)
    return updated


async def run_agents_parallel(
    llm: LLMClient,
    agents: list[AgentState],
    world: WorldState,
    goal: TargetGoal,
    model: str | None = None,
) -> list[AgentState]:
    active = [a for a in agents if not a.eliminated]
    tasks = [run_agent_turn(llm, agent, world, goal, model) for agent in active]
    results = await asyncio.gather(*tasks)

    result_map = {a.agent_id: a for a in results}
    updated_agents: list[AgentState] = []
    for agent in agents:
        if agent.eliminated:
            updated_agents.append(agent)
        else:
            updated_agents.append(result_map[agent.agent_id])
    return updated_agents
