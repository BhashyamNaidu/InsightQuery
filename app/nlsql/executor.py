"""Executes already-validated SQL over the least-privilege read-only role.

This module intentionally has no branching logic on the SQL content — by the time
anything reaches here, validate_sql() has already accepted it. Keeping execution
"dumb" is deliberate: the validator is the one place safety decisions are made.
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import ReadOnlySessionLocal


def execute_readonly(sql: str) -> list[dict]:
    settings = get_settings()
    with ReadOnlySessionLocal() as session:
        session.execute(text(f"SET statement_timeout = {settings.sql_statement_timeout_ms}"))
        result = session.execute(text(sql))
        return [dict(row._mapping) for row in result]
