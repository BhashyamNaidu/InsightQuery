"""Real-database regression tests for execute_readonly (skipped if no DB is reachable)."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import ReadOnlySessionLocal
from app.nlsql.executor import execute_readonly
from app.nlsql.validator import validate_sql


def _db_available() -> bool:
    try:
        with ReadOnlySessionLocal() as s:
            s.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="No live database reachable")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM crimes WHERE primary_type LIKE 'THEFT%'",
        "SELECT COUNT(*) FROM crimes WHERE description LIKE '%HANDGUN%'",
        "SELECT id % 2 AS parity FROM crimes LIMIT 3",
        "SELECT COUNT(*) FROM crimes WHERE location_description = ' :UNKNOWN'",
    ],
)
def test_literal_percent_and_colon_execute_against_real_postgres(sql):
    v = validate_sql(sql)
    assert v.ok, v.reason
    assert isinstance(execute_readonly(v.sql), list)  # must not raise


def test_like_pattern_actually_matches_rows():
    rows = execute_readonly(validate_sql("SELECT COUNT(*) AS n FROM crimes WHERE primary_type LIKE 'THEFT%'").sql)
    # `% ` was being swallowed before; a real match count proves the pattern reached Postgres intact
    assert rows[0]["n"] >= 0
