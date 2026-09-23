"""These hand-written analytics queries use Postgres-specific syntax (FILTER,
STDDEV_POP, EXTRACT(ISODOW ...), date_trunc) that SQLite can't execute, so a full
integration test needs a live Postgres (see scripts/ingest_data.py + a real DB).
What we CAN check without one: every query is syntactically valid Postgres SQL, and
none of them accidentally violate the same safety properties the NL-to-SQL validator
enforces on LLM-generated SQL (single statement, SELECT-only, bounded) — these are
hand-written and run over the app's own DB session rather than the read-only role, so
they're not passed through validate_sql(), but there's no reason they should look any
less safe than what that validator would accept.
"""
import inspect
import re

import sqlglot
import sqlglot.errors

from app.analytics import queries as analytics_queries

# sqlglot's postgres dialect doesn't parse SQLAlchemy's named bind-param syntax
# (`:limit`) as a value in every clause position (e.g. LIMIT). These queries are
# executed by SQLAlchemy, which handles the substitution — this test only cares
# whether the SQL is otherwise structurally valid, so bind params are swapped for
# literal placeholders before parsing.
_BIND_PARAM_RE = re.compile(r"(?<!:):(\w+)")


def _strip_bind_params(sql: str) -> str:
    return _BIND_PARAM_RE.sub("1", sql)


def _all_query_functions():
    return [
        func
        for name, func in inspect.getmembers(analytics_queries, inspect.isfunction)
        if func.__module__ == analytics_queries.__name__
    ]


def _sql_from_function_source(func) -> str:
    # Each function builds its SQL as a `sql = """ ... """` literal; extract it by
    # calling the function with a stub session that just records the SQL text passed
    # to session.execute(), rather than parsing source code.
    captured = {}

    class StubResult:
        def __iter__(self):
            return iter([])

    class StubSession:
        def execute(self, statement, params=None):
            captured["sql"] = str(statement)
            return StubResult()

    sig = inspect.signature(func)
    kwargs = {}
    for pname, param in sig.parameters.items():
        if pname == "session":
            continue
        if param.default is inspect.Parameter.empty:
            kwargs[pname] = "BATTERY"  # plausible primary_type for functions requiring one
    func(StubSession(), **kwargs)
    return captured["sql"]


def test_every_analytics_query_is_valid_postgres_sql():
    for func in _all_query_functions():
        sql = _sql_from_function_source(func)
        try:
            parsed = sqlglot.parse_one(_strip_bind_params(sql), read="postgres")
        except sqlglot.errors.ParseError as exc:
            raise AssertionError(f"{func.__name__} produced invalid SQL: {exc}\nSQL:\n{sql}")
        assert parsed is not None, f"{func.__name__} produced empty SQL"


def test_every_analytics_query_is_select_only():
    from sqlglot import exp

    for func in _all_query_functions():
        sql = _sql_from_function_source(func)
        parsed = sqlglot.parse_one(_strip_bind_params(sql), read="postgres")
        assert isinstance(parsed, exp.Select), f"{func.__name__} is not a SELECT statement"


def test_every_analytics_query_has_a_limit_or_is_a_single_aggregate():
    from sqlglot import exp

    for func in _all_query_functions():
        sql = _sql_from_function_source(func)
        parsed = sqlglot.parse_one(_strip_bind_params(sql), read="postgres")
        has_limit = parsed.args.get("limit") is not None
        # Checked anywhere in the tree (not just the outer SELECT) so a CTE that
        # groups internally (e.g. monthly_anomalies) counts too.
        has_group_by = any(True for _ in parsed.find_all(exp.Group))
        # Queries without an explicit LIMIT here are grouped aggregates whose row count
        # is bounded by the underlying dimension table (<=22 districts, <=76 areas, etc)
        # or, for monthly_anomalies, by the CTE's own GROUP BY (<=12 months) — never an
        # unbounded raw-row scan.
        assert has_limit or has_group_by, f"{func.__name__} has neither LIMIT nor GROUP BY"
