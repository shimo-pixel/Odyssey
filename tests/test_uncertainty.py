from prds.analysis.distribution import build_outcome_distribution
from prds.analysis.patterns import (
    build_data_driven_counterfactuals,
    build_data_driven_synthesis,
)
from prds.models.domain import (
    ActionResult,
    AgentAttributes,
    AgentState,
    GoalStatus,
    PeriodLogEntry,
    ResourceSnapshot,
    StrategyType,
    TargetGoal,
    WorldState,
)
from prds.simulation.parameters import StartupParams, apply_agent_diversity, resolve_params


def _agent(aid: str, progress: float, eliminated: bool, action: str, reason: str | None = None) -> AgentState:
    entry = PeriodLogEntry(
        period=1,
        world_state=WorldState(period=1, total_periods=3),
        action=action,
        result=ActionResult(),
        goal_status=GoalStatus(progress=progress, distance=1 - progress),
    )
    return AgentState(
        agent_id=aid,
        strategy_type=StrategyType.BALANCED,
        attributes=AgentAttributes(),
        resources=ResourceSnapshot(cash=50, revenue=progress * 100, users=int(progress * 1000)),
        eliminated=eliminated,
        elimination_reason=reason,
        timeline=[entry],
    )


def _sample_agents() -> list[AgentState]:
    return [
        _agent("a1", 0.95, False, "product_dev"),
        _agent("a2", 0.80, False, "fundraise"),
        _agent("a3", 0.40, False, "marketing"),
        _agent("a4", 0.05, True, "acquisition", "资金耗尽"),
    ]


def test_distribution_reports_rates_and_bands():
    goal = TargetGoal(description="x", success_metrics={"revenue": 100, "users": 1000})
    dist = build_outcome_distribution(_sample_agents(), goal, domain_id="startup")
    assert dist.sample_size == 4
    assert 0.0 <= dist.success_rate <= 1.0
    assert dist.elimination_rate == 0.25
    assert dist.goal_progress.p25 <= dist.goal_progress.median <= dist.goal_progress.p75
    assert dist.param_assumptions  # assumptions exposed for transparency
    assert "资金耗尽" in dist.elimination_reasons


def test_data_driven_synthesis_and_counterfactuals_from_stats():
    goal = TargetGoal(description="x", success_metrics={"revenue": 100})
    agents = _sample_agents()
    dist = build_outcome_distribution(agents, goal, domain_id="startup")
    synthesis = build_data_driven_synthesis(agents, goal, dist, domain_id="startup")
    assert synthesis.principles
    assert "平行世界" in synthesis.disclaimer
    cfs = build_data_driven_counterfactuals(agents, goal, domain_id="startup")
    assert cfs


def test_agent_diversity_changes_params():
    base = StartupParams()
    bold = apply_agent_diversity(base, AgentAttributes(risk_preference=0.95))
    cautious = apply_agent_diversity(base, AgentAttributes(risk_preference=0.05))
    assert bold.fundraise_base_prob > cautious.fundraise_base_prob
    assert bold.hire_min_post_runway < cautious.hire_min_post_runway


def test_param_overrides_applied():
    p = resolve_params(StartupParams(), {"revenue_per_user": 0.001, "unknown_key": 9})
    assert p.revenue_per_user == 0.001
