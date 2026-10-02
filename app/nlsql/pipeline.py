"""The single NL-to-SQL path: generate -> validate -> execute (read-only) -> at most one
repair attempt on a PostgreSQL execution error. The investigation service, the
/sql/query endpoint, and the evaluation script all call this, so what gets measured is
exactly what ships.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import DataError, ProgrammingError

from app.nlsql.executor import execute_readonly
from app.nlsql.generator import SqlGenerationResult, generate_sql, repair_sql

logger = logging.getLogger(__name__)

# Only errors that mean "this SQL is wrong" are worth a repair attempt. A dropped
# connection or statement timeout (OperationalError) fails identically on retry.
_REPAIRABLE = (ProgrammingError, DataError)


@dataclass
class SqlPipelineResult:
    generation: SqlGenerationResult  # the final attempt (the repair, if one happened)
    rows: list[dict] | None  # None unless execution succeeded
    execution_error: str | None
    repaired: bool
    first_attempt_sql: str | None = None
    first_attempt_error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def run_sql_pipeline(question: str) -> SqlPipelineResult:
    first = generate_sql(question)  # LlmError propagates; callers degrade explicitly
    tokens_in, tokens_out = first.input_tokens, first.output_tokens

    if not first.validation.ok:
        return SqlPipelineResult(first, None, None, False, input_tokens=tokens_in, output_tokens=tokens_out)

    try:
        rows = execute_readonly(first.validation.sql)
        return SqlPipelineResult(first, rows, None, False, input_tokens=tokens_in, output_tokens=tokens_out)
    except _REPAIRABLE as exc:
        first_error = str(getattr(exc, "orig", exc))
        logger.info("SQL failed at execution, attempting one repair: %s", first_error[:200])
    except Exception as exc:  # noqa: BLE001 - not repairable (e.g. DB down/timeout)
        return SqlPipelineResult(first, None, str(exc), False, input_tokens=tokens_in, output_tokens=tokens_out)

    try:
        second = repair_sql(question, first.validation.sql, first_error)
    except Exception as exc:  # noqa: BLE001 - LlmError etc.: keep the original failure
        logger.warning("SQL repair call failed: %s", exc)
        return SqlPipelineResult(
            first, None, first_error, False,
            first_attempt_sql=first.validation.sql, first_attempt_error=first_error,
            input_tokens=tokens_in, output_tokens=tokens_out,
        )

    tokens_in += second.input_tokens
    tokens_out += second.output_tokens
    common = dict(
        repaired=True, first_attempt_sql=first.validation.sql, first_attempt_error=first_error,
        input_tokens=tokens_in, output_tokens=tokens_out,
    )
    if not second.validation.ok:
        return SqlPipelineResult(second, None, None, **common)

    try:
        rows = execute_readonly(second.validation.sql)
        return SqlPipelineResult(second, rows, None, **common)
    except Exception as exc:  # noqa: BLE001
        return SqlPipelineResult(second, None, str(getattr(exc, "orig", exc)), **common)
