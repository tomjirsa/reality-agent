"""add listing attribute columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("energy_class", sa.Text(), nullable=True))
    op.add_column("listings", sa.Column("has_elevator", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_outdoor_space", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_parking", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_cellar", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("year_built", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("land_area_m2", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ["land_area_m2", "year_built", "has_cellar", "has_parking",
                "has_outdoor_space", "has_elevator", "energy_class"]:
        op.drop_column("listings", col)
