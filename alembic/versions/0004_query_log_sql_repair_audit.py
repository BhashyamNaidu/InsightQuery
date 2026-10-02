"""audit trail for the bounded SQL-repair step

query_log previously stored only the final generated SQL. With one bounded repair
attempt now possible, the audit trail must show: the exact SQL executed, whether a
repair happened, and the original (failed) SQL and its PostgreSQL error.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_log", sa.Column("executed_sql", sa.Text(), nullable=True))
    op.add_column("query_log", sa.Column("sql_repaired", sa.Boolean(), nullable=True))
    op.add_column("query_log", sa.Column("first_attempt_sql", sa.Text(), nullable=True))
    op.add_column("query_log", sa.Column("first_attempt_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("query_log", "first_attempt_error")
    op.drop_column("query_log", "first_attempt_sql")
    op.drop_column("query_log", "sql_repaired")
    op.drop_column("query_log", "executed_sql")
