import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QueryLog(Base):
    __tablename__ = "query_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(String(20), nullable=False)  # sql | rag | hybrid | rejected

    generated_sql: Mapped[str] = mapped_column(Text, nullable=True)
    sql_validation_ok: Mapped[bool] = mapped_column(Boolean, nullable=True)
    sql_rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=True)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    llm_model: Mapped[str] = mapped_column(String(100), nullable=True)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
