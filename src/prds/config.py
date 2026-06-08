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
    deepseek_api_key: str = ""
    prds_llm_model: str = "gpt-4o-mini"
    prds_llm_model_analysis: str = "gpt-4o"
    prds_llm_provider: str = ""
    prds_llm_api_base: str = ""
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

    # Industry background research (step ②)
    gemini_api_key: str = ""
    prds_research_enabled: bool = True
    prds_research_provider: str = "auto"  # auto|deep_research|grounded|fallback|off
    prds_research_model: str = "deep-research-preview-04-2026"
    prds_research_grounded_model: str = "gemini-2.5-flash"
    prds_research_timeout_s: int = 1200
    prds_research_poll_interval_s: int = 10
    # Grow the knowledge graph period-by-period via LLM episode extraction.
    prds_dynamic_graph: bool = True

    # Knowledge-graph backend: auto|graphiti|builtin
    # - graphiti: episode-driven GraphRAG on Graphiti + Neo4j (LLM auto-extracts entities/edges)
    # - builtin: in-house incremental extractor (no extra infra)
    # - auto: use graphiti when Neo4j + an embedder are configured and graphiti-core is installed
    prds_graph_backend: str = "auto"
    # Graphiti needs an embedder; default to the OpenAI-compatible endpoint used by the LLM.
    graphiti_embedding_api_key: str = ""
    graphiti_embedding_api_base: str = ""
    graphiti_embedding_model: str = ""
    graphiti_llm_api_key: str = ""
    graphiti_llm_api_base: str = ""
    graphiti_llm_model: str = ""
    graphiti_async_timeout_s: int = 300

    @property
    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    @property
    def graphiti_embedding_configured(self) -> bool:
        if self.graphiti_embedding_api_key:
            return True
        # DeepSeek has no embedding API — don't treat a DeepSeek key in OPENAI_API_KEY as embedder-ready.
        if self._deepseek_only_llm():
            return False
        return bool(self.openai_api_key)

    def _deepseek_only_llm(self) -> bool:
        model = (self.prds_llm_model_analysis or self.prds_llm_model).lower()
        if model.startswith("deepseek"):
            return True
        if self.prds_llm_api_base and "deepseek" in self.prds_llm_api_base.lower():
            return True
        if self.deepseek_api_key and self.openai_api_key == self.deepseek_api_key:
            return True
        return bool(self.deepseek_api_key and not self.openai_api_key)

    def resolved_graph_backend(self) -> str:
        """Decide which graph backend to use given config + available infra."""
        choice = (self.prds_graph_backend or "auto").lower()
        if choice == "builtin":
            return "builtin"
        graphiti_ready = self.neo4j_enabled and self.graphiti_embedding_configured
        if choice == "graphiti":
            return "graphiti" if graphiti_ready else "builtin"
        # auto
        return "graphiti" if graphiti_ready else "builtin"

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def resolved_research_provider(self) -> str:
        """Decide which research provider to actually use given config + keys."""
        if not self.prds_research_enabled or self.prds_research_provider == "off":
            return "off"
        choice = self.prds_research_provider
        if choice in {"deep_research", "grounded"} and not self.gemini_configured:
            return "fallback"
        if choice == "auto":
            return "deep_research" if self.gemini_configured else "fallback"
        return choice

    @property
    def logs_path(self) -> Path:
        path = Path(self.prds_logs_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key or self.deepseek_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
