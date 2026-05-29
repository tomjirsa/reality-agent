"""add progress columns to scrape_runs

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("progress_total", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("progress_done", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_runs", "progress_done")
    op.drop_column("scrape_runs", "progress_total")
