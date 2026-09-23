"""Regression tests for a real gap found via live testing during an LLM outage
(no Anthropic API key configured yet): classify_intent() raising LlmError
propagated all the way out of run_investigation before query_log was ever
written, defeating this system's core auditability claim for exactly the
failure mode most likely to occur in production. classify_intent() must
degrade to Route.HYBRID on an LLM failure, the same way it already does for
unparseable LLM output.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

from app.llm.client import LlmError
from app.schemas.investigation import Route
from app.services import intent


def test_classify_intent_degrades_to_hybrid_on_llm_error(monkeypatch):
    def boom(system, user, max_tokens=None):
        raise LlmError("connection error")

    monkeypatch.setattr(intent, "complete", boom)

    result = intent.classify_intent("How did theft change over time?")

    assert result.route == Route.HYBRID
    assert "LLM call failed" in result.reasoning


def test_classify_intent_still_works_normally_when_llm_succeeds(monkeypatch):
    from dataclasses import dataclass

    @dataclass
    class FakeResponse:
        text: str
        model: str = "claude-sonnet-5"
        input_tokens: int = 10
        output_tokens: int = 5

    monkeypatch.setattr(
        intent,
        "complete",
        lambda system, user, max_tokens=None: FakeResponse(
            text='{"route": "sql", "reasoning": "Needs a count."}'
        ),
    )

    result = intent.classify_intent("How many thefts happened?")

    assert result.route == Route.SQL
    assert result.reasoning == "Needs a count."
