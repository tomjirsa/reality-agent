# tests/dashboard/test_market.py
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
        yield session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def add_listing(session, hash_id, price, district_id, category_main=1, is_active=True):
    now = datetime.now(UTC)
    area = 80
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=price,
        area_m2=area,
        price_per_m2=price / area,
        locality=f"District {district_id}",
        locality_district_id=district_id,
        category_main_cb=category_main,
        category_type_cb=1,
        is_active=is_active,
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now,
    )
    session.add(listing)
    session.commit()


def test_market_overview_returns_200(client, session):
    add_listing(session, hash_id=9001, price=4_000_000, district_id=5007)
    add_listing(session, hash_id=9002, price=5_000_000, district_id=5007)
    resp = client.get("/market")
    assert resp.status_code == 200


def test_market_overview_contains_district(client, session):
    add_listing(session, hash_id=9011, price=3_000_000, district_id=5008)
    resp = client.get("/market")
    assert resp.status_code == 200
    assert "5008" in resp.text or "District 5008" in resp.text
