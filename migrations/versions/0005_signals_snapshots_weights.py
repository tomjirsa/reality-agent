"""add signal columns, market_snapshots table, scoring weights

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in [
        "condition_score", "condition_price_pct", "energy_score",
        "floor_elevator_penalty", "building_type_score", "market_delta_pct",
        "land_price_percentile", "combined_area_price_pct",
    ]:
        op.add_column("listing_scores", sa.Column(col, sa.Float(), nullable=True))
    op.add_column("listing_scores", sa.Column("drop_recency_days", sa.Integer(), nullable=True))

    op.add_column("search_configs", sa.Column("scoring_weights", sa.JSON(), nullable=True))
    op.add_column("search_configs", sa.Column("alert_thresholds", sa.JSON(), nullable=True))

    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("listing_count", sa.Integer(), nullable=False),
        sa.Column("median_price_m2", sa.Float(), nullable=True),
        sa.Column("avg_price_m2", sa.Float(), nullable=True),
        sa.Column("p25_price_m2", sa.Float(), nullable=True),
        sa.Column("p75_price_m2", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("market_snapshots")
    op.drop_column("search_configs", "alert_thresholds")
    op.drop_column("search_configs", "scoring_weights")
    for col in [
        "drop_recency_days", "combined_area_price_pct", "land_price_percentile",
        "market_delta_pct", "building_type_score", "floor_elevator_penalty",
        "energy_score", "condition_price_pct", "condition_score",
    ]:
        op.drop_column("listing_scores", col)
