"""Heuristic agent decisions for MockLLMClient — strategy- and state-aware."""

from __future__ import annotations

import hashlib
from typing import Iterable

from prds.models.domain import (
    ActionType,
    AgentDecision,
    AgentState,
    StrategyType,
    WorldState,
)
from prds.simulation.actions import MONTHLY_BURN_PER_HEAD

# Preferred actions per strategy (ordered by typical priority).
STRATEGY_PREFERENCES: dict[StrategyType, list[ActionType]] = {
    StrategyType.CONSERVATIVE: [
        ActionType.HOLD,
        ActionType.PRODUCT_DEV,
        ActionType.COST_CUT,
        ActionType.MARKETING,
    ],
    StrategyType.AGGRESSIVE: [
        ActionType.MARKETING,
        ActionType.HIRE,
        ActionType.PRODUCT_DEV,
        ActionType.STRATEGIC_PIVOT,
    ],
    StrategyType.DATA_DRIVEN: [
        ActionType.PRODUCT_DEV,
        ActionType.MARKETING,
        ActionType.HOLD,
        ActionType.PARTNERSHIP,
    ],
    StrategyType.MARKETING: [
        ActionType.MARKETING,
        ActionType.PARTNERSHIP,
        ActionType.HOLD,
        ActionType.PRODUCT_DEV,
    ],
    StrategyType.PRODUCT: [
        ActionType.PRODUCT_DEV,
        ActionType.HIRE,
        ActionType.HOLD,
        ActionType.MARKETING,
    ],
    StrategyType.FINANCIAL: [
        ActionType.COST_CUT,
        ActionType.HOLD,
        ActionType.PRODUCT_DEV,
        ActionType.FUNDRAISE,
    ],
    StrategyType.GROWTH: [
        ActionType.MARKETING,
        ActionType.HIRE,
        ActionType.PRODUCT_DEV,
        ActionType.PARTNERSHIP,
    ],
    StrategyType.BALANCED: [
        ActionType.PRODUCT_DEV,
        ActionType.MARKETING,
        ActionType.HOLD,
        ActionType.HIRE,
    ],
    StrategyType.OPPORTUNISTIC: [
        ActionType.PARTNERSHIP,
        ActionType.STRATEGIC_PIVOT,
        ActionType.MARKETING,
        ActionType.ACQUISITION,
    ],
    StrategyType.SURVIVAL: [
        ActionType.COST_CUT,
        ActionType.LAYOFF,
        ActionType.HOLD,
        ActionType.FUNDRAISE,
    ],
}

ACTION_SUMMARIES: dict[ActionType, str] = {
    ActionType.HOLD: "维持现状，观察市场",
    ActionType.PRODUCT_DEV: "投入产品研发，提升产品成熟度",
    ActionType.MARKETING: "加大市场推广，获取用户",
    ActionType.HIRE: "扩充团队，提升执行能力",
    ActionType.LAYOFF: "精简人员，降低 burn",
    ActionType.COST_CUT: "削减非核心开支，延长 runway",
    ActionType.FUNDRAISE: "启动融资，补充现金储备",
    ActionType.PARTNERSHIP: "寻求战略合作，拓展渠道",
    ActionType.STRATEGIC_PIVOT: "调整业务方向，适应市场变化",
    ActionType.ACQUISITION: "收购竞品或资产，快速扩大规模",
}


def _runway_months(resources) -> float:
    burn = max(resources.team_size * MONTHLY_BURN_PER_HEAD, 1.0)
    return resources.cash / burn


def _last_action(agent: AgentState) -> ActionType | None:
    if not agent.timeline:
        return None
    return agent.timeline[-1].action


