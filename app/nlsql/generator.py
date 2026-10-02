"""LLM proposes SQL; this module never trusts it — every result is run through
validate_sql() before anything downstream sees it as "safe SQL." See validator.py
for why that boundary exists."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.client import complete
from app.llm.prompts import SQL_GENERATION_SYSTEM_PROMPT, SQL_REPAIR_ADDENDUM
from app.nlsql.validator import ValidationResult, validate_sql

_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


@dataclass
class SqlGenerationResult:
    raw_sql: str | None
    validation: ValidationResult
    llm_model: str
    llm_provider: str
    input_tokens: int
    output_tokens: int


def generate_sql(question: str) -> SqlGenerationResult:
    response = complete(SQL_GENERATION_SYSTEM_PROMPT, question)
    raw = _FENCE_RE.sub("", response.text).strip()

    if not raw or raw.upper().startswith("NO_QUERY"):
        return SqlGenerationResult(
            raw_sql=None,
            validation=ValidationResult(
                ok=False, reason="Model determined the question is not answerable via SQL."
            ),
            llm_model=response.model,
            llm_provider=response.provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

    validation = validate_sql(raw)
    return SqlGenerationResult(
        raw_sql=raw,
        validation=validation,
        llm_model=response.model,
        llm_provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


_MAX_ERROR_CHARS = 300


def repair_sql(question: str, failed_sql: str, db_error: str) -> SqlGenerationResult:
    """One bounded repair attempt after PostgreSQL rejected an already-validated query
    at execution time (type mismatch, bad alias, ...). The database error text is
    truncated and passed back as context; the model's new SQL is untrusted like any
    other LLM output and goes through validate_sql() again in full — this never
    bypasses the validator, and is only ever used for execution errors, never to
    "fix" a query the validator rejected (that would be asking the model to route
    around the safety boundary).
    """
    error_line = " ".join(db_error.split())[:_MAX_ERROR_CHARS]
    user_prompt = (
        f"Question: {question}\n\n"
        f"Previous SQL:\n{failed_sql}\n\n"
        f"PostgreSQL error: {error_line}"
    )
    response = complete(SQL_GENERATION_SYSTEM_PROMPT + SQL_REPAIR_ADDENDUM, user_prompt)
    raw = _FENCE_RE.sub("", response.text).strip()

    if not raw or raw.upper().startswith("NO_QUERY"):
        validation = ValidationResult(ok=False, reason="Repair attempt produced no SQL.")
        raw = None
    else:
        validation = validate_sql(raw)

    return SqlGenerationResult(
        raw_sql=raw,
        validation=validation,
        llm_model=response.model,
        llm_provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
