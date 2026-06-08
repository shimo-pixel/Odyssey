from prds.models.domain import ResourceSnapshot, TargetGoal
from prds.simulation.elimination import compute_goal_status


def test_goal_progress_starts_at_zero_with_baseline():
    baseline = ResourceSnapshot(
        cash=100,
        users=0,
        revenue=0,
        product_maturity=0.3,
        market_share=0.05,
    )
    goal = TargetGoal(
        description="grow",
        success_metrics={"revenue": 100, "users": 100_000, "market_share": 0.2, "product_maturity": 1.0},
        baseline_snapshot=baseline,
    )
    status = compute_goal_status(baseline, goal)
    assert status.progress == 0.0


def test_goal_progress_without_baseline_was_inflated():
    """Old behavior: initial product_maturity/market_share inflated progress ~15%."""
    resources = ResourceSnapshot(
        cash=100,
        users=0,
        revenue=0,
        product_maturity=0.3,
        market_share=0.05,
    )
    goal = TargetGoal(
        description="grow",
        success_metrics={"revenue": 100, "users": 100_000, "market_share": 0.2, "product_maturity": 1.0},
    )
    status = compute_goal_status(resources, goal)
    assert 0.12 <= status.progress <= 0.16


def test_goal_progress_moves_with_relevant_metric():
    baseline = ResourceSnapshot(cash=50, revenue=0)
    goal = TargetGoal(
        description="回本并盈利",
        success_metrics={"cash": 100},
        baseline_snapshot=baseline,
    )
    at_start = compute_goal_status(baseline, goal)
    halfway = compute_goal_status(ResourceSnapshot(cash=75, revenue=0), goal)
    done = compute_goal_status(ResourceSnapshot(cash=100, revenue=0), goal)

    assert at_start.progress == 0.0
    assert 0.45 <= halfway.progress <= 0.55
    assert done.progress == 1.0
