# tests/dashboard/test_listings.py
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models import Base, Listing, ListingScore
from shared.db import get_db
from dashboard.main import app

UTC = timezone.utc

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(TEST_ENGINE)
    yield
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def session():
    db = TestSession()
    yield db
    db.rollback()
    db.close()


@pytest.fixture
def client(session):
    def override_get_db():
        try:
            yield session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def add_listing_with_score(session, hash_id, price, score_val=75.0, is_hot=False, is_active=True):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Byt {hash_id}",
        price_czk=price,
        area_m2=80,
        price_per_m2=price / 80,
        locality="Praha 2",
        locality_district_id=5007,
        category_main_cb=1,
        category_type_cb=1,
        is_active=is_active,
        first_seen_at=now - timedelta(days=5),
        last_seen_at=now,
    )
    session.add(listing)
    session.flush()
    score = ListingScore(
        hash_id=hash_id,
        price_percentile=20.0,
        price_per_m2_percentile=18.0,
        days_on_market=5,
        had_price_drop=False,
        is_hot=is_hot,
        combined_score=score_val,
        computed_at=now,
    )
    session.add(score)
    session.commit()


def test_listings_feed_returns_200(client, session):
    add_listing_with_score(session, hash_id=8001, price=4_000_000)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Byt 8001" in resp.text


def test_listings_feed_only_shows_active(client, session):
    add_listing_with_score(session, hash_id=8002, price=4_000_000, is_active=True)
    add_listing_with_score(session, hash_id=8003, price=2_000_000, is_active=False)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Byt 8002" in resp.text
    assert "Byt 8003" not in resp.text


def test_listings_feed_hot_filter(client, session):
    add_listing_with_score(session, hash_id=8004, price=4_000_000, is_hot=True)
    add_listing_with_score(session, hash_id=8005, price=4_000_000, is_hot=False)
    resp = client.get("/?hot_only=1")
    assert resp.status_code == 200
    assert "Byt 8004" in resp.text
    assert "Byt 8005" not in resp.text


def test_listings_feed_min_score_filter(client, session):
    add_listing_with_score(session, hash_id=8006, price=4_000_000, score_val=80.0)
    add_listing_with_score(session, hash_id=8007, price=4_000_000, score_val=50.0)
    resp = client.get("/?min_score=70")
    assert resp.status_code == 200
    assert "Byt 8006" in resp.text
    assert "Byt 8007" not in resp.text


def test_listing_detail_returns_200(client, session):
    add_listing_with_score(session, hash_id=8010, price=5_000_000)
    resp = client.get("/listing/8010")
    assert resp.status_code == 200
    assert "Byt 8010" in resp.text


def test_listing_detail_returns_404_for_missing(client):
    resp = client.get("/listing/9999999")
    assert resp.status_code == 404
