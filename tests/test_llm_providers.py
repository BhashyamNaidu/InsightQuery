"""Tests for the concrete LLM providers (app/llm/providers/). Each provider is
tested in isolation with its underlying HTTP client mocked — no real network calls,
no real Ollama/Anthropic server required.
"""
from __future__ import annotations

import httpx
import pytest
from anthropic import AuthenticationError, RateLimitError

from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.providers.ollama_provider import OllamaProvider


def _fake_anthropic_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.anthropic.com"))


class TestAnthropicProvider:
    def test_authentication_error_is_not_retried(self, monkeypatch):
        """Regression test carried over from the pre-refactor client: a permanent
        failure (bad/missing API key) must fail on the first attempt, not be
        retried 3x with exponential backoff (~40s wasted for a failure that will
        never succeed no matter how many times it's retried)."""
        call_count = {"n": 0}

        class FakeMessages:
            def create(self, **kwargs):
                call_count["n"] += 1
                raise AuthenticationError("invalid api key", response=_fake_anthropic_response(401), body=None)

        class FakeClient:
            messages = FakeMessages()

        provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
        monkeypatch.setattr(provider, "_client", FakeClient())

        with pytest.raises(AuthenticationError):
            provider.complete("system", "user", 100)
        assert call_count["n"] == 1

    def test_rate_limit_error_is_retried(self, monkeypatch):
        call_count = {"n": 0}

        class FakeMessages:
            def create(self, **kwargs):
                call_count["n"] += 1
                raise RateLimitError("rate limited", response=_fake_anthropic_response(429), body=None)

        class FakeClient:
            messages = FakeMessages()

        provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
        monkeypatch.setattr(provider, "_client", FakeClient())

        with pytest.raises(RateLimitError):
            provider.complete("system", "user", 100)
        assert call_count["n"] == 3  # stop_after_attempt(3)

    def test_successful_response_parsed_correctly(self, monkeypatch):
        from dataclasses import dataclass

        @dataclass
        class FakeBlock:
            text: str

        @dataclass
        class FakeUsage:
            input_tokens: int
            output_tokens: int

        @dataclass
        class FakeMessage:
            content: list
            usage: FakeUsage

        class FakeMessages:
            def create(self, **kwargs):
                return FakeMessage(content=[FakeBlock(text="hello")], usage=FakeUsage(10, 5))

        class FakeClient:
            messages = FakeMessages()

        provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-5")
        monkeypatch.setattr(provider, "_client", FakeClient())

        response = provider.complete("system", "user", 100)
        assert response.text == "hello"
        assert response.provider == "anthropic"
        assert response.model == "claude-sonnet-5"
        assert response.input_tokens == 10
        assert response.output_tokens == 5


class TestOllamaProvider:
    def test_connection_error_raises_clear_message(self, monkeypatch):
        def boom(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", boom)
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=5)

        with pytest.raises(ConnectionError, match="Is it running"):
            provider.complete("system", "user", 100)

    def test_model_not_found_raises_clear_message(self, monkeypatch):
        def fake_post(*args, **kwargs):
            request = httpx.Request("POST", "http://localhost:11434/api/chat")
            response = httpx.Response(404, request=request, text="model not found")
            raise httpx.HTTPStatusError("404", request=request, response=response)

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434", model="nonexistent:1b", timeout_seconds=5)

        with pytest.raises(ValueError, match="ollama pull"):
            provider.complete("system", "user", 100)

    def test_successful_response_parsed_correctly(self, monkeypatch):
        def fake_post(*args, **kwargs):
            request = httpx.Request("POST", "http://localhost:11434/api/chat")
            return httpx.Response(
                200,
                request=request,
                json={
                    "message": {"role": "assistant", "content": '{"route": "sql"}'},
                    "prompt_eval_count": 42,
                    "eval_count": 7,
                },
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2:3b", timeout_seconds=5)

        response = provider.complete("system", "user", 100)
        assert response.text == '{"route": "sql"}'
        assert response.provider == "ollama"
        assert response.model == "llama3.2:3b"
        assert response.input_tokens == 42
        assert response.output_tokens == 7

    def test_request_sent_with_correct_shape(self, monkeypatch):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            request = httpx.Request("POST", url)
            return httpx.Response(
                200, request=request, json={"message": {"content": "ok"}, "prompt_eval_count": 1, "eval_count": 1}
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = OllamaProvider(base_url="http://localhost:11434/", model="llama3.2:3b", timeout_seconds=30)
        provider.complete("You are helpful.", "Hello", 256)

        assert captured["url"] == "http://localhost:11434/api/chat"  # trailing slash stripped
        assert captured["json"]["model"] == "llama3.2:3b"
        assert captured["json"]["messages"] == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        assert captured["json"]["stream"] is False
        assert captured["json"]["options"]["num_predict"] == 256
        assert captured["timeout"] == 30
