"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("category_sub_cb", sa.Text(), nullable=True),
        sa.Column("locality_region_id", sa.Integer(), nullable=True),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("czk_price_min", sa.Integer(), nullable=True),
        sa.Column("czk_price_max", sa.Integer(), nullable=True),
        sa.Column("usable_area_min", sa.Integer(), nullable=True),
        sa.Column("usable_area_max", sa.Integer(), nullable=True),
        sa.Column("ownership", sa.Integer(), nullable=True),
        sa.Column("no_auction", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "listings",
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("price_czk", sa.Integer(), nullable=True),
        sa.Column("area_m2", sa.Integer(), nullable=True),
        sa.Column("price_per_m2", sa.Float(), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("locality_region_id", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Text(), nullable=True),
        sa.Column("building_type", sa.Text(), nullable=True),
        sa.Column("ownership", sa.Text(), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_new_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("removed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("days_to_sell", sa.Integer(), nullable=True),
        sa.Column("raw_json", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("hash_id"),
    )
    op.create_index("ix_listings_is_active", "listings", ["is_active"])
    op.create_index(
        "ix_listings_peer_group",
        "listings",
        ["category_main_cb", "category_type_cb", "locality_district_id"],
    )
    op.create_table(
        "listing_price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("price_czk", sa.Integer(), nullable=False),
        sa.Column("price_per_m2", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hash_id"], ["listings.hash_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "listing_scores",
        sa.Column("hash_id", sa.BigInteger(), nullable=False),
        sa.Column("price_percentile", sa.Float(), nullable=True),
        sa.Column("price_per_m2_percentile", sa.Float(), nullable=True),
        sa.Column("days_on_market", sa.Integer(), nullable=True),
        sa.Column("had_price_drop", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("price_drop_pct", sa.Float(), nullable=True),
        sa.Column("is_hot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("combined_score", sa.Float(), nullable=True),
        sa.Column("alerted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hash_id"], ["listings.hash_id"]),
        sa.PrimaryKeyConstraint("hash_id"),
    )
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_config_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("listings_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("listings_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["search_config_id"], ["search_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("listing_scores")
    op.drop_table("listing_price_history")
    op.drop_index("ix_listings_peer_group", table_name="listings")
    op.drop_index("ix_listings_is_active", table_name="listings")
    op.drop_table("listings")
    op.drop_table("search_configs")
