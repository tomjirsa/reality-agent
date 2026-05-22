"""travel distance enrichment

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("search_configs", sa.Column("destination_label", sa.Text(), nullable=True))
    op.add_column("search_configs", sa.Column("destination_lat", sa.Float(), nullable=True))
    op.add_column("search_configs", sa.Column("destination_lon", sa.Float(), nullable=True))
    op.add_column("search_configs", sa.Column("travel_mode", sa.Text(), nullable=True))
    op.create_table(
        "listing_search_configs",
        sa.Column("hash_id", sa.BigInteger(), sa.ForeignKey("listings.hash_id"), nullable=False),
        sa.Column("search_config_id", sa.Integer(), sa.ForeignKey("search_configs.id"), nullable=False),
        sa.PrimaryKeyConstraint("hash_id", "search_config_id"),
    )
    op.create_table(
        "listing_distances",
        sa.Column("hash_id", sa.BigInteger(), sa.ForeignKey("listings.hash_id"), nullable=False),
        sa.Column("search_config_id", sa.Integer(), sa.ForeignKey("search_configs.id"), nullable=False),
        sa.Column("travel_mode", sa.Text(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("hash_id", "search_config_id"),
    )


def downgrade() -> None:
    op.drop_table("listing_distances")
    op.drop_table("listing_search_configs")
    op.drop_column("search_configs", "travel_mode")
    op.drop_column("search_configs", "destination_lon")
    op.drop_column("search_configs", "destination_lat")
    op.drop_column("search_configs", "destination_label")
