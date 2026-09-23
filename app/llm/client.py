"""Thin wrapper around the Anthropic client. Every call site gets back the raw text
plus token usage, so callers can log usage centrally (see app.core.observability)
without each caller re-implementing that bookkeeping."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from anthropic import Anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings


@dataclass
class LlmResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


@lru_cache
def _get_client() -> Anthropic:
    return Anthropic(api_key=get_settings().anthropic_api_key)


class LlmError(RuntimeError):
    """Raised when the LLM call fails after retries, or returns unusable output."""


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
)
def _call_anthropic(system: str, user: str, max_tokens: int) -> LlmResponse:
    settings = get_settings()
    client = _get_client()
    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in message.content if hasattr(block, "text"))
    return LlmResponse(
        text=text,
        model=settings.llm_model,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )


def complete(system: str, user: str, max_tokens: int | None = None) -> LlmResponse:
    settings = get_settings()
    try:
        return _call_anthropic(system, user, max_tokens or settings.llm_max_output_tokens)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any LLM failure -> LlmError
        raise LlmError(f"LLM call failed: {exc}") from exc
