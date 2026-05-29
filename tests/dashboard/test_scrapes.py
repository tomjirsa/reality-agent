from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from dashboard.routers.scrapes import group_runs
from shared.models import ScrapeRun, SearchConfig, Base
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
def setup_db_module():
    Base.metadata.create_all(TEST_ENGINE)
    yield
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def db_session():
    db = TestSession()
    yield db
    db.rollback()
    db.close()


def _make_run(started_at, finished_at=None, status="success", **kwargs):
    run = ScrapeRun(
        search_config_id=1,
        started_at=started_at,
        finished_at=finished_at,
        listings_found=kwargs.get("listings_found", 5),
        listings_new=kwargs.get("listings_new", 1),
        listings_updated=kwargs.get("listings_updated", 0),
        listings_removed=kwargs.get("listings_removed", 0),
        status=status,
        error_message=kwargs.get("error_message"),
    )
    return run


def test_group_runs_groups_by_config_name():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [
        (_make_run(t, t_end), "Config A", 1, True),
        (_make_run(t, t_end), "Config A", 1, True),
        (_make_run(t, t_end), "Config B", 2, True),
    ]
    groups = group_runs(rows)
    names = [g["config_name"] for g in groups]
    assert "Config A" in names
    assert "Config B" in names
    assert len(groups) == 2


def test_group_runs_run_count():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [
        (_make_run(t, t_end), "Config A", 1, True),
        (_make_run(t, t_end), "Config A", 1, True),
    ]
    groups = group_runs(rows)
    assert len(groups[0]["runs"]) == 2


def test_group_runs_duration_seconds():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)
    rows = [(_make_run(start, end), "Config A", 1, True)]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] == 90


def test_group_runs_duration_none_when_running():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    rows = [(_make_run(start, None, status="running"), "Config A", 1, True)]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] is None


def test_group_runs_empty():
    assert group_runs([]) == []


def test_group_runs_carries_config_id():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [(_make_run(t, t_end), "Config X", 99, True)]
    groups = group_runs(rows)
    assert groups[0]["config_id"] == 99


def test_group_runs_carries_config_active():
    t = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    t_end = datetime(2026, 1, 1, 10, 1, tzinfo=UTC)
    rows = [(_make_run(t, t_end), "Config Y", 5, False)]
    groups = group_runs(rows)
    assert groups[0]["config_active"] is False


def test_scrape_log_includes_running_run(db_session):
    from datetime import timedelta
    config = SearchConfig(
        name="Running Config",
        category_main_cb=1,
        category_type_cb=1,
        created_at=datetime.now(UTC),
    )
    db_session.add(config)
    db_session.flush()

    # Add a completed run to avoid timezone comparison issues with next_run
    completed_run = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC) - timedelta(hours=2),
        finished_at=datetime.now(UTC) - timedelta(hours=1, minutes=50),
        status="success",
        listings_found=10,
        listings_new=5,
        listings_updated=2,
        listings_removed=0,
    )
    db_session.add(completed_run)
    db_session.flush()

    # Add a running run
    running_run = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC),
        status="running",
        progress_total=100,
        progress_done=42,
    )
    db_session.add(running_run)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    response = client.get("/scrapes")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "42" in response.text
    assert "100" in response.text


def test_trigger_run_single_config_calls_scraper_with_config_id(db_session):
    from unittest.mock import patch, MagicMock
    from shared.config import settings

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with patch("dashboard.routers.scrapes.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client = TestClient(app, follow_redirects=False)
        response = client.post("/scrapes/run/42")
    app.dependency_overrides.clear()

    mock_post.assert_called_once_with(
        f"{settings.scraper_url}/run",
        params={"config_id": 42},
        timeout=5,
    )
    assert response.status_code == 303
    assert "/scrapes" in response.headers["location"]
