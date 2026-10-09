"""A SQL branch that produced no result must never be narrated as "zero rows".

Regression for: a DELETE rejected by validate_sql() still reached synthesis with
sql_rows=[], and the model answered "No records exist to delete from the database."

These tests use the REAL validate_sql(); only the LLM, the database and persistence are
faked, so they exercise the actual rejection path end to end through run_investigation().
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest
from sqlalchemy.exc import OperationalError

from app.nlsql.generator import SqlGenerationResult
from app.nlsql.validator import ValidationResult, validate_sql
from app.schemas.investigation import Confidence, EvidenceChunk, Route, SqlExecutionResult, SynthesisOutput
from app.services import investigation
from app.services.intent import IntentResult


class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    def add(self, obj):
        self._sink.append(obj)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Harness:
    """Records query_log rows, synthesis calls and database executions for one investigation."""

    def __init__(self, monkeypatch, route, generated_sql=None, executed_rows=None, synth_answer="narrated"):
        self.logged: list = []
        self.synth_calls: list[dict] = []
        self.executions: list[str] = []

        monkeypatch.setattr(investigation, "SessionLocal", lambda: _FakeSession(self.logged))
        monkeypatch.setattr(investigation, "classify_intent", lambda q: IntentResult(route=route, reasoning="test"))

        def fake_generate(question):
            if generated_sql is None:  # the model declined to write SQL
                validation = ValidationResult(ok=False, reason="Model determined the question is not answerable via SQL.")
                return SqlGenerationResult(None, validation, "m", "ollama", 1, 1)
            return SqlGenerationResult(generated_sql, validate_sql(generated_sql), "m", "ollama", 1, 1)

        def fake_execute(sql):
            self.executions.append(sql)
            if isinstance(executed_rows, Exception):
                raise executed_rows
            return executed_rows if executed_rows is not None else []

        def fake_synthesize(**kwargs):
            self.synth_calls.append(kwargs)
            return SynthesisOutput(answer=synth_answer, citations=[], confidence=Confidence.MEDIUM, limitations=["model caveat"])

        monkeypatch.setattr("app.nlsql.pipeline.generate_sql", fake_generate)
        monkeypatch.setattr("app.nlsql.pipeline.execute_readonly", fake_execute)
        monkeypatch.setattr(investigation, "synthesize", fake_synthesize)
        monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [])

    @property
    def row(self):
        assert len(self.logged) == 1
        return self.logged[0]


BLOCKED_SQL = [
    "DELETE FROM crimes WHERE primary_type = 'THEFT'",
    "DROP TABLE crimes",
    "UPDATE crimes SET arrest = TRUE",
]
CHUNK = EvidenceChunk(document_title="Doc A", document_source="s", content="text", similarity=0.9)


@pytest.mark.parametrize("bad_sql", BLOCKED_SQL)
def test_validator_rejection_is_an_explicit_blocked_result(monkeypatch, bad_sql):
    _Harness(monkeypatch, Route.SQL, generated_sql=bad_sql)

    response = investigation.run_investigation("Delete all theft records from the database")

    sql = response.sql_result
    assert sql.outcome == "blocked_by_validator"
    assert sql.validation_ok is False
    assert sql.rows == [] and sql.executed_sql is None
    assert sql.generated_sql == bad_sql  # kept, so the attempt remains auditable
    answer = response.synthesis.answer
    assert "blocked by the SQL safety validator" in answer
    assert "no query was run" in answer
    assert "No records exist" not in answer and "0 rows" not in answer  # must not read like an empty result
    assert response.synthesis.confidence == Confidence.HIGH
    assert response.synthesis.citations == []


@pytest.mark.parametrize("bad_sql", BLOCKED_SQL)
def test_no_database_execution_after_validation_rejection(monkeypatch, bad_sql):
    h = _Harness(monkeypatch, Route.SQL, generated_sql=bad_sql)
    investigation.run_investigation("Delete all theft records from the database")
    assert h.executions == []


@pytest.mark.parametrize("bad_sql", BLOCKED_SQL)
def test_no_synthesis_call_with_fabricated_zero_rows(monkeypatch, bad_sql):
    h = _Harness(monkeypatch, Route.SQL, generated_sql=bad_sql)
    response = investigation.run_investigation("Delete all theft records from the database")
    assert h.synth_calls == []  # the LLM is never shown an empty result set for a rejected query
    assert "synthesis" not in response.stage_latency_ms  # no synthesis stage actually ran


def test_audit_log_distinguishes_rejection_from_zero_rows(monkeypatch):
    # 1) rejected: validation failed, nothing executed, row_count is NULL (not 0)
    h = _Harness(monkeypatch, Route.SQL, generated_sql="DELETE FROM crimes")
    investigation.run_investigation("Delete everything")
    rejected = h.row
    assert rejected.sql_validation_ok is False
    assert rejected.row_count is None
    assert rejected.executed_sql is None
    assert rejected.generated_sql == "DELETE FROM crimes"
    assert "not permitted" in rejected.sql_rejection_reason

    # 2) genuine zero rows: validated and executed, row_count == 0, and synthesis runs normally
    z = _Harness(monkeypatch, Route.SQL, generated_sql="SELECT COUNT(*) FROM crimes WHERE year = 1999", executed_rows=[])
    response = investigation.run_investigation("Crimes in 1999?")
    zero = z.row
    assert zero.sql_validation_ok is True
    assert zero.row_count == 0
    assert zero.executed_sql is not None
    assert zero.sql_rejection_reason is None
    assert response.sql_result.outcome == "executed"
    assert len(z.synth_calls) == 1 and z.synth_calls[0]["sql_rows"] == []  # a real empty result IS passed on

    # the two cases are separable from the log row alone
    assert (rejected.sql_validation_ok, rejected.row_count) != (zero.sql_validation_ok, zero.row_count)


def test_successful_sql_investigation_still_synthesizes_normally(monkeypatch):
    rows = [{"primary_type": "THEFT", "count": 57526}]
    h = _Harness(
        monkeypatch, Route.SQL,
        generated_sql="SELECT primary_type, COUNT(*) AS count FROM crimes GROUP BY primary_type",
        executed_rows=rows, synth_answer="Theft is most common.",
    )

    response = investigation.run_investigation("Most common crime type?")

    assert response.sql_result.outcome == "executed"
    assert response.sql_result.rows == rows and response.sql_result.row_count == 1
    assert response.synthesis.answer == "Theft is most common."
    assert len(h.synth_calls) == 1
    assert h.synth_calls[0]["sql_rows"] == rows and h.synth_calls[0]["sql"].endswith("LIMIT 200")
    assert h.row.row_count == 1
    assert "synthesis" in response.stage_latency_ms


def test_rag_only_investigation_unchanged(monkeypatch):
    h = _Harness(monkeypatch, Route.RAG)
    monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [CHUNK])

    response = investigation.run_investigation("What is an IUCR code?")

    assert response.sql_result is None
    assert response.synthesis.answer == "narrated"
    assert len(h.synth_calls) == 1
    assert h.synth_calls[0]["sql"] is None and h.synth_calls[0]["sql_rows"] is None
    assert h.executions == []
    assert h.row.sql_validation_ok is None and h.row.row_count is None


def test_hybrid_with_blocked_sql_synthesizes_from_documents_only(monkeypatch):
    h = _Harness(monkeypatch, Route.HYBRID, generated_sql="DROP TABLE crimes")
    monkeypatch.setattr(investigation, "_run_rag_stage", lambda q: [CHUNK])

    response = investigation.run_investigation("Count thefts and explain them")

    assert h.executions == []
    assert len(h.synth_calls) == 1
    call = h.synth_calls[0]
    assert call["sql"] is None and call["sql_rows"] is None  # never an empty result set
    assert call["evidence_chunks"][0]["document_title"] == "Doc A"
    assert response.sql_result.outcome == "blocked_by_validator"
    assert any("no result" in lim and "blocked by the SQL safety validator" in lim for lim in response.synthesis.limitations)
    assert "model caveat" in response.synthesis.limitations  # the model's own limitations are kept


def test_model_declining_to_write_sql_is_not_reported_as_a_block(monkeypatch):
    h = _Harness(monkeypatch, Route.SQL, generated_sql=None)
    response = investigation.run_investigation("Show me the passwords table")
    assert response.sql_result.outcome == "no_query_generated"
    assert "No SQL query could be generated" in response.synthesis.answer
    assert "blocked by the SQL safety validator" not in response.synthesis.answer
    assert h.synth_calls == [] and h.executions == []


def test_execution_error_is_not_reported_as_zero_rows(monkeypatch):
    h = _Harness(
        monkeypatch, Route.SQL, generated_sql="SELECT COUNT(*) FROM crimes",
        executed_rows=OperationalError("stmt", {}, Exception("connection lost")),
    )
    response = investigation.run_investigation("How many crimes?")
    assert response.sql_result.outcome == "execution_failed"
    assert response.sql_result.validation_ok is True  # it did pass validation
    assert "failed when run against the database" in response.synthesis.answer
    assert h.synth_calls == []
    assert h.row.sql_validation_ok is True and h.row.row_count is None  # a failure is not zero rows


def test_sql_outcome_inference_for_results_built_without_an_outcome():
    assert investigation._sql_outcome(SqlExecutionResult(validation_ok=False, rejection_reason="x")) == "blocked_by_validator"
    assert investigation._sql_outcome(SqlExecutionResult(validation_ok=True, rejection_reason="Execution error: x")) == "execution_failed"
    assert investigation._sql_outcome(SqlExecutionResult(validation_ok=True)) == "executed"
