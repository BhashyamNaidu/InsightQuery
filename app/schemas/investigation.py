from enum import Enum

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


class SqlExecutionResult(BaseModel):
    generated_sql: str | None = None
    executed_sql: str | None = None
    validation_ok: bool
    rejection_reason: str | None = None
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0


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


class SqlQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RagRetrieveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class RagRetrieveResponse(BaseModel):
    question: str
    results: list[EvidenceChunk]
