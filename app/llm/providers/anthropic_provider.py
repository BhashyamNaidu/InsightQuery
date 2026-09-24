"""Anthropic provider. Requires ANTHROPIC_API_KEY — this is the paid option, kept
available but never the default (see app/core/config.py: LLM_PROVIDER defaults to
"ollama", the free local option).
"""
from __future__ import annotations

from functools import lru_cache

import anthropic
from anthropic import Anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.llm.providers.base import LlmProvider, LlmResponse

# Errors worth retrying: transient/server-side (rate limit, connection blip, 5xx).
# Deliberately excludes AuthenticationError, PermissionDeniedError, NotFoundError,
# and BadRequestError — a missing/invalid API key or a malformed request fails
# identically on every attempt, so retrying it only adds latency (found via live
# testing: retrying a bad-auth failure 3x with exponential backoff turned an
# instant, permanent failure into a ~40 second one before the caller ever saw it).
_RETRYABLE_ERRORS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


class AnthropicProvider(LlmProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self._model = model
        self._client = _get_client(api_key)

    def complete(self, system: str, user: str, max_tokens: int) -> LlmResponse:
        message = self._call(system, user, max_tokens)
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        return LlmResponse(
            text=text,
            model=self._model,
            provider=self.name,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
    )
    def _call(self, system: str, user: str, max_tokens: int):
        return self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )


@lru_cache
def _get_client(api_key: str) -> Anthropic:
    return Anthropic(api_key=api_key)
