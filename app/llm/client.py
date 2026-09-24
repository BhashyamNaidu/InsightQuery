"""Provider-agnostic entry point for every LLM call in the app. Callers (intent
classification, SQL generation, synthesis) only ever import `complete` and
`LlmError` from here — never a specific provider — so switching LLM_PROVIDER in
.env changes behavior without changing a single call site. See
app/llm/providers/base.py for the interface and docs/LLM_STRATEGY.md for why
"ollama" (local, free) is the default rather than "anthropic" (paid, hosted).
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.llm.providers.base import LlmProvider, LlmResponse

__all__ = ["LlmResponse", "LlmError", "complete"]


class LlmError(RuntimeError):
    """Raised when the LLM call fails after retries, returns unusable output, or
    no provider is configured/reachable. Every caller in this codebase treats this
    as a normal, expected failure mode to degrade gracefully from — not a crash."""


@lru_cache
def _get_provider(provider_name: str) -> LlmProvider:
    settings = get_settings()
    if provider_name == "anthropic":
        from app.llm.providers.anthropic_provider import AnthropicProvider

        if not settings.anthropic_api_key:
            raise LlmError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Set it in .env, or switch LLM_PROVIDER to 'ollama' for the free "
                "local option (see docs/LLM_STRATEGY.md)."
            )
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    if provider_name == "ollama":
        from app.llm.providers.ollama_provider import OllamaProvider

        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    if provider_name in ("none", ""):
        raise LlmError(
            "LLM_PROVIDER is set to 'none' (or unset with no default) — LLM-dependent "
            "features are disabled. Set LLM_PROVIDER=ollama (free, local) or "
            "LLM_PROVIDER=anthropic (requires ANTHROPIC_API_KEY) in .env to enable them."
        )

    raise LlmError(f"Unknown LLM_PROVIDER: '{provider_name}'. Use 'ollama', 'anthropic', or 'none'.")


def complete(system: str, user: str, max_tokens: int | None = None) -> LlmResponse:
    settings = get_settings()
    provider = _get_provider(settings.llm_provider)
    try:
        return provider.complete(system, user, max_tokens or settings.llm_max_output_tokens)
    except LlmError:
        raise
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any provider failure -> LlmError
        raise LlmError(f"LLM call failed ({provider.name}): {exc}") from exc
