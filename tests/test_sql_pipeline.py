"""Tests for app/nlsql/pipeline.py — the generate -> validate -> execute -> (one) repair
path. The LLM and database are mocked; what's under test is the control flow and,
above all, the security properties of the repair step:

  - a query the VALIDATOR rejected is never "repaired" (that would ask the model to
    route around the safety boundary),
  - a repaired query is validated again in full before it runs,
  - only SQL-level execution errors trigger a repair, never infrastructure failures,
  - at most one repair attempt ever happens.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.nlsql import pipeline
from app.nlsql.generator import SqlGenerationResult
from app.nlsql.validator import ValidationResult, validate_sql


def _gen(sql: str | None, ok: bool = True, reason: str | None = None) -> SqlGenerationResult:
    validation = (
        ValidationResult(ok=True, sql=sql + " LIMIT 200") if ok else ValidationResult(ok=False, reason=reason)
    )
    return SqlGenerationResult(
        raw_sql=sql, validation=validation, llm_model="m", llm_provider="p", input_tokens=10, output_tokens=5
    )


def _sql_error(msg: str = 'operator does not exist: character varying = integer') -> ProgrammingError:
    return ProgrammingError("SELECT ...", {}, Exception(msg))


def test_success_on_first_attempt_does_not_repair(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT 1 FROM crimes"))
    monkeypatch.setattr(pipeline, "execute_readonly", lambda sql: [{"n": 1}])
    monkeypatch.setattr(pipeline, "repair_sql", lambda *a: pytest.fail("repair must not run"))

    result = pipeline.run_sql_pipeline("q")

    assert result.rows == [{"n": 1}]
    assert result.repaired is False


def test_validator_rejection_is_never_repaired(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("DROP TABLE crimes", ok=False, reason="nope"))
    monkeypatch.setattr(pipeline, "execute_readonly", lambda sql: pytest.fail("must not execute"))
    monkeypatch.setattr(pipeline, "repair_sql", lambda *a: pytest.fail("repair must not run"))

    result = pipeline.run_sql_pipeline("drop everything")

    assert result.generation.validation.ok is False
    assert result.rows is None
    assert result.repaired is False


def test_sql_execution_error_triggers_exactly_one_repair_that_can_succeed(monkeypatch):
    calls = {"exec": 0, "repair": 0}

    def execute(sql):
        calls["exec"] += 1
        if "'005'" not in sql:
            raise _sql_error()
        return [{"id": 1}]

    def repair(question, failed_sql, err):
        calls["repair"] += 1
        assert "character varying" in err  # DB error text is passed back as context
        return _gen("SELECT id FROM crimes WHERE district_code = '005'")

    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT id FROM crimes WHERE district_code = 5"))
    monkeypatch.setattr(pipeline, "execute_readonly", execute)
    monkeypatch.setattr(pipeline, "repair_sql", repair)

    result = pipeline.run_sql_pipeline("crimes in district 5")

    assert result.rows == [{"id": 1}]
    assert result.repaired is True
    assert result.first_attempt_error and "character varying" in result.first_attempt_error
    assert calls == {"exec": 2, "repair": 1}
    assert result.input_tokens == 20  # tokens from both LLM calls are accounted for


def test_repair_that_also_fails_is_not_retried_again(monkeypatch):
    calls = {"repair": 0}

    def repair(*a):
        calls["repair"] += 1
        return _gen("SELECT bad FROM crimes")

    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT bad1 FROM crimes"))
    monkeypatch.setattr(pipeline, "execute_readonly", lambda sql: (_ for _ in ()).throw(_sql_error("boom")))
    monkeypatch.setattr(pipeline, "repair_sql", repair)

    result = pipeline.run_sql_pipeline("q")

    assert calls["repair"] == 1
    assert result.rows is None
    assert result.repaired is True
    assert "boom" in result.execution_error


def test_repaired_sql_that_fails_validation_is_never_executed(monkeypatch):
    """A repair is untrusted LLM output like any other: if the 'fix' is unsafe, it must be
    rejected by the validator and never reach the database."""
    executed = []

    def execute(sql):
        executed.append(sql)
        raise _sql_error()

    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT bad FROM crimes"))
    monkeypatch.setattr(pipeline, "execute_readonly", execute)
    monkeypatch.setattr(
        pipeline, "repair_sql", lambda *a: _gen("DELETE FROM crimes", ok=False, reason="not permitted")
    )

    result = pipeline.run_sql_pipeline("q")

    assert len(executed) == 1  # only the original attempt ever ran
    assert result.generation.validation.ok is False
    assert result.rows is None


def test_infrastructure_failure_is_not_repaired(monkeypatch):
    """A dropped connection / statement timeout fails identically on retry — asking the
    LLM to rewrite the SQL would be wasted cost and could mask the real problem."""
    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT 1 FROM crimes"))
    monkeypatch.setattr(
        pipeline,
        "execute_readonly",
        lambda sql: (_ for _ in ()).throw(OperationalError("SELECT", {}, Exception("connection lost"))),
    )
    monkeypatch.setattr(pipeline, "repair_sql", lambda *a: pytest.fail("repair must not run"))

    result = pipeline.run_sql_pipeline("q")

    assert result.rows is None
    assert result.repaired is False
    assert "connection lost" in result.execution_error


def test_repair_llm_failure_keeps_the_original_error(monkeypatch):
    from app.llm.client import LlmError

    def repair(*a):
        raise LlmError("provider down")

    monkeypatch.setattr(pipeline, "generate_sql", lambda q: _gen("SELECT bad FROM crimes"))
    monkeypatch.setattr(pipeline, "execute_readonly", lambda sql: (_ for _ in ()).throw(_sql_error("orig error")))
    monkeypatch.setattr(pipeline, "repair_sql", repair)

    result = pipeline.run_sql_pipeline("q")

    assert result.rows is None
    assert "orig error" in result.execution_error


class TestRepairSqlPrompt:
    def test_db_error_is_truncated_and_repaired_sql_is_revalidated(self, monkeypatch):
        from dataclasses import dataclass

        from app.nlsql import generator

        @dataclass
        class R:
            text: str
            model: str = "m"
            provider: str = "p"
            input_tokens: int = 1
            output_tokens: int = 1

        captured = {}

        def fake_complete(system, user, max_tokens=None):
            captured["user"] = user
            return R("```sql\nSELECT 1 FROM crimes; DROP TABLE crimes\n```")

        monkeypatch.setattr(generator, "complete", fake_complete)
        result = generator.repair_sql("q", "SELECT bad", "x" * 5000)

        assert len(captured["user"]) < 1000  # a huge DB error can't blow up the prompt
        assert result.validation.ok is False  # stacked statement from the "repair" is rejected
        assert validate_sql("SELECT 1 FROM crimes; DROP TABLE crimes").ok is False


class TestSecurityBoundaryWithRealValidator:
    """These use the REAL validate_sql (not a mocked verdict), so they prove the property
    that matters: malicious SQL reaches neither execution nor the repair path."""

    @staticmethod
    def _real_gen(sql: str) -> SqlGenerationResult:
        return SqlGenerationResult(
            raw_sql=sql, validation=validate_sql(sql), llm_model="m", llm_provider="p",
            input_tokens=1, output_tokens=1,
        )

    @pytest.mark.parametrize(
        "malicious",
        [
            "DROP TABLE crimes",
            "SELECT * FROM crimes; DROP TABLE crimes",
            "DELETE FROM crimes WHERE 1=1",
            "SELECT * FROM query_log",
            "SELECT * FROM information_schema.tables",
            "SELECT pg_sleep(10)",
            "SELECT * FROM crimes -- ; DROP TABLE crimes",
        ],
    )
    def test_malicious_sql_gets_no_execution_and_no_repair(self, monkeypatch, malicious):
        monkeypatch.setattr(pipeline, "generate_sql", lambda q: self._real_gen(malicious))
        monkeypatch.setattr(pipeline, "execute_readonly", lambda sql: pytest.fail("executed unsafe SQL"))
        monkeypatch.setattr(pipeline, "repair_sql", lambda *a: pytest.fail("repair path reached for rejected SQL"))

        result = pipeline.run_sql_pipeline("q")

        assert result.generation.validation.ok is False
        assert result.rows is None
        assert result.repaired is False
        assert result.first_attempt_sql is None

    def test_unsafe_repair_is_rejected_by_the_real_validator_and_never_executed(self, monkeypatch):
        executed = []
        monkeypatch.setattr(pipeline, "generate_sql", lambda q: self._real_gen("SELECT SUM(arrest) FROM crimes"))

        def execute(sql):
            executed.append(sql)
            raise _sql_error()

        monkeypatch.setattr(pipeline, "execute_readonly", execute)
        monkeypatch.setattr(pipeline, "repair_sql", lambda *a: self._real_gen("DROP TABLE crimes"))

        result = pipeline.run_sql_pipeline("q")

        assert len(executed) == 1  # the original attempt only; the unsafe "repair" never ran
        assert result.repaired is True
        assert result.generation.validation.ok is False
        assert result.first_attempt_sql is not None  # still visible in the audit trail
