import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median as py_median
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.models import Listing, ListingPriceHistory, ListingScore, MarketSnapshot

UTC = timezone.utc

CONDITION_SCORES: dict[str, float] = {
    "Novostavba": 5.0,
    "Po rekonstrukci": 5.0,
    "Ve výstavbě": 4.0,
    "Velmi dobrý": 4.0,
    "Dobrý": 3.0,
    "Před rekonstrukcí": 2.0,
    "Špatný": 1.0,
    "Demolice": 0.0,
}

CONDITION_BUCKETS: dict[str, str] = {
    "Novostavba": "excellent",
    "Po rekonstrukci": "excellent",
    "Ve výstavbě": "good",
    "Velmi dobrý": "good",
    "Dobrý": "good",
    "Před rekonstrukcí": "poor",
    "Špatný": "poor",
    "Demolice": "poor",
}

ENERGY_SCORES: dict[str, float] = {
    "A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0, "F": 0.5, "G": 0.0,
}

BUILDING_TYPE_SCORES: dict[str, float] = {
    "Cihlová": 5.0, "Kamenná": 5.0,
    "Smíšená": 3.0,
    "Panelová": 2.0, "Dřevostavba": 2.0, "Skelet": 2.0,
}


def _parse_floor_number(floor_str: Optional[str]) -> Optional[int]:
    if not floor_str:
        return None
    if "přízemí" in floor_str.lower():
        return 0
    match = re.search(r"(\d+)\.", floor_str)
    return int(match.group(1)) if match else None


def _floor_elevator_penalty(floor_str: Optional[str], has_elevator: Optional[bool]) -> float:
    if has_elevator:
        return 0.0
    floor_num = _parse_floor_number(floor_str)
    if floor_num is None or floor_num <= 3:
        return 0.0
    return max(-20.0, -5.0 * (floor_num - 3))


def _drop_recency_days(db: Session, hash_id: int, now: datetime) -> Optional[int]:
    history = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.desc())
        .all()
    )
    for i in range(len(history) - 1):
        if history[i].price_czk < history[i + 1].price_czk:
            drop_at = history[i].recorded_at.replace(tzinfo=None)
            return (now.replace(tzinfo=None) - drop_at).days
    return None


def _first_price(db: Session, hash_id: int) -> Optional[int]:
    row = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.asc())
        .first()
    )
    return row.price_czk if row else None


def compute_signals(db: Session) -> None:
    now = datetime.now(UTC)

    percentile_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY price_czk
            ) * 100 AS price_percentile,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY price_per_m2
            ) * 100 AS price_per_m2_percentile
        FROM listings
        WHERE is_active = TRUE
    """)
    rows = db.execute(percentile_sql).fetchall()
    percentiles = {r[0]: (r[1], r[2]) for r in rows}

    condition_pct_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY
                    CASE condition
                        WHEN 'Novostavba'       THEN 'excellent'
                        WHEN 'Po rekonstrukci'  THEN 'excellent'
                        WHEN 'Ve výstavbě'      THEN 'good'
                        WHEN 'Velmi dobrý'      THEN 'good'
                        WHEN 'Dobrý'            THEN 'good'
                        WHEN 'Před rekonstrukcí' THEN 'poor'
                        WHEN 'Špatný'           THEN 'poor'
                        WHEN 'Demolice'         THEN 'poor'
                        ELSE NULL
                    END,
                    category_main_cb,
                    category_type_cb,
                    locality_district_id
                ORDER BY price_per_m2
            ) * 100 AS condition_price_pct
        FROM listings
        WHERE is_active = TRUE AND condition IS NOT NULL AND price_per_m2 IS NOT NULL
    """)
    condition_pcts = {r[0]: r[1] for r in db.execute(condition_pct_sql).fetchall()}

    # Historical market medians (9-month window)
    nine_months_ago = now - timedelta(days=270)
    snap_rows = (
        db.query(
            MarketSnapshot.category_main_cb,
            MarketSnapshot.category_type_cb,
            MarketSnapshot.locality_district_id,
            MarketSnapshot.median_price_m2,
        )
        .filter(MarketSnapshot.snapshot_at >= nine_months_ago)
        .all()
    )
    snap_buckets: dict[tuple, list[float]] = defaultdict(list)
    for r in snap_rows:
        if r.median_price_m2 is not None:
            snap_buckets[(r.category_main_cb, r.category_type_cb, r.locality_district_id)].append(r.median_price_m2)
    historical_medians = {k: py_median(v) for k, v in snap_buckets.items()}

    # Land percentiles
    land_pct_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY CAST(price_czk AS REAL) / NULLIF(land_area_m2, 0)
            ) * 100 AS land_price_percentile,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY CAST(price_czk AS REAL) / NULLIF(area_m2 + 0.15 * land_area_m2, 0)
            ) * 100 AS combined_area_price_pct
        FROM listings
        WHERE is_active = TRUE AND land_area_m2 IS NOT NULL AND land_area_m2 > 0
    """)
    land_pcts = {r[0]: (r[1], r[2]) for r in db.execute(land_pct_sql).fetchall()}

    active_listings = db.query(Listing).filter_by(is_active=True).all()

    for listing in active_listings:
        first_price = _first_price(db, listing.hash_id)
        had_price_drop = first_price is not None and first_price > listing.price_czk
        price_drop_pct: Optional[float] = None
        if had_price_drop and first_price:
            price_drop_pct = (first_price - listing.price_czk) / first_price * 100

        first_seen = listing.first_seen_at.replace(tzinfo=None)
        days_on_market = (now.replace(tzinfo=None) - first_seen).days

        price_pct, ppm2_pct = percentiles.get(listing.hash_id, (None, None))
        cond_score = CONDITION_SCORES.get(listing.condition) if listing.condition else None
        cond_pct = condition_pcts.get(listing.hash_id)

        existing = db.query(ListingScore).filter_by(hash_id=listing.hash_id).first()
        if existing is None:
            score_obj = ListingScore(
                hash_id=listing.hash_id,
                is_hot=False,
                computed_at=now,
            )
            db.add(score_obj)
        else:
            score_obj = existing
            score_obj.computed_at = now

        score_obj.price_percentile = price_pct
        score_obj.price_per_m2_percentile = ppm2_pct
        score_obj.days_on_market = days_on_market
        score_obj.had_price_drop = had_price_drop
        score_obj.price_drop_pct = price_drop_pct
        score_obj.condition_score = cond_score
        score_obj.condition_price_pct = cond_pct
        score_obj.energy_score = ENERGY_SCORES.get(listing.energy_class) if listing.energy_class else None
        score_obj.floor_elevator_penalty = _floor_elevator_penalty(listing.floor, listing.has_elevator)
        score_obj.building_type_score = BUILDING_TYPE_SCORES.get(listing.building_type) if listing.building_type else None
        score_obj.drop_recency_days = _drop_recency_days(db, listing.hash_id, now)

        bucket_key = (listing.category_main_cb, listing.category_type_cb, listing.locality_district_id)
        hist_median = historical_medians.get(bucket_key)
        if hist_median and listing.price_per_m2:
            score_obj.market_delta_pct = (listing.price_per_m2 - hist_median) / hist_median * 100
        else:
            score_obj.market_delta_pct = None

        land_pct_val, combined_pct_val = land_pcts.get(listing.hash_id, (None, None))
        score_obj.land_price_percentile = land_pct_val
        score_obj.combined_area_price_pct = combined_pct_val

    db.commit()
