"""case_number is not actually unique in the source data

Discovered running real ingestion: 20 of 263,841 rows in the 2023 Chicago
crimes dataset share a case_number with another row (multi-victim incidents
produce one row per victim under the same police case_number). `id` is the
true unique row identifier. Drops the incorrect unique constraint and adds
a plain (non-unique) index, since case_number is still a common lookup key.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("crimes_case_number_key", "crimes", type_="unique")
    op.create_index("ix_crimes_case_number", "crimes", ["case_number"])


def downgrade() -> None:
    op.drop_index("ix_crimes_case_number", table_name="crimes")
    op.create_unique_constraint("crimes_case_number_key", "crimes", ["case_number"])
