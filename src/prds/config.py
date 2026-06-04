from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    prds_llm_model: str = "gpt-4o-mini"
    prds_llm_model_analysis: str = "gpt-4o"
    prds_max_concurrent_llm: int = 20
    prds_default_agent_count: int = 50
    prds_default_periods: int = 120
    prds_database_url: str = "sqlite+aiosqlite:///./prds.db"
    prds_checkpoint_interval: int = 5
    prds_logs_dir: str = "./data/logs"
    prds_use_graphrag: bool = True
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    @property
    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    @property
    def logs_path(self) -> Path:
        path = Path(self.prds_logs_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
