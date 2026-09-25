"""Unit tests for app/llm/synthesis.py — previously untested despite being the
final, user-facing stage of every investigation. Covers the malformed-LLM-output
adversarial case explicitly (garbage text, missing fields, wrong types, fenced
JSON) since a synthesis failure must degrade to an honest "could not produce a
grounded answer," never raise or return unvalidated data.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

from dataclasses import dataclass

import pytest

from app.llm import synthesis
from app.schemas.investigation import Confidence


@dataclass
class _FakeResponse:
    text: str
    model: str = "test-model"
    provider: str = "test"
    input_tokens: int = 10
    output_tokens: int = 5


def _mock_complete(monkeypatch, *texts: str):
    """Mocks complete() to return each text in sequence, one per call (models the
    retry loop's up-to-2 attempts)."""
    responses = iter(_FakeResponse(t) for t in texts)
    monkeypatch.setattr(synthesis, "complete", lambda *a, **kw: next(responses))


class TestValidOutput:
    def test_clean_json_parsed_correctly(self, monkeypatch):
        _mock_complete(
            monkeypatch,
            '{"answer": "Theft rose 12%.", "citations": ["Doc A"], "confidence": "high", "limitations": []}',
        )
        result = synthesis.synthesize("Is theft up?", sql="SELECT 1", sql_rows=[{"n": 1}])
        assert result.answer == "Theft rose 12%."
        assert result.citations == ["Doc A"]
        assert result.confidence == Confidence.HIGH

    def test_markdown_fenced_json_parsed_correctly(self, monkeypatch):
        """Regression test: smaller/local models (the default LLM_PROVIDER is
        Ollama — see docs/LLM_STRATEGY.md) are more likely than a frontier hosted
        model to wrap JSON in ```json fences even when told not to. Without
        stripping fences first, this would always fail json.loads()."""
        _mock_complete(
            monkeypatch,
            '```json\n{"answer": "Theft rose 12%.", "citations": [], "confidence": "medium", "limitations": []}\n```',
        )
        result = synthesis.synthesize("Is theft up?")
        assert result.answer == "Theft rose 12%."
        assert result.confidence == Confidence.MEDIUM

    def test_json_with_surrounding_prose_parsed_correctly(self, monkeypatch):
        _mock_complete(
            monkeypatch,
            'Sure, here is my answer:\n{"answer": "No data.", "citations": [], "confidence": "low", "limitations": []}\nHope that helps!',
        )
        result = synthesis.synthesize("What happened?")
        assert result.answer == "No data."


class TestMalformedOutput:
    def test_garbage_text_degrades_gracefully_after_retry(self, monkeypatch):
        _mock_complete(monkeypatch, "I don't know how to answer that.", "Still not JSON.")
        result = synthesis.synthesize("Anything?")
        assert result.confidence == Confidence.LOW
        assert "could not produce" in result.answer.lower()
        assert "failed schema validation" in result.limitations[0].lower()

    def test_valid_json_missing_required_field_degrades_gracefully(self, monkeypatch):
        # Missing "confidence", a required field on SynthesisOutput.
        _mock_complete(monkeypatch, '{"answer": "test", "citations": []}', '{"answer": "test", "citations": []}')
        result = synthesis.synthesize("Anything?")
        assert result.confidence == Confidence.LOW

    def test_invalid_confidence_enum_value_degrades_gracefully(self, monkeypatch):
        _mock_complete(
            monkeypatch,
            '{"answer": "test", "citations": [], "confidence": "extremely-sure", "limitations": []}',
            '{"answer": "test", "citations": [], "confidence": "extremely-sure", "limitations": []}',
        )
        result = synthesis.synthesize("Anything?")
        assert result.confidence == Confidence.LOW

    def test_second_attempt_succeeding_after_first_fails_is_used(self, monkeypatch):
        _mock_complete(
            monkeypatch,
            "not json at all",
            '{"answer": "recovered on retry", "citations": [], "confidence": "high", "limitations": []}',
        )
        result = synthesis.synthesize("Anything?")
        assert result.answer == "recovered on retry"
        assert result.confidence == Confidence.HIGH

    def test_empty_string_response_degrades_gracefully(self, monkeypatch):
        _mock_complete(monkeypatch, "", "")
        result = synthesis.synthesize("Anything?")
        assert result.confidence == Confidence.LOW

    def test_json_array_instead_of_object_degrades_gracefully(self, monkeypatch):
        _mock_complete(monkeypatch, '["not", "an", "object"]', '["not", "an", "object"]')
        result = synthesis.synthesize("Anything?")
        assert result.confidence == Confidence.LOW


class TestEmptyEvidence:
    def test_no_sql_and_no_evidence_still_calls_llm_with_honest_prompt(self, monkeypatch):
        captured = {}

        def fake_complete(system, user, max_tokens=None):
            captured["user_prompt"] = user
            return _FakeResponse(
                '{"answer": "Insufficient evidence to answer.", "citations": [], "confidence": "low", "limitations": ["No SQL or documents were available."]}'
            )

        monkeypatch.setattr(synthesis, "complete", fake_complete)
        result = synthesis.synthesize("An unanswerable question", sql=None, sql_rows=None, evidence_chunks=[])

        assert "No SQL results or documents were retrieved" in captured["user_prompt"]
        assert result.confidence == Confidence.LOW
