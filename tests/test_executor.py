"""Regression test for a real bug: SQLAlchemy's text() construct treats `:word` as a
bind parameter — including inside a string literal — whenever the colon isn't itself
preceded by a word character (so `::cast` and mid-word colons like "14:30" are safe,
but a value like `' :UNKNOWN'` is not). A generated query containing such a literal
would raise "a value is required for bind parameter" if executed via
session.execute(text(sql)). execute_readonly() must use Connection.exec_driver_sql()
instead, which passes the SQL to the driver unmodified. See app/nlsql/executor.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import create_engine, text


def test_text_construct_misparses_colon_in_string_literal_as_bind_param():
    """Documents the underlying SQLAlchemy behavior that motivated the fix — if this
    test ever starts failing because SQLAlchemy changed this behavior, the workaround
    in executor.py may no longer be necessary (but would still be harmless)."""
    t = text("SELECT * FROM crimes WHERE location_description = ' :UNKNOWN'")
    assert "UNKNOWN" in t._bindparams

    # Confirms the false-negative cases (::cast and mid-word colons) that make this
    # bug easy to miss in casual testing — both are silently fine with text().
    assert text("SELECT occurred_at::date FROM crimes")._bindparams == {}
    assert text("SELECT * FROM crimes WHERE description = '14:30'")._bindparams == {}


def test_exec_driver_sql_handles_colon_in_string_literal_correctly():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE crimes (location_description TEXT)")
        conn.exec_driver_sql("INSERT INTO crimes VALUES (' :UNKNOWN')")
        result = conn.exec_driver_sql(
            "SELECT * FROM crimes WHERE location_description = ' :UNKNOWN'"
        )
        rows = [dict(r._mapping) for r in result]
    assert rows == [{"location_description": " :UNKNOWN"}]


def test_execute_readonly_uses_exec_driver_sql_not_text_execute(monkeypatch):
    """Pins the implementation choice: execute_readonly must route the generated SQL
    through exec_driver_sql, not session.execute(text(...))."""
    from app.nlsql import executor

    fake_connection = MagicMock()
    fake_connection.exec_driver_sql.return_value = []

    fake_session = MagicMock()
    fake_session.connection.return_value = fake_connection
    fake_session.__enter__.return_value = fake_session
    fake_session.__exit__.return_value = False

    monkeypatch.setattr(executor, "ReadOnlySessionLocal", lambda: fake_session)

    sql = "SELECT * FROM crimes WHERE location_description = ' :UNKNOWN' LIMIT 200"
    result = executor.execute_readonly(sql)

    assert result == []
    fake_connection.exec_driver_sql.assert_called_once_with(sql)
