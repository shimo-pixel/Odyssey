"""Multi-model catalog HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from prds.kb.settings_store import (
    LlmModelCreate,
    LlmModelsCatalogPublic,
    SetDefaultModel,
    add_llm_model,
    delete_llm_model,
    list_llm_models,
    set_default_llm_model,
)

router = APIRouter(prefix="/llm-models", tags=["llm-models"])


@router.get("", response_model=LlmModelsCatalogPublic)
async def get_llm_models() -> LlmModelsCatalogPublic:
    return await list_llm_models()


@router.post("", response_model=LlmModelsCatalogPublic)
async def create_llm_model(payload: LlmModelCreate) -> LlmModelsCatalogPublic:
    if not payload.model.strip():
        raise HTTPException(status_code=422, detail="model required")
    if not payload.api_key.strip():
        raise HTTPException(status_code=422, detail="api_key required")
    return await add_llm_model(payload)


@router.delete("/{model_id}", response_model=LlmModelsCatalogPublic)
async def remove_llm_model(model_id: str) -> LlmModelsCatalogPublic:
    return await delete_llm_model(model_id)


@router.put("/default", response_model=LlmModelsCatalogPublic)
async def put_default_model(payload: SetDefaultModel) -> LlmModelsCatalogPublic:
    try:
        return await set_default_llm_model(payload.model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="model not found") from exc
