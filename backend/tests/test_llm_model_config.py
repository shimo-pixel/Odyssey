import os

import litellm

from prds.config import Settings
from prds.llm.model_config import (
    configure_litellm,
    normalize_litellm_model,
    resolve_llm_api_key,
)


def test_normalize_deepseek_model():
    settings = Settings()
    assert normalize_litellm_model("deepseek-v4-flash", settings) == "deepseek/deepseek-v4-flash"


def test_normalize_preserves_prefixed_model():
    settings = Settings()
    assert normalize_litellm_model("deepseek/deepseek-chat", settings) == "deepseek/deepseek-chat"


def test_normalize_openai_compatible_with_api_base():
    settings = Settings(prds_llm_api_base="https://proxy.example/v1")
    assert normalize_litellm_model("custom-model", settings) == "openai/custom-model"


def test_normalize_explicit_provider():
    settings = Settings(prds_llm_provider="openai")
    assert normalize_litellm_model("my-model", settings) == "openai/my-model"


def test_resolve_key_for_openai_provider_with_deepseek_key():
    """UI often sets provider=openai for DeepSeek's OpenAI-compatible API."""
    settings = Settings(
        deepseek_api_key="sk-deepseek",
        openai_api_key="",
        prds_llm_provider="openai",
        prds_llm_model="deepseek-v4-flash",
        prds_llm_model_analysis="deepseek-v4-flash",
        prds_llm_api_base="https://api.deepseek.com/v1",
    )
    assert normalize_litellm_model("deepseek-v4-flash", settings) == "openai/deepseek-v4-flash"
    assert resolve_llm_api_key(settings) == "sk-deepseek"


def test_configure_litellm_sets_openai_env_for_deepseek_openai_compat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")  # empty placeholder from .env
    settings = Settings(
        deepseek_api_key="sk-deepseek",
        openai_api_key="",
        prds_llm_provider="openai",
        prds_llm_model="deepseek-v4-flash",
        prds_llm_model_analysis="deepseek-v4-flash",
        prds_llm_api_base="https://api.deepseek.com/v1",
    )
    configure_litellm(settings)
    assert litellm.api_key == "sk-deepseek"
    assert os.environ.get("OPENAI_API_KEY") == "sk-deepseek"
    assert litellm.api_base == "https://api.deepseek.com/v1"
