"""multi district support

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "search_configs", "locality_district_id",
        existing_type=sa.Integer(), type_=sa.Text(),
        postgresql_using="locality_district_id::text",
    )


def downgrade() -> None:
    op.alter_column(
        "search_configs", "locality_district_id",
        existing_type=sa.Text(), type_=sa.Integer(),
        postgresql_using="locality_district_id::integer",
    )
