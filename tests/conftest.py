import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from prds.config import get_settings


def _llm_response_for_messages(messages: list[dict]) -> str:
    system = messages[0]["content"].lower()

    if "community summarizer" in system or "world background that will drive" in system:
        return json.dumps(
            {
                "summary": "Test world background for simulation events.",
                "community_summaries": ["Market dynamics", "Org context", "Resource constraints"],
            }
        )

    if "event planner" in system or "simulation event" in system:
        return json.dumps(
            {
                "narrative_arc": "Early uncertainty, mid competition, late funding",
                "events": [
                    {
                        "period": 1,
                        "event_type": "policy_support",
                        "category": "macro",
                        "impact": 0.3,
                        "severity": 0.5,
                        "probability": 0.7,
                        "description": "政策支持相关行业",
                    },
                    {
                        "period": 2,
                        "event_type": "competitor_entry",
                        "category": "market",
                        "impact": -0.25,
                        "severity": 0.6,
                        "probability": 0.8,
                        "description": "新竞争对手进入市场",
                    },
                ],
            }
        )

    if "counterfactual" in system:
        return json.dumps(
            {
                "comparisons": [
                    {
                        "period": 1,
                        "decision_a": "Fundraise",
                        "outcome_a": "Secured capital",
                        "decision_b": "Product development",
                        "outcome_b": "Better product",
                        "difference": "Fundraise prioritized survival",
                    }
                ]
            }
        )

    if "strategy synthesis" in system or "recommended_roadmap" in system:
        return json.dumps(
            {
                "principles": ["Preserve runway early"],
                "key_turning_points": ["Period 1 fundraise"],
                "success_factors": ["Balanced risk management"],
                "failure_avoidance_factors": ["Avoid over-hiring"],
                "recommended_roadmap": ["Phase 1: stabilize", "Phase 2: scale"],
            }
        )

    if "graphrag entity extraction" in system:
        return json.dumps(
            {
                "entities": [
                    {"name": "TestOrg", "entity_type": "organization", "description": "Main org"},
                    {"name": "TestProduct", "entity_type": "product", "description": "Core product"},
                    {"name": "Market", "entity_type": "market", "description": "Target market"},
                ],
                "relationships": [
                    {
                        "source": "TestOrg",
                        "target": "TestProduct",
                        "relation_type": "owns",
                        "description": "owns product",
                    }
                ],
            }
        )

    if "ontology extraction" in system or "extract structured entities" in system:
        return json.dumps(
            {
                "entities": [
                    {"id": "e1", "entity_type": "organization", "name": "TestOrg", "properties": {}},
                    {"id": "e2", "entity_type": "product", "name": "TestProduct", "properties": {}},
                    {"id": "e3", "entity_type": "capital", "name": "Cash", "properties": {}},
                    {"id": "e4", "entity_type": "market", "name": "Market", "properties": {}},
                    {"id": "e5", "entity_type": "time", "name": "Timeline", "properties": {}},
                ],
                "relations": [
                    {"source_id": "e1", "target_id": "e2", "relation_type": "owns"},
                    {"source_id": "e1", "target_id": "e3", "relation_type": "owns"},
                    {"source_id": "e2", "target_id": "e4", "relation_type": "depends_on"},
                ],
                "risks": ["cash burn"],
                "opportunities": ["market growth"],
                "constraints": ["limited runway"],
                "targets": ["reach goal"],
            }
        )

    if "domain research analyst" in system:
        return json.dumps(
            {
                "report": "## 行业背景\n该领域竞争激烈，典型毛利 30-50%，获客成本较高。\n常见高概率事件：季节性需求波动、平台规则调整、人力流动。",
                "key_findings": ["毛利区间 30-50%", "获客成本偏高", "季节性需求波动常见"],
            }
        )

    if "intake analyst" in system:
        return json.dumps(
            {
                "background": "扩充后的现状描述。",
                "goal": "明确且可衡量的目标。",
                "constraints": ["约束一", "约束二"],
                "risks": ["风险一", "风险二"],
                "opportunities": ["机会一"],
                "success_metrics": {"cash": 100, "revenue": 20},
                "assumptions": ["推断的背景假设"],
                "open_questions": ["需要补充的问题"],
                "notes": "已扩充并结构化输入。",
            }
        )

    if "decision-maker" in system or "decision_maker" in system:
        return json.dumps(
            {
                "thought": "Focus on product development this period",
                "reasoning": "Runway is sufficient and product maturity is low",
                "decision": "Invest in product development",
                "action": "product_dev",
                "action_params": {"investment": 5.0},
            }
        )

    if "respond with valid json" in system:
        return json.dumps(
            {
                "thought": "Hold position",
                "reasoning": "Observe market conditions",
                "decision": "hold",
                "action": "hold",
                "action_params": {},
            }
        )

    return json.dumps({"summary": "Generic test response"})


@pytest.fixture(autouse=True)
def llm_test_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()

    async def fake_acompletion(*, model, messages, **kwargs):
        content = _llm_response_for_messages(messages)
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
