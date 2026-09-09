"""Offline test harness: a scripted LLM plus helpers for faking LightRAG.

Every kbsim stage is dispatched by a distinctive phrase from its system prompt,
and the reply is derived from the payload the stage actually sent, so the fake
model stays consistent with prompts as they evolve (branch ids, metric names and
requested event counts all come back from the request itself).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from prds.config import get_settings


def _payload_of(user: str) -> dict:
    start = user.find("{")
    if start == -1:
        return {}
    try:
        return json.loads(user[start:])
    except json.JSONDecodeError:
        return {}


def _intake_reply(payload: dict) -> dict:
    declared = payload.get("declared_success_metrics") or {}
    specs = [
        {
            "name": name,
            "unit": "分",
            "direction": "up",
            "baseline": 60.0,
            "target": float(target),
        }
        for name, target in declared.items()
        if isinstance(target, (int, float))
    ]
    if not specs:
        specs = [
            {
                "name": "数学成绩",
                "unit": "分",
                "direction": "up",
                "baseline": 62.0,
                "target": 78.0,
            }
        ]
    return {
        "background": "学生目前数学 62 分，作业按时完成但错题复盘不足。",
        "constraints": ["每天可支配学习时间 2 小时"],
        "risks": ["错题重复出现"],
        "opportunities": ["班主任愿意提供额外辅导"],
        "metric_specs": specs,
        "notes": "已从知识库读出起始指标。",
    }


def _event_plan_reply(payload: dict, *, black_swan: bool) -> dict:
    count = max(0, int(payload.get("event_count_required") or 0))
    events = []
    for index in range(1, count + 1):
        events.append(
            {
                "event_type": f"{'shock' if black_swan else 'situation'}_{index}",
                "category": "org",
                "description": (
                    f"{'突发转折' if black_swan else '处境变化'} {index}：单元测验难度上升。"
                ),
                "impact": -0.2 if index % 2 else 0.2,
                "probability": 0.1 if black_swan else 0.6,
                "severity": 0.8 if black_swan else 0.4,
                "evidence": [f"知识库记录：第 {index} 次测验成绩"],
            }
        )
    return {"events": events, "timeline_note": "按测验节奏推进"}


def _strategy_reply(payload: dict) -> dict:
    branches = payload.get("branches") or []
    return {
        "strategies": [
            {
                "branch_id": branch.get("branch_id", ""),
                "title": f"{branch.get('label', '')}：针对错题做定向训练",
                "action_label": f"策略{position}",
                "detail": "每天挑 5 道同类错题重做并讲一遍思路。",
                "rationale": "错题复盘不足是当前主要缺口。",
                "rationality": branch.get("rationality", "rational"),
            }
            for position, branch in enumerate(branches, start=1)
        ]
    }


def _state_reply(payload: dict) -> dict:
    specs = payload.get("metrics_to_predict") or []
    before = (payload.get("state_before") or {}).get("metrics") or {}
    irrational = (payload.get("chosen_strategy") or {}).get("rationality") == "irrational"
    step = 6.0 if irrational else 3.0
    return {
        "narrative": "错题重做后同类题正确率提高，课堂参与度略有上升。",
        "metrics": [
            {
                "name": spec.get("name", ""),
                "value": float(before.get(spec.get("name"), spec.get("baseline", 0.0)))
                + step,
                "reason": "定向训练带来的小幅提升。",
            }
            for spec in specs
        ],
        "risks": ["其他科目投入被挤压"],
        "side_effects": ["睡眠时间减少"] if irrational else [],
        "confidence": 0.6,
        "success": True,
    }


def _synthesis_reply(payload: dict) -> dict:
    trace = payload.get("trace") or []
    indexes = sorted({entry.get("event_index", 1) for entry in trace})[:2]
    return {
        "principles": ["先补最薄弱的环节", "每轮只改一个变量"],
        "key_turning_points": [f"第 {i} 个事件" for i in indexes] or ["第 1 个事件"],
        "success_factors": ["持续复盘"],
        "failure_avoidance_factors": ["避免临时加码"],
        "recommended_roadmap": ["第一步：建立错题本", "第二步：每周复盘一次"],
        "counterfactuals": [
            {
                "event_index": indexes[0] if indexes else 1,
                "decision_a": "定向训练错题",
                "outcome_a": "同类题正确率提升",
                "decision_b": "增加刷题总量",
                "outcome_b": "疲劳但提升有限",
                "difference": "针对性决定了效率",
            }
        ],
    }


def llm_reply_for(system: str, user: str) -> str:
    """The scripted reply for one (system, user) pair."""
    payload = _payload_of(user)

    if "输入分析器" in system:
        return json.dumps(_intake_reply(payload), ensure_ascii=False)
    if "黑天鹅事件规划器" in system:
        return json.dumps(_event_plan_reply(payload, black_swan=True), ensure_ascii=False)
    if "事件规划器" in system:
        return json.dumps(_event_plan_reply(payload, black_swan=False), ensure_ascii=False)
    if "策略生成器" in system:
        return json.dumps(_strategy_reply(payload), ensure_ascii=False)
    if "状态预测器" in system:
        return json.dumps(_state_reply(payload), ensure_ascii=False)
    if "总结器" in system:
        return json.dumps(_synthesis_reply(payload), ensure_ascii=False)

    return json.dumps({"summary": "Generic test response"}, ensure_ascii=False)


@pytest.fixture(autouse=True)
def llm_test_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("PRDS_LLM_API_BASE", "")
    monkeypatch.setenv("PRDS_LLM_PROVIDER", "")
    get_settings.cache_clear()

    async def fake_acompletion(*, model, messages, **kwargs):
        content = llm_reply_for(messages[0]["content"], messages[1]["content"])
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    monkeypatch.setattr("litellm.acompletion", AsyncMock(side_effect=fake_acompletion))
    yield
    get_settings.cache_clear()
