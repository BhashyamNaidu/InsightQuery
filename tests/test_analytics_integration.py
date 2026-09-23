"""Real integration tests against a live Postgres database — the analytics module
uses Postgres-specific syntax (FILTER, STDDEV_POP, ::date casts, named bind params
with a None default) that a syntax check alone can't fully validate. Skipped
automatically if no database is reachable (e.g. Docker isn't running), rather than
failing, so this suite doesn't block environments without a live DB.

Regression coverage: monthly_trend() and day_of_week_pattern() raised
psycopg.errors.AmbiguousParameter when called with their default primary_type=None,
because a bind parameter appearing only in `IS NULL` / equality contexts gives
psycopg3 no type information to send to Postgres. Found by actually running these
functions against the live database — sqlglot-based static validation
(test_analytics_queries.py) has no way to catch this class of bug, since the SQL is
syntactically valid; it only fails at the protocol/execution layer.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.analytics import queries as q
from app.db.session import SessionLocal


def _db_available() -> bool:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="No live database reachable")


class TestAnalyticsQueriesExecuteSuccessfully:
    def test_monthly_trend_with_no_filter(self):
        with SessionLocal() as session:
            result = q.monthly_trend(session)
        assert isinstance(result.rows, list)

    def test_monthly_trend_with_default_none_primary_type_does_not_raise(self):
        """The exact regression: primary_type=None (the function's own default)
        used to raise AmbiguousParameter."""
        with SessionLocal() as session:
            result = q.monthly_trend(session, primary_type=None)
        assert isinstance(result.rows, list)

    def test_monthly_trend_with_a_real_category(self):
        with SessionLocal() as session:
            result = q.monthly_trend(session, primary_type="THEFT")
        assert isinstance(result.rows, list)

    def test_day_of_week_pattern_with_default_none_primary_type_does_not_raise(self):
        with SessionLocal() as session:
            result = q.day_of_week_pattern(session, primary_type=None)
        assert isinstance(result.rows, list)

    def test_day_of_week_pattern_with_a_real_category(self):
        with SessionLocal() as session:
            result = q.day_of_week_pattern(session, primary_type="BATTERY")
        assert isinstance(result.rows, list)

    def test_top_crime_types(self):
        with SessionLocal() as session:
            result = q.top_crime_types(session, limit=5)
        assert len(result.rows) <= 5

    def test_district_comparison(self):
        with SessionLocal() as session:
            result = q.district_comparison(session)
        assert isinstance(result.rows, list)

    def test_community_area_breakdown(self):
        with SessionLocal() as session:
            result = q.community_area_breakdown(session, top_n=10)
        assert len(result.rows) <= 10

    def test_monthly_anomalies(self):
        with SessionLocal() as session:
            result = q.monthly_anomalies(session, primary_type="HOMICIDE")
        assert isinstance(result.rows, list)

    def test_arrest_rate_by_type(self):
        with SessionLocal() as session:
            result = q.arrest_rate_by_type(session, limit=10)
        assert len(result.rows) <= 10
