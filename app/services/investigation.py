"""The unified investigation pipeline: intent -> (SQL and/or RAG) -> synthesis.

This is the only place that ties the deterministic systems (validated SQL,
vector retrieval) to the LLM synthesis call, and it is written so that a
synthesis failure never hides what the deterministic systems already found —
sql_result and evidence are always returned even if synthesis raises.
"""
from __future__ import annotations

import logging
import time
import uuid

from app.core.config import get_settings
from app.llm.client import LlmError
from app.llm.synthesis import synthesize
from app.models import QueryLog
from app.db.session import SessionLocal
from app.nlsql.pipeline import run_sql_pipeline
from app.rag.retrieval import retrieve
from app.schemas.investigation import (
    Confidence,
    EvidenceChunk,
    InvestigateResponse,
    Route,
    SqlExecutionResult,
    SynthesisOutput,
)
from app.services.intent import classify_intent

logger = logging.getLogger(__name__)


def run_investigation(question: str) -> InvestigateResponse:
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    stage_ms: dict[str, int] = {}

    t0 = time.perf_counter()
    intent = classify_intent(question)
    stage_ms["intent"] = int((time.perf_counter() - t0) * 1000)
    route = intent.route

    sql_result: SqlExecutionResult | None = None
    evidence: list[EvidenceChunk] = []
    synthesis: SynthesisOutput | None = None
    llm_model: str | None = None
    llm_input_tokens = 0
    llm_output_tokens = 0

    if route == Route.REJECTED:
        # No SQL generation, no retrieval, no synthesis call: the intent classifier
        # already determined this isn't a good-faith investigation question, and its
        # own reasoning is a sufficient, honest answer — spending further LLM calls on
        # a question already identified as out of scope would just be wasted cost.
        synthesis = SynthesisOutput(
            answer=(
                "This question doesn't appear to be answerable by this system: "
                f"{intent.reasoning}"
            ),
            citations=[],
            confidence=Confidence.HIGH,
            limitations=["Question rejected before SQL generation or retrieval was attempted."],
        )
    else:
        if route in (Route.SQL, Route.HYBRID):
            t0 = time.perf_counter()
            sql_result, tokens = _run_sql_stage(question)
            stage_ms["sql"] = int((time.perf_counter() - t0) * 1000)
            llm_model = tokens[0] or llm_model
            llm_input_tokens += tokens[1]
            llm_output_tokens += tokens[2]

        if route in (Route.RAG, Route.HYBRID):
            t0 = time.perf_counter()
            evidence = _run_rag_stage(question)
            stage_ms["rag"] = int((time.perf_counter() - t0) * 1000)

        # A SQL branch that never produced a result (blocked by the validator, no query
        # generated, generation/execution failed) is NOT "a query that returned zero rows".
        # Passing rows=[] to synthesis made the model read a rejected DELETE as a successful
        # empty result ("No records exist to delete"), so such a branch contributes no SQL
        # evidence at all; when nothing else is left to explain, the answer is a
        # deterministic statement of what happened, with no LLM call.
        sql_missing = sql_result is not None and _sql_outcome(sql_result) != "executed"
        if sql_missing and not evidence and _sql_outcome(sql_result) != "generation_failed":
            # (generation_failed means the LLM itself is down: keep the existing degradation
            # path, where synthesis is attempted without SQL evidence and may degrade to None.)
            synthesis = _no_sql_result_answer(sql_result)
        else:
            t0 = time.perf_counter()
            try:
                synthesis = synthesize(
                    question=question,
                    sql=None if sql_missing else (sql_result.executed_sql if sql_result else None),
                    sql_rows=None if sql_missing else (sql_result.rows if sql_result else None),
                    evidence_chunks=[e.model_dump() for e in evidence],
                    sql_unavailable=_NO_RESULT_SHORT[_sql_outcome(sql_result)] if sql_missing else None,
                )
                if sql_missing:
                    synthesis = _qualify_for_missing_sql(synthesis, sql_result)
            except LlmError:
                logger.exception("Synthesis LLM call failed for request %s", request_id)
            stage_ms["synthesis"] = int((time.perf_counter() - t0) * 1000)

    latency_ms = int((time.perf_counter() - start) * 1000)

    _persist_log(
        request_id=request_id,
        question=question,
        route=route,
        sql_result=sql_result,
        latency_ms=latency_ms,
        stage_ms=stage_ms,
        llm_model=llm_model,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
    )

    return InvestigateResponse(
        request_id=request_id,
        question=question,
        route=route,
        intent_reasoning=intent.reasoning,
        sql_result=sql_result,
        evidence=evidence,
        synthesis=synthesis,
        latency_ms=latency_ms,
        stage_latency_ms=stage_ms,
    )


