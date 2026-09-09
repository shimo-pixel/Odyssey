"""LLM settings HTTP API."""

from __future__ import annotations

from fastapi import APIRouter

from prds.kb.settings_store import (
    LlmSettingsPublic,
    LlmSettingsUpdate,
    public_llm_settings,
    save_llm_settings,
)

router = APIRouter(prefix="/llm-settings", tags=["llm-settings"])


@router.get("", response_model=LlmSettingsPublic)
async def get_llm_settings() -> LlmSettingsPublic:
    return await public_llm_settings()


@router.put("", response_model=LlmSettingsPublic)
async def put_llm_settings(payload: LlmSettingsUpdate) -> LlmSettingsPublic:
    return await save_llm_settings(payload)
