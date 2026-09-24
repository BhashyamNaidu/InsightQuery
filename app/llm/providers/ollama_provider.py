"""Ollama provider: local inference, no API key, no per-token cost, no third-party
rate limit or pricing policy to depend on — genuinely free because it's just local
compute, not because of a vendor's current promotional terms. This is the default
provider (see app/core/config.py) specifically so the project runs end-to-end
without requiring anyone to pay for an API key to see it work.

Trade-off, stated plainly: CPU inference on a small (~3B parameter) local model is
slower and somewhat less reliable at strict JSON/SQL output than a frontier hosted
model. See docs/LLM_STRATEGY.md for the actual measured comparison.
"""
from __future__ import annotations

import httpx

from app.llm.providers.base import LlmProvider, LlmResponse


class OllamaProvider(LlmProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: float):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    def complete(self, system: str, user: str, max_tokens: int) -> LlmResponse:
        try:
            response = httpx.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Could not reach Ollama at {self._base_url}. Is it running? "
                f"(`ollama serve`, or `ollama list` to check installed models)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            if exc.response.status_code == 404:
                raise ValueError(
                    f"Ollama model '{self._model}' not found. Pull it first: "
                    f"`ollama pull {self._model}`"
                ) from exc
            raise RuntimeError(f"Ollama returned {exc.response.status_code}: {body}") from exc

        data = response.json()
        text = data.get("message", {}).get("content", "")
        return LlmResponse(
            text=text,
            model=self._model,
            provider=self.name,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )
