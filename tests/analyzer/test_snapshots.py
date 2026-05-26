import pytest
from datetime import datetime, timezone, timedelta
from shared.models import Listing, MarketSnapshot
from analyzer.snapshots import create_market_snapshot

UTC = timezone.utc


def add_listing(db, hash_id, price_per_m2, cat_main=1, cat_type=1, district=5007):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"L{hash_id}",
        price_czk=int(price_per_m2 * 80),
        area_m2=80,
        price_per_m2=price_per_m2,
        category_main_cb=cat_main,
        category_type_cb=cat_type,
        locality_district_id=district,
        is_active=True,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()


def test_create_snapshot_writes_one_row_per_bucket(db):
    add_listing(db, 9001, 60_000.0)
    add_listing(db, 9002, 70_000.0)
    add_listing(db, 9003, 80_000.0)
    db.commit()
    count = create_market_snapshot(db)
    assert count == 1
    snap = db.query(MarketSnapshot).filter_by(
        category_main_cb=1, category_type_cb=1, locality_district_id=5007
    ).one()
    assert snap.listing_count == 3
    assert snap.median_price_m2 == pytest.approx(70_000.0)


def test_snapshot_ignores_inactive_listings(db):
    now = datetime.now(UTC)
    add_listing(db, 9011, 60_000.0)
    inactive = Listing(
        hash_id=9012, name="L9012",
        price_czk=1_000_000, area_m2=80, price_per_m2=12_500.0,
        category_main_cb=1, category_type_cb=1, locality_district_id=5007,
        is_active=False,
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(days=2),
    )
    db.add(inactive)
    db.commit()
    create_market_snapshot(db)
    snap = db.query(MarketSnapshot).filter_by(
        category_main_cb=1, category_type_cb=1, locality_district_id=5007
    ).one()
    assert snap.listing_count == 1


def test_snapshot_creates_separate_rows_per_bucket(db):
    add_listing(db, 9021, 60_000.0, cat_main=1, cat_type=1, district=5007)
    add_listing(db, 9022, 70_000.0, cat_main=1, cat_type=2, district=5007)
    add_listing(db, 9023, 50_000.0, cat_main=1, cat_type=1, district=6202)
    db.commit()
    count = create_market_snapshot(db)
    assert count == 3
