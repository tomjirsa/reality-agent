"""add estate_area_min/max to search_configs

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("search_configs", sa.Column("estate_area_min", sa.Integer(), nullable=True))
    op.add_column("search_configs", sa.Column("estate_area_max", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_configs", "estate_area_max")
    op.drop_column("search_configs", "estate_area_min")
