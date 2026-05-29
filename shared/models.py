from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, Float, Integer, Text, ForeignKey
from sqlalchemy.types import JSON, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SearchConfig(Base):
    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_sub_cb: Mapped[Optional[str]] = mapped_column(Text)
    locality_region_id: Mapped[Optional[int]] = mapped_column(Integer)
    locality_district_id: Mapped[Optional[str]] = mapped_column(Text)
    czk_price_min: Mapped[Optional[int]] = mapped_column(Integer)
    czk_price_max: Mapped[Optional[int]] = mapped_column(Integer)
    usable_area_min: Mapped[Optional[int]] = mapped_column(Integer)
    usable_area_max: Mapped[Optional[int]] = mapped_column(Integer)
    ownership: Mapped[Optional[int]] = mapped_column(Integer)
    no_auction: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    destination_label: Mapped[Optional[str]] = mapped_column(Text)
    destination_lat: Mapped[Optional[float]] = mapped_column(Float)
    destination_lon: Mapped[Optional[float]] = mapped_column(Float)
    travel_mode: Mapped[Optional[str]] = mapped_column(Text)
    scoring_weights: Mapped[Optional[dict]] = mapped_column(JSON)
    alert_thresholds: Mapped[Optional[dict]] = mapped_column(JSON)


class Listing(Base):
    __tablename__ = "listings"

    hash_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_czk: Mapped[Optional[int]] = mapped_column(Integer)
    area_m2: Mapped[Optional[int]] = mapped_column(Integer)
    price_per_m2: Mapped[Optional[float]] = mapped_column(Float)
    locality: Mapped[Optional[str]] = mapped_column(Text)
    locality_district_id: Mapped[Optional[int]] = mapped_column(Integer)
    locality_region_id: Mapped[Optional[int]] = mapped_column(Integer)
    floor: Mapped[Optional[str]] = mapped_column(Text)
    building_type: Mapped[Optional[str]] = mapped_column(Text)
    ownership: Mapped[Optional[str]] = mapped_column(Text)
    condition: Mapped[Optional[str]] = mapped_column(Text)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_new_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    energy_class: Mapped[Optional[str]] = mapped_column(Text)
    has_elevator: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_outdoor_space: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_parking: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_cellar: Mapped[Optional[bool]] = mapped_column(Boolean)
    year_built: Mapped[Optional[int]] = mapped_column(Integer)
    land_area_m2: Mapped[Optional[int]] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    removed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    days_to_sell: Mapped[Optional[int]] = mapped_column(Integer)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON)


class ListingPriceHistory(Base):
    __tablename__ = "listing_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), nullable=False
    )
    price_czk: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_m2: Mapped[Optional[float]] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ListingScore(Base):
    __tablename__ = "listing_scores"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    price_percentile: Mapped[Optional[float]] = mapped_column(Float)
    price_per_m2_percentile: Mapped[Optional[float]] = mapped_column(Float)
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer)
    had_price_drop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_drop_pct: Mapped[Optional[float]] = mapped_column(Float)
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    combined_score: Mapped[Optional[float]] = mapped_column(Float)
    alerted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    condition_score: Mapped[Optional[float]] = mapped_column(Float)
    condition_price_pct: Mapped[Optional[float]] = mapped_column(Float)
    energy_score: Mapped[Optional[float]] = mapped_column(Float)
    floor_elevator_penalty: Mapped[Optional[float]] = mapped_column(Float)
    building_type_score: Mapped[Optional[float]] = mapped_column(Float)
    drop_recency_days: Mapped[Optional[int]] = mapped_column(Integer)
    market_delta_pct: Mapped[Optional[float]] = mapped_column(Float)
    land_price_percentile: Mapped[Optional[float]] = mapped_column(Float)
    combined_area_price_pct: Mapped[Optional[float]] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    listings_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="running", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    progress_total: Mapped[Optional[int]] = mapped_column(Integer)
    progress_done: Mapped[Optional[int]] = mapped_column(Integer)


class ListingSearchConfig(Base):
    __tablename__ = "listing_search_configs"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), primary_key=True
    )


class ListingDistance(Base):
    __tablename__ = "listing_distances"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), primary_key=True
    )
    travel_mode: Mapped[str] = mapped_column(Text, nullable=False)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    locality_district_id: Mapped[Optional[int]] = mapped_column(Integer)
    listing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    median_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    avg_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    p25_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    p75_price_m2: Mapped[Optional[float]] = mapped_column(Float)
