import random
from typing import Any

from prds.models.domain import (
    ActionResult,
    ActionType,
    AgentAttributes,
    AgentState,
    ResourceSnapshot,
    WorldState,
)

MONTHLY_BURN_PER_HEAD = 2.0


def _scale(value: float, factor: float, lo: float = 0.0, hi: float | None = None) -> float:
    result = value * factor
    result = max(lo, result)
    if hi is not None:
        result = min(hi, result)
    return result


def execute_action(
    agent: AgentState,
    world: WorldState,
    action: ActionType,
    action_params: dict[str, Any],
) -> ActionResult:
    """Deterministic action execution - LLM chooses intent, rules compute outcome."""
    resources = agent.resources.model_copy()
    attrs = agent.attributes
    exec_factor = 0.5 + attrs.execution_power * 0.5
    env = world.environment

    reward = 0.0
    penalty = 0.0
    narrative_parts: list[str] = []
    success = True

    if action == ActionType.HIRE:
        count = int(action_params.get("count", 1))
        cost = count * MONTHLY_BURN_PER_HEAD * 3
        if resources.cash >= cost:
            resources.cash -= cost
            resources.team_size += count
            reward = count * 0.5 * exec_factor
            narrative_parts.append(f"Hired {count} team members")
        else:
            success = False
            penalty = 1.0
            narrative_parts.append("Hire failed: insufficient cash")

    elif action == ActionType.LAYOFF:
        count = min(int(action_params.get("count", 1)), max(0, resources.team_size - 1))
        resources.team_size -= count
        resources.cash += count * MONTHLY_BURN_PER_HEAD
        penalty = count * 0.3
        narrative_parts.append(f"Laid off {count} members to preserve cash")

    elif action == ActionType.FUNDRAISE:
        target = float(action_params.get("amount", 50.0))
        climate = world.external_market.get("funding_climate", 0.5)
        success_prob = min(0.9, 0.2 + climate * 0.4 + attrs.information_quality * 0.3)
        if random.random() < success_prob * exec_factor:
            raised = target * exec_factor
            resources.cash += raised
            reward = raised * 0.1
            narrative_parts.append(f"Raised {raised:.1f} in funding")
        else:
            success = False
            penalty = 0.5
            narrative_parts.append("Fundraise attempt failed")

    elif action == ActionType.PRODUCT_DEV:
        investment = float(action_params.get("investment", 5.0))
        if resources.cash >= investment:
            resources.cash -= investment
            gain = investment * 0.02 * exec_factor * (1 + env.tech_maturity)
            resources.product_maturity = _scale(resources.product_maturity + gain, 1.0, 0.0, 1.0)
            resources.users += int(resources.team_size * gain * 100)
            reward = gain * 10
            narrative_parts.append("Product development progressed")
        else:
            success = False
            penalty = 0.3
            narrative_parts.append("Product dev underfunded")

    elif action == ActionType.MARKETING:
        budget = float(action_params.get("budget", 5.0))
        if resources.cash >= budget:
            resources.cash -= budget
            brand_gain = budget * 0.015 * exec_factor * (1 + env.user_growth_rate)
            resources.brand_awareness = _scale(resources.brand_awareness + brand_gain, 1.0, 0.0, 1.0)
            user_gain = int(budget * brand_gain * 200 * world.external_market.get("demand_index", 0.6))
            resources.users += user_gain
            resources.market_share = _scale(
                resources.market_share + brand_gain * 0.05, 1.0, 0.0, 1.0
            )
            reward = brand_gain * 8
            narrative_parts.append(f"Marketing reached {user_gain} new users")
        else:
            success = False
            penalty = 0.3
            narrative_parts.append("Marketing budget insufficient")

    elif action == ActionType.STRATEGIC_PIVOT:
        cost = float(action_params.get("cost", 10.0))
        if resources.cash >= cost:
            resources.cash -= cost
            resources.product_maturity *= 0.7
            resources.brand_awareness *= 0.8
            resources.market_share = _scale(resources.market_share + 0.05 * attrs.adaptability, 1.0, 0.0, 1.0)
            reward = attrs.adaptability * 2
            narrative_parts.append("Strategic pivot executed")
        else:
            success = False
            penalty = 0.5

    elif action == ActionType.PARTNERSHIP:
        investment = float(action_params.get("investment", 3.0))
        if resources.cash >= investment:
            resources.cash -= investment
            resources.brand_awareness = _scale(resources.brand_awareness + 0.05 * exec_factor, 1.0, 0.0, 1.0)
            resources.revenue += investment * 0.5 * env.economic_index
            reward = 1.5 * exec_factor
            narrative_parts.append("Partnership established")
        else:
            success = False
            penalty = 0.2

    elif action == ActionType.ACQUISITION:
        cost = float(action_params.get("cost", 30.0))
        if resources.cash >= cost:
            resources.cash -= cost
            resources.users = int(resources.users * 1.3 + 500)
            resources.market_share = _scale(resources.market_share + 0.08, 1.0, 0.0, 1.0)
            reward = 3.0 * exec_factor
            narrative_parts.append("Acquisition completed")
        else:
            success = False
            penalty = 1.0
            narrative_parts.append("Acquisition failed: insufficient capital")

    elif action == ActionType.COST_CUT:
        savings = float(action_params.get("amount", 5.0))
        resources.cash += savings
        resources.team_size = max(1, resources.team_size - 1)
        penalty = 0.4
        narrative_parts.append(f"Cost cut saved {savings:.1f}")

    else:  # HOLD
        narrative_parts.append("Maintained current course")

    # Passive monthly dynamics
    burn = resources.team_size * MONTHLY_BURN_PER_HEAD
    resources.cash -= burn
    revenue = (
        resources.users * 0.001 * resources.product_maturity * env.economic_index
        + resources.market_share * 10
    )
    resources.revenue += revenue
    resources.cash += revenue

    organic_users = int(resources.users * env.user_growth_rate * resources.brand_awareness)
    resources.users += max(0, organic_users)

    resource_change = ResourceSnapshot(
        cash=resources.cash - agent.resources.cash,
        team_size=resources.team_size - agent.resources.team_size,
        users=resources.users - agent.resources.users,
        revenue=resources.revenue - agent.resources.revenue,
        product_maturity=resources.product_maturity - agent.resources.product_maturity,
        brand_awareness=resources.brand_awareness - agent.resources.brand_awareness,
        market_share=resources.market_share - agent.resources.market_share,
    )

    return ActionResult(
        reward=reward,
        penalty=penalty,
        resource_change=resource_change,
        narrative="; ".join(narrative_parts) + f" | Monthly burn: {burn:.1f}, revenue: {revenue:.1f}",
        success=success,
    )


