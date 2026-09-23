"""Tests for the investigation orchestrator's routing logic, with the LLM/DB
boundaries (classify_intent, generate_sql, retrieve, synthesize, SessionLocal)
monkeypatched so these exercise app/services/investigation.py's own control flow
rather than external services.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

from app.schemas.investigation import Confidence, Route, SynthesisOutput
from app.services import investigation
from app.services.intent import IntentResult


class _FakeSession:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _patch_persist(monkeypatch):
    monkeypatch.setattr(investigation, "SessionLocal", lambda: _FakeSession())


def test_rejected_route_skips_sql_generation_and_retrieval(monkeypatch):
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.REJECTED, reasoning="Unrelated to crime data."),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not be called for a rejected route")

    monkeypatch.setattr(investigation, "_run_sql_stage", fail_if_called)
    monkeypatch.setattr(investigation, "_run_rag_stage", fail_if_called)
    monkeypatch.setattr(investigation, "synthesize", fail_if_called)

    response = investigation.run_investigation("Write me a poem about cats.")

    assert response.route == Route.REJECTED
    assert response.sql_result is None
    assert response.evidence == []
    assert response.synthesis is not None
    assert response.synthesis.confidence == Confidence.HIGH
    assert "Unrelated to crime data." in response.synthesis.answer


def test_sql_route_runs_sql_stage_only(monkeypatch):
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.SQL, reasoning="Needs a count."),
    )

    from app.schemas.investigation import SqlExecutionResult

    monkeypatch.setattr(
        investigation,
        "_run_sql_stage",
        lambda q: (
            SqlExecutionResult(
                generated_sql="SELECT COUNT(*) FROM crimes",
                executed_sql="SELECT COUNT(*) FROM crimes LIMIT 200",
                validation_ok=True,
                rows=[{"count": 42}],
                row_count=1,
            ),
            ("claude-sonnet-5", 10, 5),
        ),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("RAG stage should not run for a pure sql route")

    monkeypatch.setattr(investigation, "_run_rag_stage", fail_if_called)
    monkeypatch.setattr(
        investigation,
        "synthesize",
        lambda **kwargs: SynthesisOutput(
            answer="There were 42 incidents.", citations=[], confidence=Confidence.HIGH, limitations=[]
        ),
    )

    response = investigation.run_investigation("How many crimes happened?")

    assert response.route == Route.SQL
    assert response.sql_result.row_count == 1
    assert response.evidence == []
    assert response.synthesis.answer == "There were 42 incidents."


def test_hybrid_route_runs_both_stages(monkeypatch):
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.HYBRID, reasoning="Needs both."),
    )

    from app.schemas.investigation import EvidenceChunk, SqlExecutionResult

    sql_called = {"value": False}
    rag_called = {"value": False}

    def fake_sql_stage(q):
        sql_called["value"] = True
        return (
            SqlExecutionResult(validation_ok=True, rows=[], row_count=0),
            (None, 0, 0),
        )

    def fake_rag_stage(q):
        rag_called["value"] = True
        return [
            EvidenceChunk(
                document_title="Doc", document_source="doc.md", content="text", similarity=0.5
            )
        ]

    monkeypatch.setattr(investigation, "_run_sql_stage", fake_sql_stage)
    monkeypatch.setattr(investigation, "_run_rag_stage", fake_rag_stage)
    monkeypatch.setattr(
        investigation,
        "synthesize",
        lambda **kwargs: SynthesisOutput(
            answer="Combined answer.", citations=["Doc"], confidence=Confidence.MEDIUM, limitations=[]
        ),
    )

    response = investigation.run_investigation("Is theft up, and why?")

    assert sql_called["value"] is True
    assert rag_called["value"] is True
    assert len(response.evidence) == 1


def test_synthesis_llm_failure_does_not_crash_pipeline(monkeypatch):
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.RAG, reasoning="Definitional question."),
    )
    monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [])

    from app.llm.client import LlmError

    def boom(**kwargs):
        raise LlmError("provider unreachable")

    monkeypatch.setattr(investigation, "synthesize", boom)

    response = investigation.run_investigation("What is an IUCR code?")

    assert response.synthesis is None
    assert response.route == Route.RAG


def test_sql_generation_llm_failure_degrades_to_rejected_result(monkeypatch):
    """Regression test: generate_sql() raising LlmError inside _run_sql_stage used
    to propagate out of run_investigation entirely, skipping _persist_log for the
    request. Must degrade to a rejected SqlExecutionResult instead."""
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.SQL, reasoning="Needs a count."),
    )

    from app.llm.client import LlmError

    def boom(question: str):
        raise LlmError("provider unreachable")

    monkeypatch.setattr(investigation, "generate_sql", boom)
    monkeypatch.setattr(
        investigation,
        "synthesize",
        lambda **kwargs: SynthesisOutput(
            answer="No data available.", citations=[], confidence=Confidence.LOW, limitations=[]
        ),
    )

    response = investigation.run_investigation("How many thefts happened?")

    assert response.route == Route.SQL
    assert response.sql_result is not None
    assert response.sql_result.validation_ok is False
    assert "LLM call failed" in response.sql_result.rejection_reason


def test_rag_retrieval_failure_degrades_to_empty_evidence(monkeypatch):
    """Regression test: retrieve() raising (e.g. DB or embedding model down)
    inside _run_rag_stage used to propagate out of run_investigation entirely,
    skipping _persist_log for the request. Must degrade to empty evidence."""
    _patch_persist(monkeypatch)
    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.RAG, reasoning="Definitional question."),
    )

    def boom(session, question):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(investigation, "retrieve", boom)
    monkeypatch.setattr(
        investigation,
        "synthesize",
        lambda **kwargs: SynthesisOutput(
            answer="No evidence available.", citations=[], confidence=Confidence.LOW, limitations=[]
        ),
    )

    response = investigation.run_investigation("What is an IUCR code?")

    assert response.route == Route.RAG
    assert response.evidence == []


def test_full_llm_outage_still_persists_query_log(monkeypatch):
    """The end-to-end resilience claim: even if EVERY LLM-dependent stage fails
    (simulating a total Anthropic API outage — intent classification already
    degrades to hybrid per test_intent_resilience.py, and both remaining stages
    are exercised here), run_investigation must still complete and call
    _persist_log, rather than raising and losing the audit trail for the request."""
    logged = {}

    class _RecordingSession(_FakeSession):
        def add(self, obj):
            logged["query_log_entry"] = obj

    monkeypatch.setattr(investigation, "SessionLocal", lambda: _RecordingSession())

    from app.llm.client import LlmError

    def boom(*args, **kwargs):
        raise LlmError("total outage")

    monkeypatch.setattr(
        investigation,
        "classify_intent",
        lambda q: IntentResult(route=Route.HYBRID, reasoning="LLM call failed; defaulting to hybrid."),
    )
    monkeypatch.setattr(investigation, "generate_sql", boom)
    monkeypatch.setattr(investigation, "retrieve", lambda session, question: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(investigation, "synthesize", boom)

    response = investigation.run_investigation("How many thefts happened this year?")

    assert response is not None
    assert response.sql_result.validation_ok is False
    assert response.evidence == []
    assert response.synthesis is None
    assert "query_log_entry" in logged
    assert logged["query_log_entry"].route == Route.HYBRID.value
