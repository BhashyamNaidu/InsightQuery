"""Provider-agnostic LLM interface. Every concrete provider (Anthropic, Ollama, ...)
implements this and nothing else — the rest of the app (app/llm/client.py and every
caller above it) only ever sees LlmResponse/LlmError, never a provider-specific type.
This is what lets LLM_PROVIDER be a config switch instead of a code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LlmResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int


class LlmProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int) -> LlmResponse:
        """Raise LlmError (or let a provider-specific exception propagate — the
        dispatcher in app/llm/client.py wraps anything unexpected) on failure.
        Never return a response for a request that didn't actually succeed.
        """
        raise NotImplementedError
