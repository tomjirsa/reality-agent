from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.models import Listing, ListingPriceHistory, ListingScore

UTC = timezone.utc


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

        existing = db.query(ListingScore).filter_by(hash_id=listing.hash_id).first()
        if existing is None:
            score = ListingScore(
                hash_id=listing.hash_id,
                price_percentile=price_pct,
                price_per_m2_percentile=ppm2_pct,
                days_on_market=days_on_market,
                had_price_drop=had_price_drop,
                price_drop_pct=price_drop_pct,
                is_hot=False,
                computed_at=now,
            )
            db.add(score)
        else:
            existing.price_percentile = price_pct
            existing.price_per_m2_percentile = ppm2_pct
            existing.days_on_market = days_on_market
            existing.had_price_drop = had_price_drop
            existing.price_drop_pct = price_drop_pct
            existing.computed_at = now

    db.commit()
