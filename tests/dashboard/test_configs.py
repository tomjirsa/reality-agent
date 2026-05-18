# tests/dashboard/test_configs.py
import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models import Base, SearchConfig
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


def test_configs_page_returns_200(client):
    resp = client.get("/configs")
    assert resp.status_code == 200


def test_create_config(client, session):
    resp = client.post("/configs", data={
        "name": "Praha byty prodej",
        "category_main_cb": "1",
        "category_type_cb": "1",
        "locality_district_id": "5007",
    }, follow_redirects=True)
    assert resp.status_code == 200
    config = session.query(SearchConfig).filter_by(name="Praha byty prodej").first()
    assert config is not None
    assert config.active is True


def test_toggle_config(client, session):
    config = SearchConfig(
        name="Toggle Test",
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(config)
    session.commit()
    resp = client.post(f"/configs/{config.id}/toggle", follow_redirects=True)
    assert resp.status_code == 200
    session.refresh(config)
    assert config.active is False


def test_delete_config(client, session):
    config = SearchConfig(
        name="Delete Test",
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(config)
    session.commit()
    config_id = config.id
    resp = client.post(f"/configs/{config_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert session.query(SearchConfig).filter_by(id=config_id).first() is None


def test_trigger_analysis(client):
    with patch("dashboard.routers.configs.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        resp = client.post("/trigger", follow_redirects=True)
    assert resp.status_code == 200
    mock_post.assert_called_once()
