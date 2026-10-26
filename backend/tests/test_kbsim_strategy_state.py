"""Batched strategy generation and per-branch state prediction."""

import pytest

from prds.config import Settings
from prds.kbsim.branches import rationality_split
from prds.kbsim.state import (
    baseline_state,
    compute_goal_status,
    predict_state,
    render_baseline_snapshot,
    render_state_snapshot,
)
from prds.kbsim.strategies import generate_strategies, rationality_counts
from prds.llm.client import LLMClient
from prds.models.domain import (
    BranchProfile,
    Event,
    EventCategory,
    MetricReading,
    MetricSpec,
    Rationality,
    StrategyOption,
    TargetGoal,
)

SPECS = [
    MetricSpec(name="数学成绩", unit="分", baseline=62.0, target=78.0),
    MetricSpec(name="每周学习小时", unit="小时", baseline=6.0, target=10.0),
]


def _settings() -> Settings:
    return Settings(openai_api_key="test-key")


def _branches(count: int = 4) -> list[BranchProfile]:
    return [
        BranchProfile(
            branch_id=f"branch_{i:02d}",
            label=f"策略 {i}",
            index=i,
            rationality=rationality,
            persona="测试档案",
        )
        for i, rationality in enumerate(rationality_split(count, 0.7), start=1)
    ]


def _event() -> Event:
    return Event(
        event_id="evt_001",
        event_type="quiz_difficulty_up",
        category=EventCategory.ORG,
        impact=-0.2,
        probability=0.6,
        severity=0.4,
        description="单元测验难度上升",
        evidence=["第 3 次测验平均分下降"],
    )


def _goal() -> TargetGoal:
    return TargetGoal(description="一年内把数学提到 78 分")


async def _strategies(branches, llm=None):
    return await generate_strategies(
        llm or LLMClient(_settings()),
        event=_event(),
        event_index=1,
        total_events=6,
        goal=_goal(),
        branches=branches,
        metric_specs=SPECS,
        contexts={b.branch_id: "知识库上下文" for b in branches},
        last_states={},
    )


async def test_generate_strategies_returns_one_per_branch():
    branches = _branches(4)

    strategies = await _strategies(branches)

    assert set(strategies) == {b.branch_id for b in branches}
    assert all(s.title and s.action_label for s in strategies.values())
    assert len({s.title for s in strategies.values()}) == len(branches)
    assert all(len(s.action_label) <= 12 for s in strategies.values())


async def test_generate_strategies_keeps_the_branch_rationality_authoritative():
    branches = _branches(5)

    strategies = await _strategies(branches)

    for branch in branches:
        assert strategies[branch.branch_id].rationality is branch.rationality
    rational, irrational = rationality_counts(branches)
    assert rational > irrational >= 1


async def test_generate_strategies_uses_one_call_for_all_branches(monkeypatch):
    llm = LLMClient(_settings())
    calls: list[str] = []
    original = llm.structured_complete

    async def counting(system, user, model_class, model=None):
        calls.append(system[:20])
        return await original(system, user, model_class, model=model)

    monkeypatch.setattr(llm, "structured_complete", counting)

    await _strategies(_branches(6), llm=llm)

    assert len(calls) == 1


async def test_generate_strategies_stops_when_the_model_fails(monkeypatch):
    llm = LLMClient(_settings())

    async def boom(system, user, model_class, model=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "structured_complete", boom)
    branches = _branches(3)

    from prds.simulation.errors import SimulationFailure
    with pytest.raises(SimulationFailure):
        await _strategies(branches, llm=llm)


def test_compute_goal_status_averages_metric_progress():
    readings = [
        MetricReading(name="数学成绩", value=70.0, previous=62.0),
        MetricReading(name="每周学习小时", value=10.0, previous=6.0),
    ]

    status = compute_goal_status(readings, SPECS)

    assert status.metric_progress["数学成绩"] == pytest.approx(0.5)
    assert status.metric_progress["每周学习小时"] == pytest.approx(1.0)
    assert status.progress == pytest.approx(0.75)
    assert set(status.model_dump()) == {"progress", "metric_progress"}


def test_compute_goal_status_clamps_and_ignores_unknown_metrics():
    status = compute_goal_status(
        [
            MetricReading(name="数学成绩", value=200.0),
            MetricReading(name="不在指标里的东西", value=1.0),
        ],
        SPECS,
    )

    assert status.progress == pytest.approx(1.0)
    assert "不在指标里的东西" not in status.metric_progress


def test_baseline_state_starts_at_zero_progress():
    branch = _branches(1)[0]

    state = baseline_state(branch, SPECS, "起始处境")

    assert state.goal_status.progress == 0.0
    assert [m.value for m in state.metrics] == [62.0, 6.0]
    assert all(m.value == m.previous for m in state.metrics)


