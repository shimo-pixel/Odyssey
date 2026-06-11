from prds.models.domain import (
    CurrentState,
    EnvironmentParams,
    OntologyGraph,
    TargetGoal,
    WorldBackground,
    WorldState,
)


def initialize_world(
    ontology: OntologyGraph,
    current_state: CurrentState,
    goal: TargetGoal,
    total_events: int,
    *,
    world_background: WorldBackground | None = None,
) -> WorldState:
    """Build initial WorldState from ontology and user input (Phase 2)."""
    market_info = current_state.market_info
    financials = current_state.financials

    env = EnvironmentParams(
        economic_index=float(market_info.get("economic_index", 1.0)),
        policy_support=float(market_info.get("policy_support", 0.5)),
        tech_maturity=float(market_info.get("tech_maturity", current_state.resources.product_maturity)),
        competition_intensity=float(market_info.get("competition_intensity", 0.5)),
        user_growth_rate=float(market_info.get("user_growth_rate", 0.05)),
    )

    external_market = {
        "tam": float(market_info.get("tam", 1000.0)),
        "growth_rate": env.user_growth_rate,
        "demand_index": float(market_info.get("demand_index", 0.6)),
    }
    competition = {
        "competitor_count": float(market_info.get("competitor_count", 5)),
        "intensity": env.competition_intensity,
    }
    policy = {
        "support_level": env.policy_support,
        "regulatory_risk": float(market_info.get("regulatory_risk", 0.3)),
    }
    technology = {
        "maturity": env.tech_maturity,
        "innovation_pace": float(market_info.get("innovation_pace", 0.5)),
    }

    risk_summary = ", ".join(ontology.risks[:3]) if ontology.risks else "none identified"
    opp_summary = ", ".join(ontology.opportunities[:3]) if ontology.opportunities else "none identified"
    bg_summary = world_background.summary if world_background and world_background.summary else ""
    narrative = (
        f"Simulation initialized for goal: {goal.description}. "
        f"Key risks: {risk_summary}. Opportunities: {opp_summary}."
    )
    if bg_summary:
        narrative = f"{bg_summary[:500]}… | {narrative}" if len(bg_summary) > 500 else f"{bg_summary} | {narrative}"

    entity_hints = [e.name for e in ontology.entities[:15]]

    return WorldState(
        event_index=0,
        total_events=total_events,
        environment=env,
        external_market=external_market,
        competition=competition,
        policy=policy,
        technology=technology,
        recent_events=[],
        narrative_summary=narrative,
        world_background_summary=bg_summary,
        graph_entity_hints=entity_hints,
    )
