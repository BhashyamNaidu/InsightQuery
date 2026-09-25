from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.client import LlmError
from app.models import QueryLog
from app.nlsql.executor import execute_readonly
from app.nlsql.generator import generate_sql
from app.rag.retrieval import retrieve
from app.schemas.common import HealthResponse
from app.schemas.investigation import (
    EvidenceChunk,
    InvestigateRequest,
    InvestigateResponse,
    RagRetrieveRequest,
    RagRetrieveResponse,
    SqlExecutionResult,
    SqlQueryRequest,
)
from app.services.investigation import run_investigation

logger = logging.getLogger(__name__)
router = APIRouter()

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "ok"
    vector_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_status = f"error: {exc}"
    try:
        db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    except Exception as exc:  # noqa: BLE001
        vector_status = f"error: {exc}"

    overall = "ok" if db_status == "ok" and vector_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, vector_store=vector_status)


@router.post("/investigate", response_model=InvestigateResponse)
def investigate(payload: InvestigateRequest) -> InvestigateResponse:
    try:
        return run_investigation(payload.question)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Investigation pipeline failed")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "investigation_failed", "message": str(exc)},
        ) from exc


@router.post("/sql/query", response_model=SqlExecutionResult)
def sql_query(payload: SqlQueryRequest) -> SqlExecutionResult:
    """Run the NL-to-SQL pipeline standalone — useful for demonstrating SQL
    generation + validation independent of the full investigation flow."""
    try:
        gen = generate_sql(payload.question)
    except LlmError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error_code": "llm_call_failed", "message": str(exc)},
        ) from exc
    if not gen.validation.ok:
        return SqlExecutionResult(
            generated_sql=gen.raw_sql,
            validation_ok=False,
            rejection_reason=gen.validation.reason,
        )
    try:
        rows = execute_readonly(gen.validation.sql)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error_code": "sql_execution_failed", "message": str(exc)},
        ) from exc
    return SqlExecutionResult(
        generated_sql=gen.raw_sql,
        executed_sql=gen.validation.sql,
        validation_ok=True,
        rows=rows,
        row_count=len(rows),
    )


@router.post("/rag/retrieve", response_model=RagRetrieveResponse)
def rag_retrieve(payload: RagRetrieveRequest, db: Session = Depends(get_db)) -> RagRetrieveResponse:
    results = retrieve(db, payload.question, top_k=payload.top_k)
    return RagRetrieveResponse(
        question=payload.question,
        results=[
            EvidenceChunk(
                document_title=r.document_title,
                document_source=r.document_source,
                content=r.content,
                similarity=r.similarity,
            )
            for r in results
        ],
    )


@router.get("/evidence/{query_log_id}")
def get_evidence(query_log_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        log_uuid = uuid.UUID(query_log_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "invalid_id", "message": "query_log_id must be a UUID."},
        ) from exc

    log = db.get(QueryLog, log_uuid)
    if log is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "not_found", "message": "No query log found for that id."},
        )
    return {
        "id": str(log.id),
        "request_id": log.request_id,
        "question": log.question,
        "route": log.route,
        "generated_sql": log.generated_sql,
        "sql_validation_ok": log.sql_validation_ok,
        "sql_rejection_reason": log.sql_rejection_reason,
        "row_count": log.row_count,
        "latency_ms": log.latency_ms,
        "stage_latency_ms": {
            "intent": log.intent_latency_ms,
            "sql": log.sql_latency_ms,
            "rag": log.rag_latency_ms,
            "synthesis": log.synthesis_latency_ms,
        },
        "llm_provider": log.llm_provider,
        "llm_model": log.llm_model,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("/investigations")
def list_investigations(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Recent investigation history, most recent first — backs the dashboard's
    History page. Returns summaries only (no full SQL result rows) since this is
    a listing view; fetch /evidence/{id} for a single request's full trace."""
    logs = db.query(QueryLog).order_by(desc(QueryLog.created_at)).limit(limit).all()
    return {
        "results": [
            {
                "id": str(log.id),
                "question": log.question,
                "route": log.route,
                "sql_validation_ok": log.sql_validation_ok,
                "row_count": log.row_count,
                "latency_ms": log.latency_ms,
                "llm_provider": log.llm_provider,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.get("/evaluations")
def get_evaluations() -> dict:
    """Serves the saved evaluation reports (scripts/evaluate.py output) for the
    dashboard's Metrics page. Returns null for any report that hasn't been run
    yet — the dashboard shows that honestly rather than a fabricated number."""

    def _load(filename: str) -> dict | None:
        path = DOCS_DIR / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    return {
        "summary": _load("evaluation_results.json"),
        "rag": _load("rag_eval_results.json"),
        "intent": _load("intent_eval_results.json"),
        "nl2sql": _load("nl2sql_eval_results.json"),
        "e2e": _load("e2e_eval_results.json"),
    }
