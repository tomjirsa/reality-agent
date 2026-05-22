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


def test_new_model_tablenames():
    from shared.models import ListingSearchConfig, ListingDistance
    assert ListingSearchConfig.__tablename__ == "listing_search_configs"
    assert ListingDistance.__tablename__ == "listing_distances"


def test_search_config_has_destination_columns():
    from shared.models import SearchConfig
    cols = {c.key for c in SearchConfig.__table__.columns}
    assert "destination_label" in cols
    assert "destination_lat" in cols
    assert "destination_lon" in cols
    assert "travel_mode" in cols
