"""initial schema: crimes fact table + dimensions + RAG + query_log

Revision ID: 0001
Revises:
Create Date: 2026-09-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "iucr_codes",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("primary_type", sa.String(100), nullable=False),
        sa.Column("secondary_desc", sa.String(200), nullable=False),
        sa.Column("index_crime", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "police_districts",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )

    op.create_table(
        "community_areas",
        sa.Column("code", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )

    op.create_table(
        "crimes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("case_number", sa.String(20), nullable=False, unique=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False),
        sa.Column("block", sa.String(100), nullable=True),
        sa.Column("iucr_code", sa.String(10), sa.ForeignKey("iucr_codes.code"), nullable=True),
        sa.Column("primary_type", sa.String(100), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("location_description", sa.String(100), nullable=True),
        sa.Column("arrest", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("domestic", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("beat", sa.String(10), nullable=True),
        sa.Column(
            "district_code", sa.String(10), sa.ForeignKey("police_districts.code"), nullable=True
        ),
        sa.Column("ward", sa.Integer, nullable=True),
        sa.Column(
            "community_area_code",
            sa.Integer,
            sa.ForeignKey("community_areas.code"),
            nullable=True,
        ),
        sa.Column("fbi_code", sa.String(10), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("year", sa.Integer, nullable=False),
    )
    op.create_index("ix_crimes_occurred_at", "crimes", ["occurred_at"])
    op.create_index("ix_crimes_primary_type", "crimes", ["primary_type"])
    op.create_index(
        "ix_crimes_primary_type_occurred_at", "crimes", ["primary_type", "occurred_at"]
    )
    op.create_index("ix_crimes_district_code", "crimes", ["district_code"])
    op.create_index("ix_crimes_community_area_code", "crimes", ["community_area_code"])
    op.create_index("ix_crimes_arrest", "crimes", ["arrest"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
    )
    # Deliberately no ANN index (IVFFlat/HNSW) here: the corpus is ~15 curated
    # documents (a few hundred chunks at most, see ARCHITECTURE.md's scope
    # boundaries), and IVFFlat specifically is actively counterproductive below
    # roughly a few thousand rows — with `lists` sized for a large corpus, each
    # cluster ends up holding a handful of vectors or fewer, which degrades recall
    # rather than improving query speed on a table small enough for an exact
    # sequential scan to already be sub-millisecond. Revisit if the corpus grows.

    op.create_table(
        "query_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("route", sa.String(20), nullable=False),
        sa.Column("generated_sql", sa.Text, nullable=True),
        sa.Column("sql_validation_ok", sa.Boolean, nullable=True),
        sa.Column("sql_rejection_reason", sa.Text, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_input_tokens", sa.Integer, nullable=True),
        sa.Column("llm_output_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("query_log")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_index("ix_crimes_arrest", table_name="crimes")
    op.drop_index("ix_crimes_community_area_code", table_name="crimes")
    op.drop_index("ix_crimes_district_code", table_name="crimes")
    op.drop_index("ix_crimes_primary_type_occurred_at", table_name="crimes")
    op.drop_index("ix_crimes_primary_type", table_name="crimes")
    op.drop_index("ix_crimes_occurred_at", table_name="crimes")
    op.drop_table("crimes")
    op.drop_table("community_areas")
    op.drop_table("police_districts")
    op.drop_table("iucr_codes")
