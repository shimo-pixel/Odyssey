"""Shared helpers for constraint-aware, realistic simulation dynamics."""

MONTHLY_BURN_PER_HEAD = 2.0

from prds.models.domain import AgentState, ResourceSnapshot, TargetGoal, WorldState


def monthly_burn(resources: ResourceSnapshot) -> float:
    return max(resources.team_size * MONTHLY_BURN_PER_HEAD, 0.1)


def runway_months(resources: ResourceSnapshot) -> float:
    return resources.cash / monthly_burn(resources)


def competition_factor(world: WorldState) -> float:
    return float(world.competition.get("intensity", world.environment.competition_intensity))


def demand_factor(world: WorldState) -> float:
    return float(world.external_market.get("demand_index", 0.6))


def funding_climate(world: WorldState) -> float:
    return float(world.external_market.get("funding_climate", 0.5))


def recent_events_summary(world: WorldState, limit: int = 5) -> list[str]:
    return [e.description or e.event_type for e in world.recent_events[:limit]]


def consecutive_negative_cashflow(agent: AgentState, periods: int = 3) -> bool:
    recent = agent.timeline[-periods:]
    if len(recent) < periods:
        return False
    return all(entry.result.financials.net_cash_flow < 0 for entry in recent)


def build_decision_context(agent: AgentState, world: WorldState, goal: TargetGoal) -> dict:
    from prds.simulation.elimination import compute_goal_status

    burn = monthly_burn(agent.resources)
    goal_status = compute_goal_status(agent.resources, goal)
    context = {
        "runway_months": round(runway_months(agent.resources), 2),
        "monthly_burn": round(burn, 2),
        "competition_intensity": round(competition_factor(world), 2),
        "demand_index": round(demand_factor(world), 2),
        "funding_climate": round(funding_climate(world), 2),
        "economic_index": round(world.environment.economic_index, 2),
        "recent_external_events": recent_events_summary(world),
        "goal_status": goal_status.model_dump(),
        "simulation_note": (
            "Most real organizations fail to hit ambitious goals. "
            "Choose the most plausible action under current constraints, not the most optimistic."
        ),
    }
    # Domain grounding (steps ③-⑤): industry background + knowledge-graph facts so the
    # agent decides like a real practitioner in this domain, not in a vacuum.
    if world.world_background_summary:
        context["domain_background"] = world.world_background_summary[:600]
    if world.domain_brief:
        context["domain_key_findings"] = list(world.domain_brief)
    if world.domain_facts:
        context["domain_graph_facts"] = list(world.domain_facts)
    if world.graph_entity_hints:
        context["domain_entities"] = world.graph_entity_hints[:10]
    if world.knowledge_graph:
        from prds.graph.agent_ontology import extract_agent_subgraph, resolve_agent_node_id

        node_id = resolve_agent_node_id(world.knowledge_graph, agent)
        if node_id:
            subgraph = extract_agent_subgraph(world.knowledge_graph, node_id)
            if subgraph:
                context["agent_graph_context"] = subgraph
    return context
