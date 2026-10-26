"""Runtime LLM settings persistence + LightRAG .env sync + multi-model catalog."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from prds.config import Settings, get_settings, set_runtime_llm_overrides
from prds.storage.models import AppSetting
from prds.storage.repository import SimulationRepository

logger = logging.getLogger(__name__)

LLM_SETTINGS_KEY = "llm_settings"
LLM_MODELS_KEY = "llm_models"


class LlmSettingsUpdate(BaseModel):
    api_key: str | None = None
    model: str | None = None
    model_analysis: str | None = None
    api_base: str | None = None
    provider: str | None = None


class LlmSettingsPublic(BaseModel):
    model: str = ""
    model_analysis: str = ""
    api_base: str = ""
    provider: str = ""
    api_key_masked: str = ""
    configured: bool = False
    lightrag_restart_hint: str = "Restart LightRAG after changing LLM settings for the knowledge base."


class LlmModelCreate(BaseModel):
    name: str = ""
    provider: str = "openai"
    model: str = Field(..., min_length=1)
    api_base: str = ""
    api_key: str = Field(..., min_length=1)
    model_analysis: str = ""


class LlmModelPublic(BaseModel):
    id: str
    name: str = ""
    provider: str = ""
    model: str = ""
    api_base: str = ""
    model_analysis: str = ""
    api_key_masked: str = ""
    created_at: str | None = None
    is_default: bool = False


class LlmModelsCatalogPublic(BaseModel):
    models: list[LlmModelPublic] = Field(default_factory=list)
    default_model_id: str | None = None


class SetDefaultModel(BaseModel):
    model_id: str


_repo: SimulationRepository | None = None


def _get_repo() -> SimulationRepository:
    global _repo
    if _repo is None:
        _repo = SimulationRepository()
    return _repo


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}***{key[-4:]}"


def lightrag_workdir() -> Path:
    path = Path("data/lightrag")
    path.mkdir(parents=True, exist_ok=True)
    (path / "inputs").mkdir(exist_ok=True)
    (path / "rag_storage").mkdir(exist_ok=True)
    return path


async def load_llm_overrides() -> dict[str, Any]:
    repo = _get_repo()
    async with repo.session_factory() as session:
        row = await session.get(AppSetting, LLM_SETTINGS_KEY)
        if row is None:
            return {}
        try:
            data = json.loads(row.value_json)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def apply_overrides_to_settings(settings: Settings, overrides: dict[str, Any]) -> Settings:
    data = settings.model_dump()
    if overrides.get("api_key"):
        key = overrides["api_key"]
        api_base = (overrides.get("api_base") or settings.prds_llm_api_base or "").lower()
        if "deepseek" in api_base or (overrides.get("model") or "").lower().startswith("deepseek"):
            data["deepseek_api_key"] = key
            if not data.get("openai_api_key"):
                data["openai_api_key"] = ""
        else:
            data["openai_api_key"] = key
    if overrides.get("model"):
        data["prds_llm_model"] = overrides["model"]
    if overrides.get("model_analysis"):
        data["prds_llm_model_analysis"] = overrides["model_analysis"]
    if overrides.get("api_base") is not None:
        data["prds_llm_api_base"] = overrides["api_base"]
    if overrides.get("provider") is not None:
        data["prds_llm_provider"] = overrides["provider"]
    return Settings(**data)


async def get_effective_settings() -> Settings:
    base = get_settings()
    overrides = await load_llm_overrides()
    if not overrides:
        return base
    return apply_overrides_to_settings(base, overrides)


def sync_lightrag_env(overrides: dict[str, Any], base: Settings) -> None:
    env_path = lightrag_workdir() / ".env"
    if not env_path.exists():
        env_path.write_text(
            "HOST=0.0.0.0\nPORT=9621\nLIGHTRAG_API_PREFIX=/lightrag\n",
            encoding="utf-8",
        )

    api_key = overrides.get("api_key") or base.deepseek_api_key or base.openai_api_key
    model = overrides.get("model") or base.prds_llm_model
    api_base = overrides.get("api_base") or base.prds_llm_api_base or ""
    provider = overrides.get("provider") or base.prds_llm_provider or "openai"

    updates = {
        "LLM_BINDING": provider or "openai",
        "LLM_MODEL": model,
    }
    if api_key:
        updates["LLM_BINDING_API_KEY"] = api_key
        updates["OPENAI_API_KEY"] = api_key
    if api_base:
        updates["LLM_BINDING_HOST"] = api_base.rstrip("/")

    text = env_path.read_text(encoding="utf-8")
    existing_keys = set()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        existing_keys.add(line.partition("=")[0].strip())

    # Branch simulation fans out concurrent inserts/queries across workspaces;
    # LightRAG's stock concurrency is too low to keep up. Seeded once so a
    # hand-tuned value in the .env is never overwritten.
    for key, value in (
        ("MAX_ASYNC", "16"),
        ("MAX_PARALLEL_INSERT", "8"),
        ("EMBEDDING_FUNC_MAX_ASYNC", "16"),
    ):
        if key not in existing_keys:
            updates[key] = value

    if "EMBEDDING_BINDING" not in existing_keys:
        updates["EMBEDDING_BINDING"] = "openai"
        updates["EMBEDDING_MODEL"] = "text-embedding-3-small"
        updates["EMBEDDING_DIM"] = "1536"
        updates["EMBEDDING_SEND_DIM"] = "false"
        if api_key:
            updates["EMBEDDING_BINDING_API_KEY"] = api_key
        if api_base and "deepseek" not in api_base.lower():
            updates["EMBEDDING_BINDING_HOST"] = api_base.rstrip("/")
        else:
            updates["EMBEDDING_BINDING_HOST"] = "https://api.openai.com/v1"

    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        k, _, _ = line.partition("=")
        k = k.strip()
        if k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


async def public_llm_settings() -> LlmSettingsPublic:
    base = get_settings()
    overrides = await load_llm_overrides()
    effective = apply_overrides_to_settings(base, overrides) if overrides else base
    key = overrides.get("api_key") or effective.deepseek_api_key or effective.openai_api_key
    return LlmSettingsPublic(
        model=effective.prds_llm_model,
        model_analysis=effective.prds_llm_model_analysis,
        api_base=effective.prds_llm_api_base,
        provider=effective.prds_llm_provider,
        api_key_masked=mask_key(key),
        configured=bool(key),
    )


async def save_llm_settings(payload: LlmSettingsUpdate) -> LlmSettingsPublic:
    current = await load_llm_overrides()
    data = {**current}
    if payload.api_key is not None and payload.api_key.strip():
        data["api_key"] = payload.api_key.strip()
    if payload.model is not None:
        data["model"] = payload.model.strip()
    if payload.model_analysis is not None:
        data["model_analysis"] = payload.model_analysis.strip()
    if payload.api_base is not None:
        data["api_base"] = payload.api_base.strip()
    if payload.provider is not None:
        data["provider"] = payload.provider.strip()

    repo = _get_repo()
    async with repo.session_factory() as session:
        row = await session.get(AppSetting, LLM_SETTINGS_KEY)
        if row is None:
            row = AppSetting(key=LLM_SETTINGS_KEY, value_json=json.dumps(data))
            session.add(row)
        else:
            row.value_json = json.dumps(data)
        await session.commit()

    set_runtime_llm_overrides(data)
    base = get_settings()
    try:
        sync_lightrag_env(data, base)
    except Exception as exc:
        logger.warning("Failed to sync LightRAG .env: %s", exc)

    await _ensure_catalog_seeded(force_from_overrides=data)
    return await public_llm_settings()


def _display_name(entry: dict[str, Any]) -> str:
    name = (entry.get("name") or "").strip()
    if name:
        return name
    model = (entry.get("model") or "").strip()
    provider = (entry.get("provider") or "").strip()
    if provider and model:
        return f"{provider}/{model}"
    return model or provider or "model"


def _public_entry(entry: dict[str, Any], default_id: str | None) -> LlmModelPublic:
    eid = str(entry.get("id") or "")
    return LlmModelPublic(
        id=eid,
        name=_display_name(entry),
        provider=str(entry.get("provider") or ""),
        model=str(entry.get("model") or ""),
        api_base=str(entry.get("api_base") or ""),
        model_analysis=str(entry.get("model_analysis") or ""),
        api_key_masked=mask_key(str(entry.get("api_key") or "")),
        created_at=entry.get("created_at"),
        is_default=bool(default_id and eid == default_id),
    )


async def _load_catalog_raw() -> dict[str, Any]:
    repo = _get_repo()
    async with repo.session_factory() as session:
        row = await session.get(AppSetting, LLM_MODELS_KEY)
        if row is None:
            return {"models": [], "default_model_id": None}
        try:
            data = json.loads(row.value_json)
            if not isinstance(data, dict):
                return {"models": [], "default_model_id": None}
            models = data.get("models")
            if not isinstance(models, list):
                models = []
            return {
                "models": [m for m in models if isinstance(m, dict)],
                "default_model_id": data.get("default_model_id"),
            }
        except json.JSONDecodeError:
            return {"models": [], "default_model_id": None}


async def _save_catalog_raw(data: dict[str, Any]) -> None:
    repo = _get_repo()
    payload = json.dumps(
        {
            "models": data.get("models") or [],
            "default_model_id": data.get("default_model_id"),
        }
    )
    async with repo.session_factory() as session:
        row = await session.get(AppSetting, LLM_MODELS_KEY)
        if row is None:
            session.add(AppSetting(key=LLM_MODELS_KEY, value_json=payload))
        else:
            row.value_json = payload
        await session.commit()


def _overrides_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_key": entry.get("api_key") or "",
        "model": entry.get("model") or "",
        "model_analysis": entry.get("model_analysis") or entry.get("model") or "",
        "api_base": entry.get("api_base") or "",
        "provider": entry.get("provider") or "openai",
    }


async def apply_default_model_runtime() -> None:
    catalog = await _ensure_catalog_seeded()
    default_id = catalog.get("default_model_id")
    models = catalog.get("models") or []
    entry = next((m for m in models if m.get("id") == default_id), None)
    if entry is None and models:
        entry = models[0]
        catalog["default_model_id"] = entry.get("id")
        await _save_catalog_raw(catalog)
    if not entry:
        return
    data = _overrides_from_entry(entry)
    repo = _get_repo()
    async with repo.session_factory() as session:
        row = await session.get(AppSetting, LLM_SETTINGS_KEY)
        if row is None:
            session.add(AppSetting(key=LLM_SETTINGS_KEY, value_json=json.dumps(data)))
        else:
            row.value_json = json.dumps(data)
        await session.commit()
    set_runtime_llm_overrides(data)
    try:
        sync_lightrag_env(data, get_settings())
    except Exception as exc:
        logger.warning("Failed to sync LightRAG .env from catalog: %s", exc)


async def _ensure_catalog_seeded(
    force_from_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog = await _load_catalog_raw()
    models: list[dict[str, Any]] = list(catalog.get("models") or [])
    if models and not force_from_overrides:
        default_id = catalog.get("default_model_id")
        if not default_id or not any(m.get("id") == default_id for m in models):
            catalog["default_model_id"] = models[0].get("id")
            await _save_catalog_raw(catalog)
        return catalog

    overrides = force_from_overrides if force_from_overrides is not None else await load_llm_overrides()
    base = get_settings()
    api_key = (overrides.get("api_key") or base.deepseek_api_key or base.openai_api_key or "").strip()
    model = (overrides.get("model") or base.prds_llm_model or "").strip()
    if not api_key or not model:
        return catalog

    if force_from_overrides and models:
        default_id = catalog.get("default_model_id")
        target = next((m for m in models if m.get("id") == default_id), models[0])
        target.update(
            {
                "provider": overrides.get("provider") or target.get("provider") or "openai",
                "model": model,
                "api_base": overrides.get("api_base") or "",
                "api_key": api_key or target.get("api_key") or "",
                "model_analysis": overrides.get("model_analysis")
                or target.get("model_analysis")
                or model,
                "name": target.get("name") or model,
            }
        )
        catalog["models"] = models
        await _save_catalog_raw(catalog)
        return catalog

    if models:
        return catalog

    entry = {
        "id": str(uuid.uuid4()),
        "name": model,
        "provider": overrides.get("provider") or base.prds_llm_provider or "openai",
        "model": model,
        "api_base": overrides.get("api_base") or base.prds_llm_api_base or "",
        "api_key": api_key,
        "model_analysis": overrides.get("model_analysis") or base.prds_llm_model_analysis or model,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    catalog = {"models": [entry], "default_model_id": entry["id"]}
    await _save_catalog_raw(catalog)
    return catalog


async def list_llm_models() -> LlmModelsCatalogPublic:
    catalog = await _ensure_catalog_seeded()
    default_id = catalog.get("default_model_id")
    models = [_public_entry(m, default_id) for m in (catalog.get("models") or [])]
    return LlmModelsCatalogPublic(models=models, default_model_id=default_id)


async def add_llm_model(payload: LlmModelCreate) -> LlmModelsCatalogPublic:
    catalog = await _ensure_catalog_seeded()
    models: list[dict[str, Any]] = list(catalog.get("models") or [])
    entry = {
        "id": str(uuid.uuid4()),
        "name": (payload.name or payload.model).strip(),
        "provider": (payload.provider or "openai").strip() or "openai",
        "model": payload.model.strip(),
        "api_base": (payload.api_base or "").strip(),
        "api_key": payload.api_key.strip(),
        "model_analysis": (payload.model_analysis or payload.model).strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    models.append(entry)
    if not catalog.get("default_model_id"):
        catalog["default_model_id"] = entry["id"]
    catalog["models"] = models
    await _save_catalog_raw(catalog)
    await apply_default_model_runtime()
    return await list_llm_models()


async def delete_llm_model(model_id: str) -> LlmModelsCatalogPublic:
    catalog = await _ensure_catalog_seeded()
    models = [m for m in (catalog.get("models") or []) if m.get("id") != model_id]
    catalog["models"] = models
    if catalog.get("default_model_id") == model_id:
        catalog["default_model_id"] = models[0]["id"] if models else None
    await _save_catalog_raw(catalog)
    if models:
        await apply_default_model_runtime()
    return await list_llm_models()


async def set_default_llm_model(model_id: str) -> LlmModelsCatalogPublic:
    catalog = await _ensure_catalog_seeded()
    models = catalog.get("models") or []
    if not any(m.get("id") == model_id for m in models):
        raise KeyError("model not found")
    catalog["default_model_id"] = model_id
    await _save_catalog_raw(catalog)
    await apply_default_model_runtime()
    return await list_llm_models()


async def get_model_entry(model_id: str | None = None, *, strict: bool = False) -> dict[str, Any] | None:
    catalog = await _ensure_catalog_seeded()
    models = catalog.get("models") or []
    if not models:
        return None
    mid = model_id or catalog.get("default_model_id")
    if mid:
        found = next((m for m in models if m.get("id") == mid), None)
        if found:
            return found
    if strict and model_id:
        return None
    return models[0]


def settings_from_model_entry(entry: dict[str, Any]) -> Settings:
    # Each selected entry owns its credentials; never inherit another model's key.
    data = get_settings().model_dump()
    data.update(openai_api_key=entry.get("api_key") or "",
                deepseek_api_key=entry.get("api_key") or "",
                prds_llm_model=entry["model"], prds_llm_model_analysis=entry["model"],
                prds_llm_api_base=entry.get("api_base") or "",
                prds_llm_provider=entry.get("provider") or "")
    return Settings(**data)
