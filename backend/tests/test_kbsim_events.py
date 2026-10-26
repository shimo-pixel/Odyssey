"""Grounded event planning, including black swan injection on long timelines."""

import pytest

from prds.config import Settings
from prds.kbsim.events import (
    black_swan_quota,
    black_swan_slots,
    event_keywords,
    plan_events,
)
from prds.kbsim.intake import IntakeBrief, build_intake_brief
from prds.llm.client import LLMClient
from prds.models.domain import (
    CurrentState,
    Event,
    EventCategory,
    MetricSpec,
    SimulationConfig,
    TargetGoal,
)

KB_CONTEXT = "知识库检索结果：期中数学 62 分，错题以函数为主。"


def _settings(**overrides) -> Settings:
    return Settings(openai_api_key="test-key", **overrides)


def _brief() -> IntakeBrief:
    return IntakeBrief(
        background="数学 62 分",
        metric_specs=[MetricSpec(name="数学成绩", unit="分", baseline=62.0, target=78.0)],
    )


def _goal() -> TargetGoal:
    return TargetGoal(description="一年内把数学提到 78 分")


@pytest.mark.parametrize(
    "total,expected",
    [(1, 0), (6, 0), (19, 0), (20, 2), (24, 2), (30, 2), (40, 3), (60, 3)],
)
def test_black_swan_quota_activates_only_on_long_timelines(total, expected):
    assert black_swan_quota(total, _settings()) == expected


def test_black_swan_quota_respects_the_configured_cap():
    settings = _settings(prds_kbsim_max_black_swans=1, prds_kbsim_black_swan_min_events=10)

    assert black_swan_quota(40, settings) == 1
    assert black_swan_quota(9, settings) == 0


def test_black_swan_slots_are_seed_deterministic():
    first = black_swan_slots(24, 2, seed=42)
    again = black_swan_slots(24, 2, seed=42)
    other = black_swan_slots(24, 2, seed=7)

    assert first == again
    assert first != other


def test_black_swan_slots_land_in_the_back_of_the_timeline():
    slots = black_swan_slots(30, 3, seed=42)

    assert len(slots) == 3
    assert slots == sorted(slots)
    assert min(slots) >= 12  # ceil(30 * 0.4)
    assert max(slots) <= 30


def test_black_swan_slots_empty_without_quota():
    assert black_swan_slots(24, 0, seed=1) == []
    assert black_swan_slots(0, 2, seed=1) == []


async def test_plan_events_short_run_has_no_black_swans():
    events = await plan_events(
        LLMClient(_settings()),
        goal=_goal(),
        brief=_brief(),
        config=SimulationConfig(max_events=6, seed=42),
        kb_context=KB_CONTEXT,
        settings=_settings(),
    )

    assert len(events) == 6
    assert not any(e.is_black_swan for e in events)
    assert all(e.evidence for e in events), "every event must cite the knowledge base"
    assert all(e.description for e in events)
    assert all(-1.0 <= e.impact <= 1.0 for e in events)


async def test_plan_events_long_run_injects_capped_black_swans():
    events = await plan_events(
        LLMClient(_settings()),
        goal=_goal(),
        brief=_brief(),
        config=SimulationConfig(max_events=24, seed=42),
        kb_context=KB_CONTEXT,
        settings=_settings(),
    )

    swans = [i for i, e in enumerate(events, start=1) if e.is_black_swan]
    assert len(events) == 24
    assert 1 <= len(swans) <= 3
    assert swans == black_swan_slots(24, len(swans), 42)
    for event in events:
        if event.is_black_swan:
            assert event.probability <= 0.2
            assert event.severity >= 0.7
            assert event.evidence


async def test_plan_events_black_swan_placement_follows_the_seed():
    async def run(seed: int) -> list[int]:
        events = await plan_events(
            LLMClient(_settings()),
            goal=_goal(),
            brief=_brief(),
            config=SimulationConfig(max_events=30, seed=seed),
            kb_context=KB_CONTEXT,
            settings=_settings(),
        )
        return [i for i, e in enumerate(events, start=1) if e.is_black_swan]

    assert await run(42) == await run(42)
    assert await run(42) != await run(2026)


async def test_plan_events_rejects_an_empty_plan(monkeypatch):
    llm = LLMClient(_settings())

    async def empty_plan(system, user, model_class, model=None):
        return model_class()

    monkeypatch.setattr(llm, "structured_complete", empty_plan)

    with pytest.raises(ValueError, match="事件规划"):
        await plan_events(
            llm,
            goal=_goal(),
            brief=_brief(),
            config=SimulationConfig(max_events=4),
            kb_context=KB_CONTEXT,
            settings=_settings(),
        )


def test_event_keywords_reuse_metric_names_and_evidence():
    event = Event(
        event_id="evt_001",
        event_type="quiz_difficulty_up",
        category=EventCategory.ORG,
        impact=-0.2,
        probability=0.6,
        severity=0.4,
        description="单元测验难度上升",
        evidence=["第 3 次测验平均分下降"],
    )

    high, low = event_keywords(event, _brief())

    assert "quiz difficulty up" in high
    assert "数学成绩" in high
    assert any("第 3 次测验" in k for k in low)
    assert len(high) == len(set(high)) and len(low) == len(set(low))


async def test_intake_brief_reads_metrics_from_the_knowledge_base():
    brief = await build_intake_brief(
        LLMClient(_settings()),
        goal=_goal(),
        current_state=CurrentState(background=""),
        kb_context=KB_CONTEXT,
    )

    assert brief.background
    assert brief.metric_specs
    spec = brief.metric_specs[0]
    assert spec.name and spec.target != spec.baseline


async def test_intake_brief_rejects_missing_required_outputs(monkeypatch):
    llm = LLMClient(_settings())

    async def blank(system, user, model_class, model=None):
        return model_class()

    monkeypatch.setattr(llm, "structured_complete", blank)

    with pytest.raises(ValueError):
        await build_intake_brief(
            llm,
            goal=TargetGoal(description="提升数学", success_metrics={"数学成绩": 78}),
            current_state=CurrentState(background="现状", constraints=["时间有限"]),
            kb_context="",
        )
