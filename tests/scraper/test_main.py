import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from shared.models import SearchConfig, Listing, ListingPriceHistory, ScrapeRun, ListingSearchConfig
from scraper.main import upsert_listings, detect_removals, create_scrape_run, finish_scrape_run, run_pipeline, _scrape_lock, cleanup_stale_runs

UTC = timezone.utc


def make_search_config(db):
    config = SearchConfig(
        name="Test Praha",
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    return config


def make_listing_detail(hash_id=1001, price=5_000_000):
    return {
        "hash_id": hash_id,
        "name": f"Byt {hash_id}",
        "price_czk": price,
        "area_m2": 80,
        "price_per_m2": price / 80,
        "locality": "Praha 2",
        "locality_district_id": 5007,
        "locality_region_id": 10,
        "floor": "2. podlaží",
        "building_type": "Cihlová",
        "condition": "Dobrý",
        "ownership": "Osobní",
        "is_new_flag": False,
        "raw_json": {},
    }


def test_upsert_new_listing_inserts(db):
    config = make_search_config(db)
    details = [make_listing_detail(hash_id=2001)]
    stats = upsert_listings(db, config, details)
    listing = db.query(Listing).filter_by(hash_id=2001).one()
    assert listing.price_czk == 5_000_000
    assert listing.is_active is True
    assert stats["new"] == 1
    assert stats["updated"] == 0


def test_upsert_same_price_does_not_create_history(db):
    config = make_search_config(db)
    details = [make_listing_detail(hash_id=2002)]
    upsert_listings(db, config, details)
    upsert_listings(db, config, details)
    history = db.query(ListingPriceHistory).filter_by(hash_id=2002).all()
    assert len(history) == 0


def test_upsert_price_change_creates_history(db):
    config = make_search_config(db)
    details_v1 = [make_listing_detail(hash_id=2003, price=5_000_000)]
    details_v2 = [make_listing_detail(hash_id=2003, price=4_500_000)]
    upsert_listings(db, config, details_v1)
    stats = upsert_listings(db, config, details_v2)
    listing = db.query(Listing).filter_by(hash_id=2003).one()
    assert listing.price_czk == 4_500_000
    history = db.query(ListingPriceHistory).filter_by(hash_id=2003).all()
    assert len(history) == 1
    assert history[0].price_czk == 5_000_000
    assert stats["updated"] == 1


def test_detect_removals_marks_missing_listings_inactive(db):
    config = SearchConfig(
        name="Removal Test Config",
        category_main_cb=9,
        category_type_cb=9,
        locality_district_id=9999,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=3001,
        name="Old listing",
        price_czk=4_000_000,
        category_main_cb=9,
        category_type_cb=9,
        locality_district_id=9999,
        is_active=True,
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(days=1),
    )
    db.add(listing)
    db.commit()

    count = detect_removals(db, config, current_hash_ids=set())
    db.refresh(listing)
    assert listing.is_active is False
    assert listing.removed_at is not None
    assert listing.days_to_sell == 10
    assert count == 1


def test_detect_removals_ignores_present_listings(db):
    config = SearchConfig(
        name="Ignore Test Config",
        category_main_cb=8,
        category_type_cb=8,
        locality_district_id=8888,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=3002,
        name="Active listing",
        price_czk=4_000_000,
        category_main_cb=8,
        category_type_cb=8,
        locality_district_id=8888,
        is_active=True,
        first_seen_at=now - timedelta(days=5),
        last_seen_at=now,
    )
    db.add(listing)
    db.commit()
    count = detect_removals(db, config, current_hash_ids={3002})
    db.refresh(listing)
    assert listing.is_active is True
    assert count == 0


def test_create_and_finish_scrape_run(db):
    config = make_search_config(db)
    run = create_scrape_run(db, config)
    assert run.status == "running"
    assert run.id is not None

    finish_scrape_run(db, run, listings_found=10, listings_new=2, listings_updated=1, listings_removed=0)
    db.refresh(run)
    assert run.status == "success"
    assert run.listings_found == 10
    assert run.finished_at is not None


def test_upsert_records_listing_search_config_link(db):
    config = make_search_config(db)
    details = [make_listing_detail(hash_id=4001)]
    upsert_listings(db, config, details)
    link = db.query(ListingSearchConfig).filter_by(
        hash_id=4001, search_config_id=config.id
    ).first()
    assert link is not None


def test_upsert_does_not_duplicate_link_on_second_call(db):
    config = make_search_config(db)
    details = [make_listing_detail(hash_id=4002)]
    upsert_listings(db, config, details)
    upsert_listings(db, config, details)
    links = db.query(ListingSearchConfig).filter_by(
        hash_id=4002, search_config_id=config.id
    ).all()
    assert len(links) == 1


def test_run_pipeline_skips_if_already_running():
    with patch("scraper.main.SessionLocal") as mock_db:
        _scrape_lock.acquire()
        try:
            run_pipeline()
        finally:
            _scrape_lock.release()
        mock_db.assert_not_called()


def test_cleanup_stale_runs_marks_running_as_aborted(db):
    config = make_search_config(db)
    stale = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC) - timedelta(hours=2),
        status="running",
    )
    db.add(stale)
    db.commit()

    cleanup_stale_runs(db)
    db.refresh(stale)

    assert stale.status == "aborted"
    assert stale.finished_at is not None


def test_cleanup_stale_runs_leaves_finished_runs_alone(db):
    config = make_search_config(db)
    now = datetime.now(UTC)
    finished = ScrapeRun(
        search_config_id=config.id,
        started_at=now - timedelta(hours=1),
        finished_at=now,
        status="success",
    )
    db.add(finished)
    db.commit()

    cleanup_stale_runs(db)
    db.refresh(finished)

    assert finished.status == "success"
