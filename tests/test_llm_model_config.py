from prds.config import Settings
from prds.llm.model_config import normalize_litellm_model


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