def _run_sql_stage(question: str) -> tuple[SqlExecutionResult, tuple[str | None, int, int]]:
    try:
        result = run_sql_pipeline(question)
    except LlmError as exc:
        # Same reasoning as classify_intent's LlmError handling: degrade to a
        # rejected result rather than letting this propagate out of
        # run_investigation and skip query_log entirely for the request.
        logger.warning("SQL generation LLM call failed: %s", exc)
        return (
            SqlExecutionResult(
                outcome="generation_failed",
                validation_ok=False,
                rejection_reason=f"SQL generation LLM call failed: {exc}",
            ),
            (None, 0, 0),
        )

    gen = result.generation
    tokens = (gen.llm_model, result.input_tokens, result.output_tokens)
    note = (
        f"First attempt failed in PostgreSQL ({result.first_attempt_error[:160]}); "
        "the query was regenerated once and re-validated."
        if result.repaired and result.first_attempt_error
        else None
    )

    if not gen.validation.ok:
        return (
            SqlExecutionResult(
                outcome="blocked_by_validator" if gen.raw_sql is not None else "no_query_generated",
                generated_sql=gen.raw_sql,
                validation_ok=False,
                rejection_reason=gen.validation.reason,
                repaired=result.repaired,
                repair_note=note,
                first_attempt_sql=result.first_attempt_sql,
                first_attempt_error=result.first_attempt_error,
            ),
            tokens,
        )

    if result.rows is None:
        logger.warning("SQL execution failed: %s", result.execution_error)
        return (
            SqlExecutionResult(
                outcome="execution_failed",
                generated_sql=gen.raw_sql,
                executed_sql=gen.validation.sql,
                validation_ok=True,
                rejection_reason=f"Execution error: {result.execution_error}",
                repaired=result.repaired,
                repair_note=note,
                first_attempt_sql=result.first_attempt_sql,
                first_attempt_error=result.first_attempt_error,
            ),
            tokens,
        )

    return (
        SqlExecutionResult(
            outcome="executed",
            generated_sql=gen.raw_sql,
            executed_sql=gen.validation.sql,
            validation_ok=True,
            rows=result.rows,
            row_count=len(result.rows),
            repaired=result.repaired,
            repair_note=note,
            first_attempt_sql=result.first_attempt_sql,
            first_attempt_error=result.first_attempt_error,
        ),
        tokens,
    )


def _sql_outcome(r: SqlExecutionResult) -> str:
    """The explicit outcome, with a conservative inference for results built without one."""
    if r.outcome:
        return r.outcome
    if not r.validation_ok:
        return "blocked_by_validator"
    return "execution_failed" if r.rejection_reason else "executed"


_NO_RESULT = {
    "blocked_by_validator": (
        "This request was blocked by the SQL safety validator, so no query was run against the "
        "database. Only read-only SELECT queries over the approved analytics tables are permitted.",
        Confidence.HIGH,
    ),
    "no_query_generated": (
        "No SQL query could be generated for this question, so nothing was run against the database.",
        Confidence.HIGH,
    ),
    "generation_failed": (
        "The SQL generation step was unavailable, so no query was run against the database.",
        Confidence.LOW,
    ),
    "execution_failed": (
        "The query passed safety validation but failed when run against the database, "
        "so no result is available.",
        Confidence.LOW,
    ),
}


_NO_RESULT_SHORT = {
    "blocked_by_validator": "the query was blocked by the SQL safety validator and nothing was run",
    "no_query_generated": "no SQL query could be generated",
    "generation_failed": "the SQL generation step was unavailable",
    "execution_failed": "the query failed when run against the database",
}


