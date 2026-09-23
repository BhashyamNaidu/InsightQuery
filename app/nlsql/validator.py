"""Deterministic, AST-level validator for LLM-generated SQL.

This is the single most important safety boundary in the whole system: the LLM proposes
SQL, but this module — not the LLM, not a string-replace filter — decides whether it ever
touches the database. Nothing here trusts the model's intent; everything is a structural
check on the parsed statement.

Defense in depth beyond this module: the validated SQL is executed over a Postgres role
with SELECT-only grants on exactly these four tables (see scripts/init_db_roles.sql), with
a statement timeout set on the connection. A bug here should degrade to "query rejected",
never to "query executed with elevated privilege."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.core.config import get_settings
from app.nlsql.schema import ALL_ALLOWED_COLUMNS, ALLOWED_TABLES

DISALLOWED_STATEMENT_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Grant,
    exp.Merge,
    exp.Command,  # sqlglot's catch-all for statements it can't otherwise classify
)

BANNED_FUNCTIONS = {
    "pg_sleep",
    "dblink",
    "dblink_connect",
    "dblink_exec",
    "lo_import",
    "lo_export",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "set_config",
    "current_setting",
    "copy_from_program",
    "pg_reload_conf",
}

DISALLOWED_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "pg_temp"}


@dataclass
class ValidationResult:
    ok: bool
    sql: str | None = None  # the (possibly LIMIT-augmented) SQL that is safe to execute
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def validate_sql(raw_sql: str, *, max_row_limit: int | None = None) -> ValidationResult:
    max_row_limit = max_row_limit or get_settings().sql_row_limit

    sql = (raw_sql or "").strip()
    if not sql:
        return ValidationResult(ok=False, reason="Empty SQL.")

    # Comments are never needed for legitimate analytical queries here and are a classic
    # way to smuggle statement-stacking or hide payloads from naive string checks — reject
    # outright rather than trying to strip them safely.
    if "--" in sql or "/*" in sql:
        return ValidationResult(ok=False, reason="SQL comments are not permitted.")

    sql = sql.rstrip(";").strip()

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except Exception as exc:  # sqlglot raises various ParseError subclasses
        return ValidationResult(ok=False, reason=f"SQL failed to parse: {exc}")

    if len(statements) != 1:
        return ValidationResult(
            ok=False,
            reason="Exactly one SQL statement is permitted (no statement stacking).",
        )

    statement = statements[0]

    if isinstance(statement, DISALLOWED_STATEMENT_TYPES):
        return ValidationResult(
            ok=False,
            reason=(
                f"Statement type '{type(statement).__name__}' is not permitted; "
                "only SELECT is allowed."
            ),
        )

    if not isinstance(statement, (exp.Select, exp.Union)):
        return ValidationResult(ok=False, reason="Only SELECT statements are permitted.")

    if statement.args.get("locks"):
        return ValidationResult(ok=False, reason="Locking clauses (FOR UPDATE/SHARE) are not permitted.")

    # CTE names (`WITH monthly AS (...)`) are virtual tables scoped to this statement: the
    # SELECT that *defines* a CTE is still validated against the real allow-list below, so
    # it's safe to treat references to the CTE's own name as allowed.
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE) if cte.alias}

    tables = list(statement.find_all(exp.Table))
    if not tables:
        return ValidationResult(ok=False, reason="Query does not reference any allowed table.")

    for table in tables:
        table_name = (table.name or "").lower()
        schema_name = (table.db or "").lower()
        if table_name in cte_names:
            continue
        if schema_name in DISALLOWED_SCHEMAS:
            return ValidationResult(
                ok=False, reason=f"Access to schema '{schema_name}' is not permitted."
            )
        if table_name not in ALLOWED_TABLES:
            return ValidationResult(
                ok=False,
                reason=(
                    f"Table '{table_name}' is not in the allowed table list "
                    f"{sorted(ALLOWED_TABLES)}."
                ),
            )

    # Column allow-list: every referenced column name must exist somewhere in the allowed
    # schema, OR be an alias this statement itself defines (e.g. `COUNT(*) AS n` referenced
    # later in ORDER BY — sqlglot parses that back-reference as a bare Column node since it
    # has no live catalog to resolve it against). This does not bind a column to its
    # specific table (that requires full semantic qualification via sqlglot's optimizer,
    # which needs a live schema catalog) — it is a coarse but effective backstop given none
    # of the four allowed tables holds sensitive data. See docs/SQL_SAFETY.md.
    alias_names = {a.alias.lower() for a in statement.find_all(exp.Alias) if a.alias}
    allowed_names = ALL_ALLOWED_COLUMNS | alias_names | cte_names

    for column in statement.find_all(exp.Column):
        col_name = (column.name or "").lower()
        if col_name and col_name != "*" and col_name not in allowed_names:
            return ValidationResult(
                ok=False, reason=f"Column '{col_name}' is not in the allowed column list."
            )

    sql_lower = statement.sql(dialect="postgres").lower()
    for banned in BANNED_FUNCTIONS:
        if re.search(rf"\b{re.escape(banned)}\s*\(", sql_lower):
            return ValidationResult(ok=False, reason=f"Use of function '{banned}' is not permitted.")

    warnings: list[str] = []
    existing_limit = statement.args.get("limit")
    if existing_limit is not None:
        limit_expr = existing_limit.expression if hasattr(existing_limit, "expression") else None
        try:
            limit_value = int(limit_expr.this) if limit_expr is not None else int(existing_limit.this)
        except (AttributeError, ValueError, TypeError):
            return ValidationResult(ok=False, reason="Could not parse LIMIT clause.")
        if limit_value > max_row_limit:
            return ValidationResult(
                ok=False,
                reason=(
                    f"Requested LIMIT {limit_value} exceeds the maximum allowed "
                    f"({max_row_limit})."
                ),
            )
    else:
        statement = statement.limit(max_row_limit)
        warnings.append(f"No LIMIT specified; applied default LIMIT {max_row_limit}.")

    return ValidationResult(ok=True, sql=statement.sql(dialect="postgres"), warnings=warnings)
