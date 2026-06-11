import random
from typing import Any

from prds.models.domain import (
    ActionResult,
    ActionType,
    AgentAttributes,
    AgentState,
    ActionFinancials,
    ResourceDelta,
    ResourceSnapshot,
    WorldState,
)
from prds.simulation.realism import (
    MONTHLY_BURN_PER_HEAD,
    competition_factor,
    demand_factor,
    funding_climate,
    monthly_burn,
    runway_months,
)


def _scale(value: float, factor: float, lo: float = 0.0, hi: float | None = None) -> float:
    result = value * factor
    result = max(lo, result)
    if hi is not None:
        result = min(hi, result)
    return result


def execute_action(
    agent: AgentState,
    world: WorldState,
    action: ActionType | str,
    action_params: dict[str, Any],
    *,
    domain_id: str = "startup",
    param_overrides: dict | None = None,
) -> ActionResult:
    action_str = action.value if isinstance(action, ActionType) else str(action)
    try:
        action_type = ActionType(action_str)
    except ValueError:
        action_type = ActionType.HOLD
    return _execute_startup_action(agent, world, action_type, action_params, param_overrides)


def _execute_startup_action(
    agent: AgentState,
    world: WorldState,
    action: ActionType,
    action_params: dict[str, Any],
    param_overrides: dict | None = None,
) -> ActionResult:
    """Deterministic action execution - LLM chooses intent, rules compute outcome."""
    from prds.simulation.parameters import StartupParams, apply_agent_diversity, resolve_params

    resources = agent.resources.model_copy()
    attrs = agent.attributes
    p: StartupParams = apply_agent_diversity(
        resolve_params(StartupParams(), param_overrides), attrs
    )
    exec_factor = 0.5 + attrs.execution_power * 0.5
    env = world.environment
    competition = competition_factor(world)
    demand = demand_factor(world)
    climate = funding_climate(world)

    reward = 0.0
    penalty = 0.0
    narrative_parts: list[str] = []
    success = True
    action_expense = 0.0
    action_income = 0.0

    def spend(amount: float) -> None:
        nonlocal action_expense
        if amount <= 0:
            return
        resources.cash -= amount
        action_expense += amount

    def earn(amount: float) -> None:
        nonlocal action_income
        if amount <= 0:
            return
        resources.cash += amount
        action_income += amount

    if action == ActionType.HIRE:
        count = int(action_params.get("count", 1))
        cost = count * p.monthly_burn_per_head * p.hire_cost_months
        projected_burn = (resources.team_size + count) * p.monthly_burn_per_head
        post_runway = resources.cash / max(projected_burn, 0.1)
        if resources.cash >= cost and post_runway >= p.hire_min_post_runway:
            spend(cost)
            resources.team_size += count
            reward = count * 0.3 * exec_factor
            narrative_parts.append(f"Hired {count} team members (runway ~{post_runway:.1f}mo)")
        else:
            success = False
            penalty = 0.8
            narrative_parts.append("Hire blocked: insufficient cash or runway after expansion")

    elif action == ActionType.LAYOFF:
        count = min(int(action_params.get("count", 1)), max(0, resources.team_size - 1))
        if count > 0:
            resources.team_size -= count
            severance = count * p.monthly_burn_per_head * p.layoff_severance_months
            spend(severance)
            penalty = count * 0.35
            narrative_parts.append(f"Laid off {count} members (severance {severance:.1f})")
        else:
            success = False
            narrative_parts.append("Layoff not possible at minimum team size")

    elif action == ActionType.FUNDRAISE:
        target = float(action_params.get("amount", 50.0))
        success_prob = min(
            p.fundraise_max_prob,
            p.fundraise_base_prob
            + climate * p.fundraise_climate_weight
            + attrs.information_quality * p.fundraise_info_weight,
        ) * exec_factor
        if climate < 0.25:
            success_prob *= 0.5
        if random.random() < success_prob:
            raised = target * exec_factor * (p.fundraise_yield_base + climate * p.fundraise_yield_climate)
            earn(raised)
            reward = raised * 0.05
            narrative_parts.append(f"Raised {raised:.1f} in a difficult funding market")
        else:
            success = False
            penalty = 0.6
            narrative_parts.append("Fundraise failed after investor pass / term mismatch")

    elif action == ActionType.PRODUCT_DEV:
        investment = float(action_params.get("investment", 5.0))
        if resources.cash >= investment:
            spend(investment)
            gain = investment * p.product_dev_efficiency * exec_factor * (0.4 + env.tech_maturity * 0.6)
            resources.product_maturity = _scale(resources.product_maturity + gain, 1.0, 0.0, 1.0)
            if resources.product_maturity >= 0.2:
                user_delta = int(max(1, resources.users * gain * 0.08))
            else:
                user_delta = int(gain * 80)
            resources.users += user_delta
            reward = gain * 6
            narrative_parts.append(f"Product progressed (+{user_delta} users, maturity +{gain:.2f})")
        else:
            success = False
            penalty = 0.3
            narrative_parts.append("Product dev underfunded")

    elif action == ActionType.MARKETING:
        budget = float(action_params.get("budget", 5.0))
        if resources.cash >= budget and resources.product_maturity >= p.marketing_min_maturity:
            spend(budget)
            saturation = 1.0 / (1.0 + resources.brand_awareness * 2.0)
            brand_gain = (
                budget
                * p.marketing_efficiency
                * exec_factor
                * max(0.25, demand)
                * (1.0 - competition * 0.45)
                * saturation
            )
            resources.brand_awareness = _scale(resources.brand_awareness + brand_gain, 1.0, 0.0, 1.0)
            raw_gain = int(budget * brand_gain * 35 * demand * resources.product_maturity)
            cap = int(max(20, resources.users * 0.12))
            user_gain = min(raw_gain, cap)
            resources.users += user_gain
            resources.market_share = _scale(
                resources.market_share + brand_gain * 0.03 * demand, 1.0, 0.0, 1.0
            )
            reward = brand_gain * 5
            narrative_parts.append(f"Marketing added ~{user_gain} users in a competitive market")
        elif resources.product_maturity < p.marketing_min_maturity:
            success = False
            penalty = 0.4
            narrative_parts.append("Marketing ineffective before basic product readiness")
        else:
            success = False
            penalty = 0.3
            narrative_parts.append("Marketing budget insufficient")

    elif action == ActionType.STRATEGIC_PIVOT:
        cost = float(action_params.get("cost", 10.0))
        if resources.cash >= cost:
            spend(cost)
            resources.product_maturity *= 0.65
            resources.brand_awareness *= 0.75
            resources.users = int(resources.users * 0.85)
            resources.market_share = _scale(
                resources.market_share + 0.03 * attrs.adaptability, 1.0, 0.0, 1.0
            )
            reward = attrs.adaptability * 1.2
            penalty = 0.5
            narrative_parts.append("Pivot executed with traction loss and repositioning cost")
        else:
            success = False
            penalty = 0.5

    elif action == ActionType.PARTNERSHIP:
        investment = float(action_params.get("investment", 3.0))
        if resources.cash >= investment:
            spend(investment)
            resources.brand_awareness = _scale(
                resources.brand_awareness + 0.03 * exec_factor * demand, 1.0, 0.0, 1.0
            )
            deal_revenue = investment * 0.25 * env.economic_index * demand
            resources.revenue += deal_revenue
            reward = 0.8 * exec_factor
            narrative_parts.append(f"Partnership signed; incremental revenue ~{deal_revenue:.1f}")
        else:
            success = False
            penalty = 0.2

    elif action == ActionType.ACQUISITION:
        cost = float(action_params.get("cost", 30.0))
        viable = (
            resources.cash >= cost * 1.2
            and resources.product_maturity >= p.acquisition_min_maturity
            and runway_months(resources) >= p.acquisition_min_runway
        )
        if viable and random.random() < p.acquisition_success_prob * exec_factor:
            spend(cost)
            integration_cost = cost * 0.15
            spend(integration_cost)
            resources.users = int(resources.users * 1.12 + 150)
            resources.market_share = _scale(resources.market_share + 0.04, 1.0, 0.0, 1.0)
            penalty = 0.6
            reward = 1.5 * exec_factor
            narrative_parts.append("Acquisition closed with integration friction")
        else:
            success = False
            penalty = 1.0
            narrative_parts.append("Acquisition failed: capital, readiness, or diligence blocked deal")

    elif action == ActionType.COST_CUT:
        savings = min(float(action_params.get("amount", 5.0)), monthly_burn(resources) * 0.8)
        if savings > 0:
            resources.team_size = max(1, resources.team_size - 1)
            earn(savings)
            penalty = 0.45
            narrative_parts.append(f"Cost cut saved {savings:.1f} but reduced capacity")
        else:
            success = False
            narrative_parts.append("No meaningful cost left to cut")

    else:  # HOLD
        narrative_parts.append("Maintained current course")

    operating_burn = monthly_burn(resources)
    resources.cash -= operating_burn
    if resources.product_maturity < 0.12:
        operating_revenue = resources.market_share * 1.5 * env.economic_index * demand
    else:
        operating_revenue = (
            resources.users
            * p.revenue_per_user
            * resources.product_maturity
            * env.economic_index
            * max(0.3, demand)
            * (1.0 - competition * 0.35)
            + resources.market_share * 4 * resources.product_maturity * demand
        )
    resources.revenue += operating_revenue
    resources.cash += operating_revenue

    organic_users = int(
        resources.users
        * env.user_growth_rate
        * resources.brand_awareness
        * p.organic_growth_weight
        * max(0.2, demand)
    )
    resources.users += max(0, organic_users)

    book_revenue_delta = resources.revenue - agent.resources.revenue
    non_cash_revenue = max(0.0, book_revenue_delta - operating_revenue)
    total_expense = action_expense + operating_burn
    total_revenue = action_income + operating_revenue + non_cash_revenue
    net_cash_flow = resources.cash - agent.resources.cash
    financials = ActionFinancials(
        action_expense=action_expense,
        action_income=action_income,
        operating_burn=operating_burn,
        operating_revenue=operating_revenue + non_cash_revenue,
        total_expense=total_expense,
        total_revenue=total_revenue,
        net_cash_flow=net_cash_flow,
    )

    resource_change = ResourceDelta(
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
        financials=financials,
        narrative=(
            "; ".join(narrative_parts)
            + f" | 支出 {total_expense:.1f}（动作 {action_expense:.1f}+运营 {operating_burn:.1f}）"
            + f"，收益 {total_revenue:.1f}，净现金流 {net_cash_flow:+.1f}"
        ),
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
        domain_metrics=dict(base.domain_metrics),
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
