from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

# Populated from SQLite at startup / when settings are saved (sync merge into get_settings).
_runtime_llm_overrides: dict[str, Any] = {}


def set_runtime_llm_overrides(overrides: dict[str, Any] | None) -> None:
    global _runtime_llm_overrides
    _runtime_llm_overrides = dict(overrides or {})
    get_settings.cache_clear()


def get_runtime_llm_overrides() -> dict[str, Any]:
    return dict(_runtime_llm_overrides)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    prds_llm_model: str = "gpt-4o-mini"
    prds_llm_model_analysis: str = "gpt-4o"
    prds_llm_provider: str = ""
    prds_llm_api_base: str = ""
    prds_max_concurrent_llm: int = 20
    prds_default_agent_count: int = 4
    prds_default_max_events: int = 6

    # --- KB branch simulation (kbsim) ---
    prds_kbsim_rational_ratio: float = 0.7
    prds_kbsim_black_swan_min_events: int = 20
    prds_kbsim_black_swan_ratio: float = 0.08
    prds_kbsim_max_black_swans: int = 3
    prds_kbsim_max_steps: int = 200
    prds_kbsim_max_concurrent_branches: int = 8
    prds_kbsim_max_fork_bytes: int = 512 * 1024 * 1024
    prds_kbsim_reindex_every: int = 1
    # 0 means wait until indexing finishes, with no overall deadline.
    prds_kbsim_index_timeout_s: float = 0.0
    prds_kbsim_retrieval_chars: int = 6000
    prds_kbsim_research: bool = False
    prds_kbsim_keep_branches: bool = True
    prds_database_url: str = "sqlite+aiosqlite:///./prds.db"
    prds_logs_dir: str = "./data/logs"
    prds_kb_upload_dir: str = "./data/kb"
    prds_lightrag_url: str = "http://127.0.0.1:9621"

    @property
    def logs_path(self) -> Path:
        path = Path(self.prds_logs_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def kb_upload_path(self) -> Path:
        path = Path(self.prds_kb_upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key or self.deepseek_api_key)


def _apply_runtime_overrides(settings: Settings) -> Settings:
    overrides = _runtime_llm_overrides
    if not overrides:
        return settings
    data = settings.model_dump()
    if overrides.get("api_key"):
        key = overrides["api_key"]
        api_base = (overrides.get("api_base") or data.get("prds_llm_api_base") or "").lower()
        model = (overrides.get("model") or data.get("prds_llm_model") or "").lower()
        if "deepseek" in api_base or model.startswith("deepseek"):
            data["deepseek_api_key"] = key
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


@lru_cache
def get_settings() -> Settings:
    return _apply_runtime_overrides(Settings())
