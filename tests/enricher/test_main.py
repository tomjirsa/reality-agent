import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.models import (
    Base, SearchConfig, Listing, ListingSearchConfig, ListingDistance
)
from enricher.main import enrich_all_configs, _extract_gps

UTC = timezone.utc

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}
)
Session = sessionmaker(bind=engine)


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = Session()
    yield session
    session.rollback()
    session.close()


def _make_config(db, *, name="Test", dest_lat=50.08, dest_lon=14.42, mode="car"):
    config = SearchConfig(
        name=name,
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        destination_lat=dest_lat,
        destination_lon=dest_lon,
        travel_mode=mode,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    return config


def _make_listing(db, hash_id, *, lat=50.07, lon=14.43):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        raw_json={"map": {"lat": lat, "lon": lon}},
    )
    db.add(listing)
    db.flush()
    return listing


def _link(db, hash_id, config_id):
    db.add(ListingSearchConfig(hash_id=hash_id, search_config_id=config_id))
    db.flush()


def test_extract_gps_returns_lat_lon():
    raw = {"map": {"lat": 50.08, "lon": 14.42}}
    assert _extract_gps(raw) == (50.08, 14.42)


def test_extract_gps_returns_none_for_missing_map():
    assert _extract_gps({}) is None
    assert _extract_gps(None) is None


def test_extract_gps_returns_none_for_missing_coords():
    assert _extract_gps({"map": {"lat": 50.08}}) is None


def test_enrich_all_configs_creates_distance_row(db):
    config = _make_config(db, name="Enrich1")
    _make_listing(db, hash_id=9001)
    _link(db, 9001, config.id)
    db.commit()

    with patch("enricher.main.route", return_value={"distance_m": 2000, "duration_s": 400}):
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")

    dist = db.query(ListingDistance).filter_by(hash_id=9001, search_config_id=config.id).first()
    assert dist is not None
    assert dist.distance_m == 2000
    assert dist.duration_s == 400
    assert dist.travel_mode == "car"


def test_enrich_all_configs_skips_already_enriched(db):
    config = _make_config(db, name="Enrich2")
    _make_listing(db, hash_id=9002)
    _link(db, 9002, config.id)
    db.add(ListingDistance(
        hash_id=9002,
        search_config_id=config.id,
        travel_mode="car",
        distance_m=1000,
        duration_s=200,
        computed_at=datetime.now(UTC),
    ))
    db.commit()

    with patch("enricher.main.route") as mock_route:
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")
    mock_route.assert_not_called()


def test_enrich_all_configs_skips_listing_without_gps(db):
    config = _make_config(db, name="Enrich3")
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=9003,
        name="No GPS",
        price_czk=3_000_000,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now,
        last_seen_at=now,
        raw_json={},
    )
    db.add(listing)
    db.flush()
    _link(db, 9003, config.id)
    db.commit()

    with patch("enricher.main.route") as mock_route:
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")
    mock_route.assert_not_called()
    assert db.query(ListingDistance).filter_by(hash_id=9003).first() is None


def test_enrich_all_configs_skips_config_without_destination(db):
    config = SearchConfig(
        name="NoDest",
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    _make_listing(db, hash_id=9004)
    _link(db, 9004, config.id)
    db.commit()

    with patch("enricher.main.route") as mock_route:
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")
    mock_route.assert_not_called()


def test_enrich_all_configs_skips_on_route_failure(db):
    config = _make_config(db, name="Enrich4")
    _make_listing(db, hash_id=9005)
    _link(db, 9005, config.id)
    db.commit()

    with patch("enricher.main.route", return_value=None):
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")

    assert db.query(ListingDistance).filter_by(hash_id=9005).first() is None
