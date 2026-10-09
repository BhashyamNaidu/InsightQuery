from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Route(str, Enum):
    SQL = "sql"
    RAG = "rag"
    HYBRID = "hybrid"
    REJECTED = "rejected"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SqlOutcome = Literal[
    "executed",  # validated and run; rows (possibly zero) are real database results
    "blocked_by_validator",  # rejected by validate_sql(); never executed
    "no_query_generated",  # the model declined to write SQL; nothing validated or run
    "generation_failed",  # the SQL-generation LLM call itself failed
    "execution_failed",  # validated, but PostgreSQL returned an error; no rows exist
]


class SqlExecutionResult(BaseModel):
    # Separates "no result" from "zero rows": only outcome == "executed" means the database
    # produced rows. Optional so existing callers and clients keep working.
    outcome: SqlOutcome | None = None
    generated_sql: str | None = None
    executed_sql: str | None = None
    validation_ok: bool
    rejection_reason: str | None = None
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    repaired: bool = False
    repair_note: str | None = None
    first_attempt_sql: str | None = None  # populated only when a repair happened
    first_attempt_error: str | None = None


class EvidenceChunk(BaseModel):
    document_title: str
    document_source: str
    content: str
    similarity: float


class SynthesisOutput(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    confidence: Confidence
    limitations: list[str] = Field(default_factory=list)


class InvestigateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class InvestigateResponse(BaseModel):
    request_id: str
    question: str
    route: Route
    intent_reasoning: str | None = None
    sql_result: SqlExecutionResult | None = None
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    synthesis: SynthesisOutput | None = None
    latency_ms: int
    stage_latency_ms: dict[str, int] = Field(default_factory=dict)


class SqlQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RagRetrieveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class RagRetrieveResponse(BaseModel):
    question: str
    results: list[EvidenceChunk]
