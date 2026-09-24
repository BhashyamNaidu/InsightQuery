"""add stage-level latency and llm_provider to query_log

Needed for real per-stage latency measurement (intent/SQL/RAG/synthesis) and to
distinguish which LLM provider (anthropic/ollama) served a given request now that
the provider is configurable — see app/llm/providers/.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_log", sa.Column("intent_latency_ms", sa.Integer(), nullable=True))
    op.add_column("query_log", sa.Column("sql_latency_ms", sa.Integer(), nullable=True))
    op.add_column("query_log", sa.Column("rag_latency_ms", sa.Integer(), nullable=True))
    op.add_column("query_log", sa.Column("synthesis_latency_ms", sa.Integer(), nullable=True))
    op.add_column("query_log", sa.Column("llm_provider", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("query_log", "llm_provider")
    op.drop_column("query_log", "synthesis_latency_ms")
    op.drop_column("query_log", "rag_latency_ms")
    op.drop_column("query_log", "sql_latency_ms")
    op.drop_column("query_log", "intent_latency_ms")
