"""Tests for the dashboard HTML pages and the API endpoints that back them
(/investigations, /evaluations). The pages themselves are static Jinja2 templates
that fetch data client-side, so testing "does the page render" and "does the
backing endpoint return the right shape" covers the meaningful surface — the
client-side rendering logic (app/static/js/*.js) isn't unit-testable without a
browser, and was verified manually against the live system instead.
"""
from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestDashboardPages:
    def test_investigate_page_renders(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ask an investigation question" in response.text
        assert "/static/js/investigate.js" in response.text

    def test_history_page_renders(self):
        response = client.get("/history")
        assert response.status_code == 200
        assert "Investigation history" in response.text

    def test_metrics_page_renders(self):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "Evaluation metrics" in response.text

    def test_static_css_is_served(self):
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_static_js_is_served(self):
        response = client.get("/static/js/common.js")
        assert response.status_code == 200


class TestEvaluationsEndpoint:
    def test_returns_null_for_reports_that_have_not_been_run(self, monkeypatch, tmp_path):
        from app.api import routes

        monkeypatch.setattr(routes, "DOCS_DIR", tmp_path)  # empty dir: nothing has been run

        response = client.get("/evaluations")
        assert response.status_code == 200
        body = response.json()
        assert body == {"summary": None, "rag": None, "intent": None, "nl2sql": None, "e2e": None}

    def test_returns_saved_report_when_present(self, monkeypatch, tmp_path):
        from app.api import routes
        import json

        (tmp_path / "rag_eval_results.json").write_text(json.dumps({"recall_at_5": 1.0, "mrr": 0.9}))
        monkeypatch.setattr(routes, "DOCS_DIR", tmp_path)

        response = client.get("/evaluations")
        assert response.status_code == 200
        assert response.json()["rag"] == {"recall_at_5": 1.0, "mrr": 0.9}

    def test_malformed_json_file_does_not_crash_endpoint(self, monkeypatch, tmp_path):
        from app.api import routes

        (tmp_path / "intent_eval_results.json").write_text("{not valid json")
        monkeypatch.setattr(routes, "DOCS_DIR", tmp_path)

        response = client.get("/evaluations")
        assert response.status_code == 200
        assert response.json()["intent"] is None


class TestInvestigationsEndpoint:
    def test_returns_list_shape(self):
        response = client.get("/investigations?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert isinstance(body["results"], list)

    def test_limit_out_of_range_rejected(self):
        response = client.get("/investigations?limit=0")
        assert response.status_code == 422

        response = client.get("/investigations?limit=1000")
        assert response.status_code == 422

    def test_result_entries_have_expected_fields(self):
        response = client.get("/investigations?limit=1")
        body = response.json()
        if body["results"]:
            entry = body["results"][0]
            for field in ("id", "question", "route", "sql_validation_ok", "row_count", "latency_ms", "created_at"):
                assert field in entry
