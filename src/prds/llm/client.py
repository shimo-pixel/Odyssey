import asyncio
import json
import logging
import re
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from prds.agents.prompts import build_agent_system_prompt
from prds.config import Settings, get_settings
from prds.llm.mock_decisions import build_mock_decision
from prds.models.domain import AgentDecision, AgentState, WorldState

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(self.settings.prds_max_concurrent_llm)
        if self.settings.openai_api_key:
            litellm.api_key = self.settings.openai_api_key

    @property
    def api_key_available(self) -> bool:
        return bool(self.settings.openai_api_key)

    @property
    def default_model(self) -> str:
        return self.settings.prds_llm_model

    @property
    def analysis_model(self) -> str:
        return self.settings.prds_llm_model_analysis

    async def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        model = model or self.default_model
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if response_format:
            kwargs["response_format"] = response_format

        async with self._semaphore:
            for attempt in range(3):
                try:
                    response = await litellm.acompletion(**kwargs)
                    content = response.choices[0].message.content
                    return content or ""
                except Exception as exc:
                    logger.warning("LLM call failed (attempt %d): %s", attempt + 1, exc)
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
        return ""

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        return json.loads(text)

    async def structured_complete(
        self,
        system: str,
        user: str,
        model_class: type[T],
        model: str | None = None,
    ) -> T:
        schema_hint = json.dumps(model_class.model_json_schema(), ensure_ascii=False)
        full_system = f"{system}\n\nRespond with valid JSON matching schema:\n{schema_hint}"
        raw = await self.complete(full_system, user, model=model)
        data = self._parse_json(raw)
        return model_class.model_validate(data)

    async def decide(
        self,
        agent: AgentState,
        world: WorldState,
        goal_description: str,
        model: str | None = None,
    ) -> AgentDecision:
        system = build_agent_system_prompt(agent.strategy_type.value)
        user_payload = {
            "goal": goal_description,
            "period": world.period,
            "world_state": world.model_dump(),
            "agent_resources": agent.resources.model_dump(),
            "agent_attributes": agent.attributes.model_dump(),
            "recent_timeline": [e.model_dump() for e in agent.timeline[-3:]],
        }
        user = json.dumps(user_payload, ensure_ascii=False, indent=2)
        return await self.structured_complete(system, user, AgentDecision, model=model)


class MockLLMClient(LLMClient):
    """Deterministic mock for tests without API keys."""

    def __init__(self) -> None:
        super().__init__()
        self._call_count = 0

    @property
    def api_key_available(self) -> bool:
        return True

    async def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        self._call_count += 1
        if "ontology" in system.lower() or "entities" in system.lower():
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
        if "counterfactual" in system.lower():
            return json.dumps(
                {
                    "comparisons": [
                        {
                            "period": 1,
                            "decision_a": "Fundraise",
                            "outcome_a": "Secured capital, extended runway",
                            "decision_b": "Product development",
                            "outcome_b": "Better product but shorter runway",
                            "difference": "Fundraise prioritized survival over product depth",
                        }
                    ]
                }
            )
        if "principles" in system.lower() or "roadmap" in system.lower():
            return json.dumps(
                {
                    "principles": ["Preserve runway early", "Invest in product after PMF signals"],
                    "key_turning_points": ["Period 3 fundraise success"],
                    "success_factors": ["Balanced risk management", "Timely marketing"],
                    "failure_avoidance_factors": ["Avoid over-hiring before revenue"],
                    "recommended_roadmap": [
                        "Period 1-3: Stabilize product and reduce burn",
                        "Period 4-6: Launch marketing experiments",
                        "Period 7+: Scale proven channels",
                    ],
                }
            )
        return json.dumps(
            {
                "thought": "Generic mock response",
                "reasoning": "Fallback mock",
                "decision": "hold",
                "action": "hold",
                "action_params": {},
            }
        )

    async def decide(
        self,
        agent: AgentState,
        world: WorldState,
        goal_description: str,
        model: str | None = None,
    ) -> AgentDecision:
        return build_mock_decision(agent, world, goal_description)

    async def structured_complete(
        self,
        system: str,
        user: str,
        model_class: type[T],
        model: str | None = None,
    ) -> T:
        raw = await self.complete(system, user, model=model)
        return model_class.model_validate(self._parse_json(raw))
