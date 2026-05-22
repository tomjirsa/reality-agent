from datetime import datetime, timezone
import pytest

UTC = timezone.utc


def test_create_search_config(db):
    from shared.models import SearchConfig
    config = SearchConfig(
        name="Praha byty prodej",
        category_main_cb=1,
        category_type_cb=1,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.id is not None
    assert config.active is True
    assert config.no_auction is True


def test_create_listing(db):
    from shared.models import Listing
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000001,
        name="Byt 3+kk 80m²",
        price_czk=5_900_000,
        area_m2=80,
        price_per_m2=73_750.0,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    assert listing.hash_id == 9999000001
    assert listing.is_new_flag is False


def test_create_price_history(db):
    from shared.models import Listing, ListingPriceHistory
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000002,
        name="Byt 2+kk",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    history = ListingPriceHistory(
        hash_id=9999000002,
        price_czk=4_200_000,
        price_per_m2=52_500.0,
        recorded_at=now,
    )
    db.add(history)
    db.commit()
    results = db.query(ListingPriceHistory).filter_by(hash_id=9999000002).all()
    assert len(results) == 1
    assert results[0].price_czk == 4_200_000


def test_create_listing_score(db):
    from shared.models import Listing, ListingScore
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9999000003,
        name="Byt 1+kk",
        price_czk=3_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    score = ListingScore(
        hash_id=9999000003,
        price_percentile=15.0,
        price_per_m2_percentile=20.0,
        days_on_market=3,
        had_price_drop=False,
        is_hot=True,
        combined_score=82.5,
        computed_at=now,
    )
    db.add(score)
    db.commit()
    result = db.query(ListingScore).filter_by(hash_id=9999000003).one()
    assert result.is_hot is True
    assert result.combined_score == pytest.approx(82.5)


def test_create_scrape_run(db):
    from shared.models import SearchConfig, ScrapeRun
    now = datetime.now(UTC)
    config = SearchConfig(
        name="Test Config",
        category_main_cb=1,
        category_type_cb=1,
        created_at=now,
    )
    db.add(config)
    db.flush()
    run = ScrapeRun(
        search_config_id=config.id,
        started_at=now,
        listings_found=10,
        listings_new=2,
        listings_updated=1,
        listings_removed=0,
        status="success",
    )
    db.add(run)
    db.commit()
    result = db.query(ScrapeRun).filter_by(search_config_id=config.id).one()
    assert result.status == "success"
    assert result.listings_found == 10


def test_listing_search_config_roundtrip(db):
    from shared.models import SearchConfig, Listing, ListingSearchConfig
    config = SearchConfig(
        name="Test Config",
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=99001,
        name="Test Listing",
        price_czk=3_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    link = ListingSearchConfig(hash_id=99001, search_config_id=config.id)
    db.add(link)
    db.commit()
    fetched = db.query(ListingSearchConfig).filter_by(hash_id=99001, search_config_id=config.id).one()
    assert fetched.hash_id == 99001
    assert fetched.search_config_id == config.id


def test_listing_distance_roundtrip(db):
    from shared.models import SearchConfig, Listing, ListingDistance
    config = SearchConfig(
        name="Test Config 2",
        category_main_cb=1,
        category_type_cb=1,
        destination_lat=50.08,
        destination_lon=14.42,
        travel_mode="car",
        active=True,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=99002,
        name="Test Listing 2",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    dist = ListingDistance(
        hash_id=99002,
        search_config_id=config.id,
        travel_mode="car",
        distance_m=1500,
        duration_s=300,
        computed_at=now,
    )
    db.add(dist)
    db.commit()
    fetched = db.query(ListingDistance).filter_by(hash_id=99002, search_config_id=config.id).one()
    assert fetched.distance_m == 1500
    assert fetched.duration_s == 300
    assert fetched.travel_mode == "car"
    assert config.destination_lat == 50.08
    assert config.travel_mode == "car"
