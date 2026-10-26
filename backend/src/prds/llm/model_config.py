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


def resolve_llm_api_key(settings: Settings, model: str | None = None) -> str | None:
    """Pick the API key LiteLLM needs for the given (or default) model route."""
    raw = (model or settings.prds_llm_model_analysis or settings.prds_llm_model or "").strip()
    normalized = normalize_litellm_model(raw, settings) if raw else ""
    if normalized.startswith("deepseek/"):
        return (settings.deepseek_api_key or settings.openai_api_key) or None
    # openai/* (incl. DeepSeek via OpenAI-compatible provider + api_base), anthropic, etc.
    return (settings.openai_api_key or settings.deepseek_api_key) or None


def resolve_llm_api_base(settings: Settings, model: str) -> str | None:
    """Provider defaults are request-local; do not use LiteLLM's process globals."""
    if settings.prds_llm_api_base:
        return settings.prds_llm_api_base.rstrip("/")
    normalized = normalize_litellm_model(model, settings)
    provider = normalized.split("/", 1)[0] if "/" in normalized else "openai"
    return {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "anthropic": "https://api.anthropic.com",
    }.get(provider)


def _set_env_if_value(name: str, value: str) -> None:
    """Set env var when we have a real key; overwrite empty placeholders from .env."""
    if not value:
        return
    existing = os.environ.get(name)
    if existing is None or not existing.strip():
        os.environ[name] = value


def configure_litellm(settings: Settings) -> None:
    """Apply provider credentials and optional API base from settings."""
    if settings.prds_llm_api_base:
        litellm.api_base = settings.prds_llm_api_base.rstrip("/")

    openai_key = (settings.openai_api_key or "").strip()
    deepseek_key = (settings.deepseek_api_key or settings.openai_api_key or "").strip()

    _set_env_if_value("DEEPSEEK_API_KEY", deepseek_key)

    routes: set[str] = set()
    for raw in (settings.prds_llm_model, settings.prds_llm_model_analysis):
        if not (raw or "").strip():
            continue
        normalized = normalize_litellm_model(raw, settings)
        if normalized.startswith("deepseek/"):
            routes.add("deepseek")
        else:
            routes.add("openai_compat")

    # DeepSeek native provider
    if "deepseek" in routes and deepseek_key:
        litellm.api_key = deepseek_key

    # OpenAI-compatible path (provider=openai + DeepSeek host is the common UI case).
    # LiteLLM's OpenAI client reads OPENAI_API_KEY; an empty value in .env must be overwritten.
    needs_openai_compat = (
        "openai_compat" in routes
        or bool(settings.prds_llm_api_base)
        or (settings.prds_llm_provider or "").lower() == "openai"
    )
    if needs_openai_compat:
        auth = openai_key or deepseek_key
        if auth:
            litellm.api_key = auth
            _set_env_if_value("OPENAI_API_KEY", auth)
    elif openai_key:
        litellm.api_key = openai_key
        _set_env_if_value("OPENAI_API_KEY", openai_key)
