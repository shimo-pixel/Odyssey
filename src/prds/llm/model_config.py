import os

import litellm

from prds.config import Settings


def normalize_litellm_model(model: str, settings: Settings) -> str:
    """Ensure LiteLLM can route the model to a provider."""
    model = model.strip()
    if not model or "/" in model:
        return model

    if settings.prds_llm_provider:
        return f"{settings.prds_llm_provider}/{model}"

    lower = model.lower()
    if lower.startswith("deepseek"):
        return f"deepseek/{model}"

    if settings.prds_llm_api_base:
        return f"openai/{model}"

    if lower.startswith("claude-"):
        return f"anthropic/{model}"

    return model


def configure_litellm(settings: Settings) -> None:
    """Apply provider credentials and optional API base from settings."""
    if settings.prds_llm_api_base:
        litellm.api_base = settings.prds_llm_api_base

    if settings.openai_api_key:
        litellm.api_key = settings.openai_api_key
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)

    deepseek_key = settings.deepseek_api_key or settings.openai_api_key
    if deepseek_key:
        os.environ.setdefault("DEEPSEEK_API_KEY", deepseek_key)

    for raw in (settings.prds_llm_model, settings.prds_llm_model_analysis):
        if normalize_litellm_model(raw, settings).startswith("deepseek/"):
            if deepseek_key:
                litellm.api_key = deepseek_key
            break
