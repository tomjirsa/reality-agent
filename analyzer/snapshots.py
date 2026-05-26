from collections import defaultdict
from datetime import datetime, timezone
from statistics import median, quantiles
from typing import Optional

from sqlalchemy.orm import Session

from shared.models import Listing, MarketSnapshot

UTC = timezone.utc


def create_market_snapshot(db: Session) -> int:
    now = datetime.now(UTC)

    rows = (
        db.query(
            Listing.category_main_cb,
            Listing.category_type_cb,
            Listing.locality_district_id,
            Listing.price_per_m2,
        )
        .filter(Listing.is_active == True, Listing.price_per_m2 != None)
        .all()
    )

    buckets: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        key = (row.category_main_cb, row.category_type_cb, row.locality_district_id)
        buckets[key].append(row.price_per_m2)

    count = 0
    for (cat_main, cat_type, district_id), prices in buckets.items():
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        med = median(prices_sorted)
        avg = sum(prices_sorted) / n
        if n >= 4:
            qs = quantiles(prices_sorted, n=4)
            p25, p75 = qs[0], qs[2]
        else:
            p25 = p75 = med

        db.add(MarketSnapshot(
            snapshot_at=now,
            category_main_cb=cat_main,
            category_type_cb=cat_type,
            locality_district_id=district_id,
            listing_count=n,
            median_price_m2=med,
            avg_price_m2=avg,
            p25_price_m2=p25,
            p75_price_m2=p75,
        ))
        count += 1

    db.commit()
    return count