def _qualify_for_missing_sql(synthesis: SynthesisOutput, r: SqlExecutionResult) -> SynthesisOutput:
    """A hybrid answer written without its database half must say so, whatever the model wrote.

    The model is told (in the prompt) to leave the database part unanswered, but it once
    answered it anyway from general knowledge ("robbery has the highest arrest rate", high
    confidence) with nothing to support that. Prompt wording is a request, not a boundary, so
    this is enforced in code and does not depend on the model complying: a fixed lead-in
    sentence is put in front of the answer, the confidence is capped at LOW (part of the
    question is, by construction, unanswered), and the gap is recorded as a limitation.
    """
    lead = (
        f"The database part of this question could not be answered ({_NO_RESULT_SHORT[_sql_outcome(r)]}). "
        "What follows draws only on the retrieved documents and contains no database figures. "
    )
    return synthesis.model_copy(
        update={
            "answer": lead + synthesis.answer,
            "confidence": Confidence.LOW,
            "limitations": [*synthesis.limitations, _sql_branch_limitation(r)],
        }
    )


def _sql_branch_limitation(r: SqlExecutionResult) -> str:
    return f"The database part of this question has no result: {_NO_RESULT[_sql_outcome(r)][0]}"


def _no_sql_result_answer(r: SqlExecutionResult) -> SynthesisOutput:
    """Deterministic, truthful answer for a SQL branch that produced no result (no LLM call)."""
    text, confidence = _NO_RESULT[_sql_outcome(r)]
    return SynthesisOutput(
        answer=text,
        citations=[],
        confidence=confidence,
        limitations=["No data was queried or returned; this reports what the system did, not a database result."],
    )


def _run_rag_stage(question: str) -> list[EvidenceChunk]:
    try:
        with SessionLocal() as session:
            retrieved = retrieve(session, question)
    except Exception:  # noqa: BLE001 - same reasoning as the SQL stage: a retrieval
        # failure (DB down, embedding model unavailable) must degrade to "no
        # evidence found" rather than propagate out of run_investigation and skip
        # query_log for the request.
        logger.exception("RAG retrieval failed")
        return []
    return [
        EvidenceChunk(
            document_title=r.document_title,
            document_source=r.document_source,
            content=r.content,
            similarity=r.similarity,
        )
        for r in retrieved
    ]


def _persist_log(
    *,
    request_id: str,
    question: str,
    route: Route,
    sql_result: SqlExecutionResult | None,
    latency_ms: int,
    stage_ms: dict[str, int],
    llm_model: str | None,
    llm_input_tokens: int,
    llm_output_tokens: int,
) -> None:
    with SessionLocal() as session:
        session.add(
            QueryLog(
                request_id=request_id,
                question=question,
                route=route.value,
                generated_sql=sql_result.generated_sql if sql_result else None,
                executed_sql=sql_result.executed_sql if sql_result else None,
                sql_validation_ok=sql_result.validation_ok if sql_result else None,
                sql_repaired=sql_result.repaired if sql_result else None,
                first_attempt_sql=sql_result.first_attempt_sql if sql_result else None,
                first_attempt_error=sql_result.first_attempt_error if sql_result else None,
                sql_rejection_reason=sql_result.rejection_reason if sql_result else None,
                # NULL (not 0) unless the database produced rows, so a rejection or an execution
                # error is distinguishable in the audit log from a query that returned zero rows.
                row_count=sql_result.row_count if sql_result and _sql_outcome(sql_result) == "executed" else None,
                latency_ms=latency_ms,
                intent_latency_ms=stage_ms.get("intent"),
                sql_latency_ms=stage_ms.get("sql"),
                rag_latency_ms=stage_ms.get("rag"),
                synthesis_latency_ms=stage_ms.get("synthesis"),
                llm_provider=get_settings().llm_provider,
                llm_model=llm_model,
                llm_input_tokens=llm_input_tokens or None,
                llm_output_tokens=llm_output_tokens or None,
            )
        )
        session.commit()