async def test_predict_state_fills_every_tracked_metric():
    branch = _branches(1)[0]
    previous = baseline_state(branch, SPECS, "起始处境")
    strategy = StrategyOption(
        branch_id=branch.branch_id, title="定向训练错题", rationality=branch.rationality
    )

    state = await predict_state(
        LLMClient(_settings()),
        branch=branch,
        event=_event(),
        event_index=1,
        total_events=6,
        strategy=strategy,
        previous=previous,
        specs=SPECS,
        goal=_goal(),
        context="知识库上下文",
    )

    assert [m.name for m in state.metrics] == [s.name for s in SPECS]
    assert all(m.unit for m in state.metrics)
    assert all(m.previous == prev.value for m, prev in zip(state.metrics, previous.metrics))
    assert state.narrative
    assert 0.0 <= state.confidence <= 1.0
    assert state.goal_status.progress > 0


async def test_predict_state_stops_when_prediction_fails(monkeypatch):
    llm = LLMClient(_settings())

    async def boom(system, user, model_class, model=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "structured_complete", boom)
    branch = _branches(1)[0]
    previous = baseline_state(branch, SPECS, "起始处境")

    from prds.simulation.errors import SimulationFailure
    with pytest.raises(SimulationFailure):
        await predict_state(
            llm,
            branch=branch,
            event=_event(),
            event_index=1,
            total_events=6,
            strategy=StrategyOption(branch_id=branch.branch_id, title="维持现状"),
            previous=previous,
            specs=SPECS,
            goal=_goal(),
            context="",
        )


def test_state_snapshot_is_self_describing_and_compact():
    branch = _branches(1)[0]
    state = baseline_state(branch, SPECS, "起始处境")
    state.metrics[0].value = 70.0
    state.metrics[0].reason = "错题复盘见效"
    state.risks = ["其他科目被挤压"]
    state.side_effects = ["睡眠减少"]

    snapshot = render_state_snapshot(
        branch=branch,
        goal=_goal(),
        event=_event(),
        event_index=2,
        strategy=StrategyOption(branch_id=branch.branch_id, title="定向训练错题"),
        state=state,
    )

    assert "数学成绩：70 分" in snapshot
    assert "此前 62 分" in snapshot and "上升 8" in snapshot
    assert "错题复盘见效" in snapshot
    assert "其他科目被挤压" in snapshot and "睡眠减少" in snapshot
    assert "取代之前的状态记录" in snapshot
    assert len(snapshot) < 2000


def test_baseline_snapshot_lists_start_and_target_values():
    snapshot = render_baseline_snapshot(
        goal=_goal(), background="数学 62 分", specs=SPECS, constraints=["时间有限"]
    )

    assert "当前 62 分，目标 78 分" in snapshot
    assert "时间有限" in snapshot


@pytest.mark.parametrize('invalid_kind', ['missing', 'renamed', 'duplicate', 'blank_reason', 'blank_narrative'])
@pytest.mark.parametrize('recovers', [True, False])
async def test_prediction_retries_incomplete_output(monkeypatch, invalid_kind, recovers):
    import copy
    import json
    from unittest.mock import AsyncMock
    from prds.simulation.errors import SimulationFailure

    valid = {
        'narrative': '状态发生变化',
        'metrics': [{'name': s.name, 'value': 70, 'reason': '训练见效'} for s in SPECS],
        'confidence': 0.7, 'success': False,
    }
    invalid = copy.deepcopy(valid)
    if invalid_kind == 'missing':
        invalid['metrics'].pop()
    elif invalid_kind == 'renamed':
        invalid['metrics'][0]['name'] = '改名后的指标'
    elif invalid_kind == 'duplicate':
        invalid['metrics'][1]['name'] = invalid['metrics'][0]['name']
    elif invalid_kind == 'blank_reason':
        invalid['metrics'][0]['reason'] = '   '
    else:
        invalid['narrative'] = '   '
    replies = [invalid, valid] if recovers else [invalid] * 3
    llm = LLMClient(_settings())
    complete = AsyncMock(side_effect=[json.dumps(v, ensure_ascii=False) for v in replies])
    monkeypatch.setattr(llm, 'complete', complete)
    monkeypatch.setattr('prds.llm.client.asyncio.sleep', AsyncMock())
    branch = _branches(1)[0]
    kwargs = dict(branch=branch, event=_event(), event_index=4, total_events=6,
                  strategy=StrategyOption(branch_id=branch.branch_id, title='测试策略'),
                  previous=baseline_state(branch, SPECS, '起点'), specs=SPECS,
                  goal=_goal(), context='')
    if recovers:
        state = await predict_state(llm, **kwargs)
        assert [m.name for m in state.metrics] == [s.name for s in SPECS]
        assert complete.await_count == 2
    else:
        with pytest.raises(SimulationFailure) as error:
            await predict_state(llm, **kwargs)
        assert error.value.issue.event_index == 4
        assert error.value.issue.stage == 'prediction'
        assert complete.await_count == 3
