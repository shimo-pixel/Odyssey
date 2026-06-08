import asyncio
import json
import logging
import re
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from prds.agents.prompts import build_agent_system_prompt
from prds.config import Settings, get_settings
from prds.llm.model_config import configure_litellm, normalize_litellm_model
from prds.models.domain import AgentDecision, AgentState, TargetGoal, WorldState

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMStructuredOutputError(ValueError):
    """Raised when an LLM response cannot be parsed into the expected schema."""


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.llm_configured:
            raise RuntimeError(
                "LLM API key is not configured. Set OPENAI_API_KEY or DEEPSEEK_API_KEY in .env."
            )
        self._semaphore = asyncio.Semaphore(self.settings.prds_max_concurrent_llm)
        configure_litellm(self.settings)

    @property
    def api_key_available(self) -> bool:
        return self.settings.llm_configured

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
        model = normalize_litellm_model(model or self.default_model, self.settings)
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
                    choice = response.choices[0]
                    message = choice.message
                    content = message.content or getattr(message, "reasoning_content", None) or ""
                    if not content.strip():
                        finish = getattr(choice, "finish_reason", None)
                        logger.warning(
                            "LLM returned empty content (attempt %d, finish_reason=%s, model=%s)",
                            attempt + 1,
                            finish,
                            model,
                        )
                        raise LLMStructuredOutputError("LLM returned empty content")
                    return content
                except LLMStructuredOutputError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
                except Exception as exc:
                    logger.warning("LLM call failed (attempt %d): %s", attempt + 1, exc)
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.5 * (attempt + 1))
        raise LLMStructuredOutputError("LLM returned no content after retries")

    @staticmethod
    def _extract_json_blob(text: str) -> str | None:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            if start == -1:
                continue
            depth = 0
            in_string = False
            escape = False
            for index, char in enumerate(text[start:], start=start):
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        return text[start : index + 1]
        return None

    @classmethod
    def _parse_json(cls, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise LLMStructuredOutputError("Empty LLM response")

        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            blob = cls._extract_json_blob(text)
            if not blob:
                raise
            parsed = json.loads(blob)

        if not isinstance(parsed, dict):
            raise LLMStructuredOutputError(f"Expected JSON object, got {type(parsed).__name__}")
        return parsed

    async def structured_complete(
        self,
        system: str,
        user: str,
        model_class: type[T],
        model: str | None = None,
    ) -> T:
        schema_hint = json.dumps(model_class.model_json_schema(), ensure_ascii=False)
        full_system = (
            f"{system}\n\nRespond with valid JSON only — no markdown fences or commentary.\n"
            f"Schema:\n{schema_hint}"
        )
        repair_user = user
        last_error: Exception | None = None
        last_raw = ""

        for attempt in range(3):
            try:
                raw = await self.complete(
                    full_system,
                    repair_user,
                    model=model,
                    response_format={"type": "json_object"},
                )
                last_raw = raw
                data = self._parse_json(raw)
                return model_class.model_validate(data)
            except (json.JSONDecodeError, LLMStructuredOutputError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "Failed to parse LLM JSON (attempt %d/3): %s; raw=%r",
                    attempt + 1,
                    exc,
                    (last_raw[:500] + "...") if len(last_raw) > 500 else last_raw,
                )

            repair_user = (
                f"{user}\n\n"
                "Your previous reply was invalid or empty. "
                "Return ONLY one JSON object matching the schema. No markdown."
            )
            if attempt < 2:
                await asyncio.sleep(0.75 * (attempt + 1))

        raise LLMStructuredOutputError(
            f"Could not parse LLM JSON after 3 attempts: {last_error}; "
            f"last raw={last_raw[:500]!r}"
        ) from last_error

    async def decide(
        self,
        agent: AgentState,
        world: WorldState,
        goal: TargetGoal,
        model: str | None = None,
        *,
        domain_id: str = "startup",
    ) -> AgentDecision:
        from prds.domains.registry import get_domain_profile

        profile = get_domain_profile(domain_id)
        system = profile.build_system_prompt(agent.strategy_type.value)
        decision_context = profile.build_decision_context(agent, world, goal)
        user_payload = {
            "domain_id": domain_id,
            "goal": goal.model_dump(),
            "decision_context": decision_context,
            "period": world.period,
            "total_periods": world.total_periods,
            "world_state": world.model_dump(),
            "agent_resources": agent.resources.model_dump(),
            "agent_attributes": agent.attributes.model_dump(),
            "recent_timeline": [
                {
                    **e.model_dump(),
                    "financials": e.result.financials.model_dump(),
                    "period_summary": e.result.period_summary,
                    "goal_status": e.goal_status.model_dump(),
                }
                for e in agent.timeline[-3:]
            ],
        }
        user = json.dumps(user_payload, ensure_ascii=False, indent=2)
        return await self.structured_complete(system, user, AgentDecision, model=model)