def update_agent_from_result(
    agent: AgentState,
    result: ActionResult,
    new_resources: ResourceSnapshot,
) -> AgentState:
    risk_delta = result.penalty * 0.1 - result.reward * 0.02
    exec_delta = (0.05 if result.success else -0.03) * agent.attributes.execution_power
    adapt_delta = 0.02 if result.success else -0.01

    return agent.model_copy(
        update={
            "resources": new_resources,
            "risk_exposure": max(0.0, min(1.0, agent.risk_exposure + risk_delta)),
            "execution_score": max(0.0, min(1.0, agent.execution_score + exec_delta)),
            "adaptability_score": max(0.0, min(1.0, agent.adaptability_score + adapt_delta)),
        }
    )


def apply_result_resources(agent: AgentState, result: ActionResult) -> ResourceSnapshot:
    base = agent.resources
    delta = result.resource_change
    return ResourceSnapshot(
        cash=base.cash + delta.cash,
        team_size=base.team_size + delta.team_size,
        users=base.users + delta.users,
        revenue=base.revenue + delta.revenue,
        product_maturity=max(0.0, min(1.0, base.product_maturity + delta.product_maturity)),
        brand_awareness=max(0.0, min(1.0, base.brand_awareness + delta.brand_awareness)),
        market_share=max(0.0, min(1.0, base.market_share + delta.market_share)),
    )


def randomize_attributes(rng: random.Random, strategy: str) -> AgentAttributes:
    """Bias attributes based on strategy type."""
    base = AgentAttributes(
        risk_preference=rng.uniform(0.2, 0.8),
        learning_rate=rng.uniform(0.3, 0.9),
        execution_power=rng.uniform(0.3, 0.9),
        information_quality=rng.uniform(0.3, 0.9),
        adaptability=rng.uniform(0.3, 0.9),
    )
    bias_map = {
        "ConservativeAgent": {"risk_preference": 0.2},
        "AggressiveAgent": {"risk_preference": 0.9, "execution_power": 0.8},
        "DataDrivenAgent": {"information_quality": 0.9, "learning_rate": 0.85},
        "MarketingAgent": {"execution_power": 0.7},
        "ProductAgent": {"execution_power": 0.75, "learning_rate": 0.8},
        "FinancialAgent": {"risk_preference": 0.3, "information_quality": 0.85},
        "GrowthAgent": {"risk_preference": 0.7, "adaptability": 0.8},
        "BalancedAgent": {},
        "OpportunisticAgent": {"adaptability": 0.9, "risk_preference": 0.75},
        "SurvivalAgent": {"risk_preference": 0.15, "execution_power": 0.6},
    }
    biases = bias_map.get(strategy, {})
    data = base.model_dump()
    for key, val in biases.items():
        data[key] = max(0.0, min(1.0, (data[key] + val) / 2 if val <= 1 else val))
    return AgentAttributes(**data)
