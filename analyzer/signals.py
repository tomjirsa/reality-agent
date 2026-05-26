from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.models import Listing, ListingPriceHistory, ListingScore

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

    db.commit()
