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

from app.llm.client import LlmError
from app.llm.synthesis import synthesize
from app.models import QueryLog
from app.db.session import SessionLocal
from app.nlsql.executor import execute_readonly
from app.nlsql.generator import generate_sql
from app.rag.retrieval import retrieve
from app.schemas.investigation import (
    EvidenceChunk,
    InvestigateResponse,
    Route,
    SqlExecutionResult,
)
from app.services.intent import classify_intent

logger = logging.getLogger(__name__)


def run_investigation(question: str) -> InvestigateResponse:
    start = time.perf_counter()
    request_id = str(uuid.uuid4())

    intent = classify_intent(question)
    route = intent.route

    sql_result: SqlExecutionResult | None = None
    evidence: list[EvidenceChunk] = []
    llm_model: str | None = None
    llm_input_tokens = 0
    llm_output_tokens = 0

    if route in (Route.SQL, Route.HYBRID):
        sql_result, tokens = _run_sql_stage(question)
        llm_model = tokens[0] or llm_model
        llm_input_tokens += tokens[1]
        llm_output_tokens += tokens[2]

    if route in (Route.RAG, Route.HYBRID):
        evidence = _run_rag_stage(question)

    synthesis = None
    try:
        synthesis = synthesize(
            question=question,
            sql=sql_result.executed_sql if sql_result else None,
            sql_rows=sql_result.rows if sql_result else None,
            evidence_chunks=[e.model_dump() for e in evidence],
        )
    except LlmError:
        logger.exception("Synthesis LLM call failed for request %s", request_id)

    latency_ms = int((time.perf_counter() - start) * 1000)

    _persist_log(
        request_id=request_id,
        question=question,
        route=route,
        sql_result=sql_result,
        latency_ms=latency_ms,
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
    )


def _run_sql_stage(question: str) -> tuple[SqlExecutionResult, tuple[str | None, int, int]]:
    gen = generate_sql(question)
    tokens = (gen.llm_model, gen.input_tokens, gen.output_tokens)

    if not gen.validation.ok:
        return (
            SqlExecutionResult(
                generated_sql=gen.raw_sql,
                validation_ok=False,
                rejection_reason=gen.validation.reason,
            ),
            tokens,
        )

    try:
        rows = execute_readonly(gen.validation.sql)
        return (
            SqlExecutionResult(
                generated_sql=gen.raw_sql,
                executed_sql=gen.validation.sql,
                validation_ok=True,
                rows=rows,
                row_count=len(rows),
            ),
            tokens,
        )
    except Exception as exc:  # noqa: BLE001 - DB failure must degrade, not crash the pipeline
        logger.exception("SQL execution failed")
        return (
            SqlExecutionResult(
                generated_sql=gen.raw_sql,
                executed_sql=gen.validation.sql,
                validation_ok=True,
                rejection_reason=f"Execution error: {exc}",
                rows=[],
                row_count=0,
            ),
            tokens,
        )


def _run_rag_stage(question: str) -> list[EvidenceChunk]:
    with SessionLocal() as session:
        retrieved = retrieve(session, question)
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
                sql_validation_ok=sql_result.validation_ok if sql_result else None,
                sql_rejection_reason=sql_result.rejection_reason if sql_result else None,
                row_count=sql_result.row_count if sql_result else None,
                latency_ms=latency_ms,
                llm_model=llm_model,
                llm_input_tokens=llm_input_tokens or None,
                llm_output_tokens=llm_output_tokens or None,
            )
        )
        session.commit()
