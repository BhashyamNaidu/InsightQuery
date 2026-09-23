"""API-level tests. The investigation pipeline itself (LLM + DB) is exercised via
unit tests on its component modules elsewhere; here we test the API contract —
request/response schemas, status codes, and structured error handling — by
monkeypatching the service-layer entry points so these tests don't need a live
database or a real Anthropic API key.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.investigation import (
    Confidence,
    EvidenceChunk,
    InvestigateResponse,
    Route,
    SqlExecutionResult,
    SynthesisOutput,
)

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200_with_expected_shape(self, monkeypatch):
        from app.api import routes

        class FakeDb:
            def execute(self, *args, **kwargs):
                return None

        def fake_get_db():
            yield FakeDb()

        app.dependency_overrides[routes.get_db] = fake_get_db
        try:
            response = client.get("/health")
        finally:
            app.dependency_overrides.pop(routes.get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        assert body["vector_store"] == "ok"

    def test_health_reports_degraded_on_db_error(self, monkeypatch):
        from app.api import routes

        class FailingDb:
            def execute(self, *args, **kwargs):
                raise RuntimeError("connection refused")

        def fake_get_db():
            yield FailingDb()

        app.dependency_overrides[routes.get_db] = fake_get_db
        try:
            response = client.get("/health")
        finally:
            app.dependency_overrides.pop(routes.get_db, None)

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"


class TestInvestigateEndpoint:
    def test_happy_path_returns_full_trace(self, monkeypatch):
        fake_response = InvestigateResponse(
            request_id="11111111-1111-1111-1111-111111111111",
            question="How did theft change over time?",
            route=Route.HYBRID,
            intent_reasoning="Needs both a trend figure and context.",
            sql_result=SqlExecutionResult(
                generated_sql="SELECT 1",
                executed_sql="SELECT 1 LIMIT 200",
                validation_ok=True,
                rows=[{"month": "2023-01-01", "incident_count": 100}],
                row_count=1,
            ),
            evidence=[
                EvidenceChunk(
                    document_title="Seasonal Crime Patterns",
                    document_source="08_seasonal_crime_patterns.md",
                    content="Crime tends to rise in warmer months.",
                    similarity=0.82,
                )
            ],
            synthesis=SynthesisOutput(
                answer="Theft incidents rose in summer months [source: Seasonal Crime Patterns].",
                citations=["Seasonal Crime Patterns"],
                confidence=Confidence.MEDIUM,
                limitations=["Single year of data."],
            ),
            latency_ms=42,
        )
        monkeypatch.setattr(
            "app.api.routes.run_investigation", lambda question: fake_response
        )

        response = client.post("/investigate", json={"question": "How did theft change over time?"})

        assert response.status_code == 200
        body = response.json()
        assert body["route"] == "hybrid"
        assert body["sql_result"]["row_count"] == 1
        assert body["evidence"][0]["document_title"] == "Seasonal Crime Patterns"
        assert body["synthesis"]["confidence"] == "medium"

    def test_pipeline_exception_returns_structured_500(self, monkeypatch):
        def boom(question: str):
            raise RuntimeError("LLM provider unreachable")

        monkeypatch.setattr("app.api.routes.run_investigation", boom)

        response = client.post("/investigate", json={"question": "anything"})

        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_code"] == "investigation_failed"

    def test_empty_question_rejected_by_validation(self):
        response = client.post("/investigate", json={"question": ""})
        assert response.status_code == 422

    def test_missing_question_field_rejected(self):
        response = client.post("/investigate", json={})
        assert response.status_code == 422

    def test_overlong_question_rejected(self):
        response = client.post("/investigate", json={"question": "a" * 5000})
        assert response.status_code == 422


class TestSqlQueryEndpoint:
    def test_rejected_sql_returns_200_with_reason_not_error(self, monkeypatch):
        # A rejected/unsafe query is a normal, expected outcome of this endpoint,
        # not a server error — the API should say so with a 200 + validation_ok=false,
        # not throw.
        from app.nlsql.generator import SqlGenerationResult
        from app.nlsql.validator import ValidationResult

        def fake_generate_sql(question: str) -> SqlGenerationResult:
            return SqlGenerationResult(
                raw_sql="DROP TABLE crimes",
                validation=ValidationResult(ok=False, reason="Statement type 'Drop' is not permitted."),
                llm_model="claude-sonnet-5",
                input_tokens=10,
                output_tokens=5,
            )

        monkeypatch.setattr("app.api.routes.generate_sql", fake_generate_sql)

        response = client.post("/sql/query", json={"question": "delete everything"})

        assert response.status_code == 200
        body = response.json()
        assert body["validation_ok"] is False
        assert "not permitted" in body["rejection_reason"]

    def test_execution_failure_returns_502(self, monkeypatch):
        from app.nlsql.generator import SqlGenerationResult
        from app.nlsql.validator import ValidationResult

        def fake_generate_sql(question: str) -> SqlGenerationResult:
            return SqlGenerationResult(
                raw_sql="SELECT * FROM crimes",
                validation=ValidationResult(ok=True, sql="SELECT * FROM crimes LIMIT 200"),
                llm_model="claude-sonnet-5",
                input_tokens=10,
                output_tokens=5,
            )

        def fake_execute_readonly(sql: str):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr("app.api.routes.generate_sql", fake_generate_sql)
        monkeypatch.setattr("app.api.routes.execute_readonly", fake_execute_readonly)

        response = client.post("/sql/query", json={"question": "show me everything"})

        assert response.status_code == 502
        assert response.json()["detail"]["error_code"] == "sql_execution_failed"

    def test_llm_call_failure_returns_502_not_generic_500(self, monkeypatch):
        # Found via live testing without an Anthropic API key configured: an LLM
        # failure during SQL generation fell through to the generic unhandled-
        # exception handler (500, "internal_error") instead of being distinguished
        # from a genuine application bug, unlike the execution-failure path above.
        from app.llm.client import LlmError

        def fake_generate_sql(question: str):
            raise LlmError("LLM call failed: connection error")

        monkeypatch.setattr("app.api.routes.generate_sql", fake_generate_sql)

        response = client.post("/sql/query", json={"question": "how many thefts happened"})

        assert response.status_code == 502
        assert response.json()["detail"]["error_code"] == "llm_call_failed"


class TestEvidenceEndpoint:
    def test_invalid_uuid_returns_400(self):
        response = client.get("/evidence/not-a-uuid")
        assert response.status_code == 400
        assert response.json()["detail"]["error_code"] == "invalid_id"

    def test_unknown_id_returns_404(self, monkeypatch):
        from app.api import routes

        class FakeDb:
            def get(self, model, id_):
                return None

        def fake_get_db():
            yield FakeDb()

        app.dependency_overrides[routes.get_db] = fake_get_db
        try:
            response = client.get("/evidence/11111111-1111-1111-1111-111111111111")
        finally:
            app.dependency_overrides.pop(routes.get_db, None)

        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "not_found"


class TestRagRetrieveEndpoint:
    def test_top_k_out_of_range_rejected(self):
        response = client.post("/rag/retrieve", json={"question": "what is a beat?", "top_k": 0})
        assert response.status_code == 422

        response = client.post("/rag/retrieve", json={"question": "what is a beat?", "top_k": 100})
        assert response.status_code == 422
