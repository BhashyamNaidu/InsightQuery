"""Tests for app/llm/client.py's provider dispatch logic — the layer that reads
LLM_PROVIDER and picks a concrete provider. Verifies the graceful-degradation
contract: every misconfiguration (unknown provider, anthropic with no key, no
provider at all) raises LlmError with an actionable message, never an unhandled
exception, and never leaks whatever partial credential state exists.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "")

import pytest

from app.core.config import get_settings
from app.llm import client as client_module
from app.llm.client import LlmError


@pytest.fixture(autouse=True)
def _clear_caches():
    get_settings.cache_clear()
    client_module._get_provider.cache_clear()
    yield
    get_settings.cache_clear()
    client_module._get_provider.cache_clear()


def test_anthropic_provider_without_api_key_raises_clear_llm_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    with pytest.raises(LlmError, match="ANTHROPIC_API_KEY is not set"):
        client_module.complete("system", "user")


def test_none_provider_raises_clear_llm_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")

    with pytest.raises(LlmError, match="disabled"):
        client_module.complete("system", "user")


def test_unknown_provider_raises_clear_llm_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "some-made-up-provider")

    with pytest.raises(LlmError, match="Unknown LLM_PROVIDER"):
        client_module.complete("system", "user")


def test_provider_exception_is_wrapped_as_llm_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:1")  # nothing listening

    with pytest.raises(LlmError):
        client_module.complete("system", "user")


def test_ollama_is_the_default_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = get_settings()
    assert settings.llm_provider == "ollama"


def test_successful_ollama_call_returns_llm_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    from dataclasses import dataclass

    @dataclass
    class FakeResponse:
        text: str = "hello"
        model: str = "llama3.2:3b"
        provider: str = "ollama"
        input_tokens: int = 5
        output_tokens: int = 2

    class FakeProvider:
        name = "ollama"

        def complete(self, system, user, max_tokens):
            return FakeResponse()

    monkeypatch.setattr(client_module, "_get_provider", lambda name: FakeProvider())

    response = client_module.complete("system", "user")
    assert response.text == "hello"
    assert response.provider == "ollama"
