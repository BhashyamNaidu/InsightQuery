"""Executes already-validated SQL over the least-privilege read-only role.

This module intentionally has no branching logic on the SQL content — by the time
anything reaches here, validate_sql() has already accepted it. Keeping execution
"dumb" is deliberate: the validator is the one place safety decisions are made.

Uses Connection.exec_driver_sql() rather than session.execute(text(sql)) on purpose:
SQLAlchemy's text() construct scans for `:identifier` sequences and treats them as bind
parameters, including inside string literals, whenever the colon isn't itself preceded by
a word character (so it also isn't fooled by a `::cast` or a mid-word colon like
"14:30") — e.g. a WHERE clause with a value like `' :UNKNOWN'` would make text() demand a
bind value for a parameter named `UNKNOWN` that doesn't exist, raising at execution time
instead of returning results. Generated SQL here is a complete, literal statement with no
bind parameters of its own — exec_driver_sql() passes it to the driver unmodified, which
is what that method is for.
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import ReadOnlySessionLocal


def execute_readonly(sql: str) -> list[dict]:
    settings = get_settings()
    with ReadOnlySessionLocal() as session:
        connection = session.connection()
        connection.execute(text(f"SET statement_timeout = {settings.sql_statement_timeout_ms}"))
        result = connection.exec_driver_sql(sql)
        return [dict(row._mapping) for row in result]