def _stable_pick(options: list[ActionType], seed: str) -> ActionType:
    if not options:
        return ActionType.HOLD
    digest = hashlib.md5(seed.encode()).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def _filter_feasible(
    candidates: Iterable[ActionType],
    agent: AgentState,
    world: WorldState,
    *,
    last: ActionType | None,
) -> list[ActionType]:
    res = agent.resources
    runway = _runway_months(res)
    funding_climate = world.external_market.get("funding_climate", 0.5)
    feasible: list[ActionType] = []

    for action in candidates:
        if action == last:
            continue
        if action == ActionType.FUNDRAISE:
            # Fundraise is a major move — only when runway is tight or climate is favorable.
            if runway > 6 and agent.strategy_type not in (
                StrategyType.FINANCIAL,
                StrategyType.SURVIVAL,
            ):
                continue
            if runway > 3 and funding_climate < 0.45:
                continue
        if action == ActionType.HIRE and res.cash < res.team_size * MONTHLY_BURN_PER_HEAD * 4:
            continue
        if action == ActionType.MARKETING and res.cash < 5:
            continue
        if action == ActionType.PRODUCT_DEV and res.cash < 5:
            continue
        if action == ActionType.ACQUISITION and res.cash < 35:
            continue
        if action == ActionType.STRATEGIC_PIVOT and res.cash < 10:
            continue
        if action == ActionType.LAYOFF and res.team_size <= 2:
            continue
        feasible.append(action)

    return feasible


def _state_boosts(agent: AgentState, world: WorldState, goal_description: str) -> list[ActionType]:
    """Contextual nudges based on metrics and recent events."""
    res = agent.resources
    boosts: list[ActionType] = []
    runway = _runway_months(res)

    if res.product_maturity < 0.35:
        boosts.extend([ActionType.PRODUCT_DEV, ActionType.PRODUCT_DEV])
    if res.users < 200 and ("用户" in goal_description or "user" in goal_description.lower()):
        boosts.extend([ActionType.MARKETING, ActionType.MARKETING])
    if res.brand_awareness < 0.25:
        boosts.append(ActionType.MARKETING)
    if runway < 4:
        boosts.extend([ActionType.COST_CUT, ActionType.LAYOFF])
        if agent.strategy_type in (StrategyType.FINANCIAL, StrategyType.SURVIVAL):
            boosts.append(ActionType.FUNDRAISE)
    if res.cash > 80 and res.market_share < 0.05:
        boosts.append(ActionType.ACQUISITION)

    for evt in world.recent_events:
        if evt.event_type in ("tech_breakthrough", "innovation_wave"):
            boosts.append(ActionType.PRODUCT_DEV)
        if evt.event_type in ("market_expansion", "demand_surge"):
            boosts.append(ActionType.MARKETING)
        if evt.event_type in ("funding_winter", "capital_crunch"):
            boosts.extend([ActionType.COST_CUT, ActionType.HOLD])

    return boosts


def build_mock_decision(
    agent: AgentState,
    world: WorldState,
    goal_description: str,
) -> AgentDecision:
    strategy = agent.strategy_type
    last = _last_action(agent)
    base = list(STRATEGY_PREFERENCES.get(strategy, STRATEGY_PREFERENCES[StrategyType.BALANCED]))
    boosted = base + _state_boosts(agent, world, goal_description)
    options = _filter_feasible(boosted, agent, world, last=last)

    if not options:
        options = _filter_feasible(
            [ActionType.HOLD, ActionType.PRODUCT_DEV, ActionType.MARKETING, ActionType.COST_CUT],
            agent,
            world,
            last=last,
        ) or [ActionType.HOLD]

    seed = f"{agent.agent_id}:{world.period}:{strategy.value}"
    action = _stable_pick(options, seed)
    summary = ACTION_SUMMARIES.get(action, f"Execute {action.value}")

    runway = _runway_months(agent.resources)
    thought = (
        f"第 {world.period} 期：现金 runway 约 {runway:.1f} 月，"
        f"产品成熟度 {agent.resources.product_maturity:.2f}，"
        f"用户 {agent.resources.users}"
    )
    priority = "生存" if runway < 4 else "增长"
    reasoning = (
        f"作为 {strategy.value}，当前优先{priority}；"
        f"选择「{summary}」，避免重复上一期"
        f"{f'的 {last.value}' if last else ''}。"
    )

    params: dict[str, float | int] = {
        "investment": 5.0,
        "budget": 5.0,
        "amount": 20.0,
        "count": 1,
        "cost": 10.0,
    }
    if action == ActionType.HIRE:
        params["count"] = 1 if agent.resources.cash < 60 else 2
    elif action == ActionType.FUNDRAISE:
        params["amount"] = 30.0 if runway < 3 else 20.0
    elif action == ActionType.MARKETING:
        params["budget"] = 8.0 if agent.strategy_type == StrategyType.MARKETING else 5.0

    return AgentDecision(
        thought=thought,
        reasoning=reasoning,
        decision=summary,
        action=action,
        action_params=params,
    )
