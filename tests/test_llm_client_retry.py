"""Regression test for a real latency bug found via live testing: _call_anthropic
retried on every exception type, including permanent failures like a missing/
invalid API key (AuthenticationError). Retrying a failure that will identically
fail on every attempt only adds latency for no benefit — observed as a ~40 second
delay (3 attempts, exponential backoff up to 8s) before a request finally failed,
for an error that was knowable on the first attempt. Only transient/server-side
errors (rate limits, connection issues, 5xx) should be retried.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import httpx
import pytest
from anthropic import AuthenticationError, RateLimitError

from app.llm.client import LlmError, _call_anthropic


def _fake_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.anthropic.com"))


def test_authentication_error_is_not_retried(monkeypatch):
    call_count = {"n": 0}

    class FakeMessages:
        def create(self, **kwargs):
            call_count["n"] += 1
            raise AuthenticationError("invalid api key", response=_fake_response(401), body=None)

    class FakeClient:
        messages = FakeMessages()

    from app.llm import client as client_module

    monkeypatch.setattr(client_module, "_get_client", lambda: FakeClient())

    with pytest.raises(AuthenticationError):
        _call_anthropic("system", "user", 100)

    assert call_count["n"] == 1  # no retries for a permanent failure


def test_rate_limit_error_is_retried(monkeypatch):
    call_count = {"n": 0}

    class FakeMessages:
        def create(self, **kwargs):
            call_count["n"] += 1
            raise RateLimitError("rate limited", response=_fake_response(429), body=None)

    class FakeClient:
        messages = FakeMessages()

    from app.llm import client as client_module

    monkeypatch.setattr(client_module, "_get_client", lambda: FakeClient())

    with pytest.raises(RateLimitError):
        _call_anthropic("system", "user", 100)

    assert call_count["n"] == 3  # stop_after_attempt(3) — a transient error IS retried


def test_complete_wraps_non_retryable_failure_as_llm_error(monkeypatch):
    from app.llm import client as client_module

    def boom(system, user, max_tokens):
        raise AuthenticationError("invalid api key", response=_fake_response(401), body=None)

    monkeypatch.setattr(client_module, "_call_anthropic", boom)

    with pytest.raises(LlmError):
        client_module.complete("system", "user")
