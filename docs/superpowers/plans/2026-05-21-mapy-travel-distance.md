# Travel Distance Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-listing travel distance/duration from a configurable destination using the mapy.cz Routing API, stored as enrichment data and surfaced in the dashboard.

**Architecture:** The scraper orchestrates a three-phase pipeline: scrape → enrich distances → trigger analyzer. A new `enricher/` package calls the mapy.cz Routing API for listings that don't yet have a distance row for the active search config's destination. Distances are stored in a new `listing_distances` table keyed on `(hash_id, search_config_id)`, with a `listing_search_configs` junction table linking listings to the config that found them.

**Tech Stack:** Python 3.12, SQLAlchemy 2, httpx, FastAPI, Jinja2, Alembic, pytest with SQLite in-memory, Bootstrap 5

---

## File Map

**Create:**
- `enricher/__init__.py` — package marker
- `enricher/client.py` — mapy.cz geocode + routing HTTP calls
- `enricher/main.py` — enrichment orchestration (`enrich_all_configs`)
- `tests/enricher/__init__.py` — package marker
- `tests/enricher/test_client.py` — unit tests for client (mocked httpx)
- `tests/enricher/test_main.py` — unit tests for orchestration (real SQLite, mocked client)
- `migrations/versions/0003_travel_distance.py` — Alembic migration

**Modify:**
- `shared/models.py` — add `ListingSearchConfig`, `ListingDistance` models; 4 new columns on `SearchConfig`
- `shared/config.py` — add `mapy_api_key`
- `pyproject.toml` — add `enricher` to packages
- `scraper/main.py` — record junction table in `upsert_listings`; replace `scrape_all_configs` with `run_pipeline`
- `dashboard/routers/configs.py` — geocode on config save; new form fields
- `dashboard/routers/listings.py` — config filter + distance join in feed; distances in detail
- `dashboard/templates/configs.html` — destination + travel mode fields and table columns
- `dashboard/templates/listings.html` — config filter dropdown; distance column
- `dashboard/templates/detail.html` — travel distances section
- `tests/scraper/test_main.py` — tests for junction table recording
- `tests/dashboard/test_configs.py` — tests for geocoding path
- `tests/dashboard/test_listings.py` — tests for config filter + distance display

---

## Task 1: Data models and Alembic migration

**Files:**
- Modify: `shared/models.py`
- Modify: `pyproject.toml`
- Create: `migrations/versions/0003_travel_distance.py`
- Test: `tests/shared/test_models.py`

- [ ] **Step 1: Add new models and columns to `shared/models.py`**

Add four columns to `SearchConfig` and two new model classes at the end of the file:

```python
# Inside SearchConfig class, after the `active` column:
destination_label: Mapped[Optional[str]] = mapped_column(Text)
destination_lat: Mapped[Optional[float]] = mapped_column(Float)
destination_lon: Mapped[Optional[float]] = mapped_column(Float)
travel_mode: Mapped[Optional[str]] = mapped_column(Text)
```

```python
# New classes appended after ScrapeRun:

class ListingSearchConfig(Base):
    __tablename__ = "listing_search_configs"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), primary_key=True
    )


class ListingDistance(Base):
    __tablename__ = "listing_distances"

    hash_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.hash_id"), primary_key=True
    )
    search_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_configs.id"), primary_key=True
    )
    travel_mode: Mapped[str] = mapped_column(Text, nullable=False)
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
```

- [ ] **Step 2: Write failing model import test in `tests/shared/test_models.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

```
poetry run pytest tests/shared/test_models.py::test_new_model_tablenames tests/shared/test_models.py::test_search_config_has_destination_columns -v
```

Expected: `FAILED` — `ImportError` or `AssertionError` (models not defined yet — you're mid-edit, the step above should be done first, so expect PASS here as confirmation)

- [ ] **Step 4: Run test to verify it passes**

```
poetry run pytest tests/shared/test_models.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Add `enricher` package to `pyproject.toml`**

In the `[tool.poetry]` section, add `enricher` to the packages list:

```toml
[tool.poetry]
packages = [
    {include = "shared"},
    {include = "scraper"},
    {include = "analyzer"},
    {include = "dashboard"},
    {include = "enricher"},
]
```

- [ ] **Step 6: Create Alembic migration `migrations/versions/0003_travel_distance.py`**

```python
"""travel distance enrichment

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("search_configs", sa.Column("destination_label", sa.Text(), nullable=True))
    op.add_column("search_configs", sa.Column("destination_lat", sa.Float(), nullable=True))
    op.add_column("search_configs", sa.Column("destination_lon", sa.Float(), nullable=True))
    op.add_column("search_configs", sa.Column("travel_mode", sa.Text(), nullable=True))
    op.create_table(
        "listing_search_configs",
        sa.Column("hash_id", sa.BigInteger(), sa.ForeignKey("listings.hash_id"), nullable=False),
        sa.Column("search_config_id", sa.Integer(), sa.ForeignKey("search_configs.id"), nullable=False),
        sa.PrimaryKeyConstraint("hash_id", "search_config_id"),
    )
    op.create_table(
        "listing_distances",
        sa.Column("hash_id", sa.BigInteger(), sa.ForeignKey("listings.hash_id"), nullable=False),
        sa.Column("search_config_id", sa.Integer(), sa.ForeignKey("search_configs.id"), nullable=False),
        sa.Column("travel_mode", sa.Text(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("hash_id", "search_config_id"),
    )


def downgrade() -> None:
    op.drop_table("listing_distances")
    op.drop_table("listing_search_configs")
    op.drop_column("search_configs", "travel_mode")
    op.drop_column("search_configs", "destination_lon")
    op.drop_column("search_configs", "destination_lat")
    op.drop_column("search_configs", "destination_label")
```

- [ ] **Step 7: Run full test suite to confirm no regressions**

```
poetry run pytest -v
```

Expected: all existing tests `PASSED`, new model tests `PASSED`

- [ ] **Step 8: Commit**

```bash
git add shared/models.py pyproject.toml migrations/versions/0003_travel_distance.py tests/shared/test_models.py
git commit -m "feat: add ListingSearchConfig and ListingDistance models with migration"
```

---

## Task 2: mapy.cz API client

**Files:**
- Create: `enricher/__init__.py`
- Create: `enricher/client.py`
- Create: `tests/enricher/__init__.py`
- Create: `tests/enricher/test_client.py`

- [ ] **Step 1: Create package markers**

Create `enricher/__init__.py` and `tests/enricher/__init__.py` as empty files.

- [ ] **Step 2: Write failing tests in `tests/enricher/test_client.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from enricher.client import geocode, route


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_geocode_returns_lat_lon():
    mock_resp = _mock_response({
        "items": [{"position": {"lat": 50.0815, "lon": 14.4241}}]
    })
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("Václavské náměstí, Praha", "test-key")
    assert result == (50.0815, 14.4241)


def test_geocode_returns_none_on_empty_items():
    mock_resp = _mock_response({"items": []})
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("nonexistent place xyz", "test-key")
    assert result is None


def test_geocode_returns_none_on_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
        result = geocode("Praha", "test-key")
    assert result is None


def test_geocode_returns_none_on_4xx():
    mock_resp = _mock_response({}, status_code=401)
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("Praha", "bad-key")
    assert result is None


def test_route_returns_distance_and_duration():
    mock_resp = _mock_response({
        "routeSummary": {"distance": 1500, "duration": 300}
    })
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=123)
    assert result == {"distance_m": 1500, "duration_s": 300}
    params = mock_get.call_args[1]["params"]
    assert params["routeType"] == "car_fast_traffic"


def test_route_maps_travel_modes():
    mock_resp = _mock_response({"routeSummary": {"distance": 800, "duration": 600}})
    for mode, expected_type in [
        ("walk", "foot_fast"),
        ("bike", "bike_road"),
        ("transit", "public_transport"),
    ]:
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            route(50.087, 14.421, 50.075, 14.435, mode, "test-key")
        params = mock_get.call_args[1]["params"]
        assert params["routeType"] == expected_type, f"mode={mode}"


def test_route_returns_none_on_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_returns_none_on_4xx():
    mock_resp = _mock_response({}, status_code=404)
    with patch("httpx.get", return_value=mock_resp):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_returns_none_on_5xx():
    mock_resp = _mock_response({}, status_code=500)
    with patch("httpx.get", return_value=mock_resp):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_uses_lon_lat_order_in_params():
    mock_resp = _mock_response({"routeSummary": {"distance": 1000, "duration": 200}})
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        route(50.087, 14.421, 50.075, 14.435, "car", "test-key")
    params = mock_get.call_args[1]["params"]
    # mapy.cz expects "lon,lat" order
    assert params["start"] == "14.421,50.087"
    assert params["end"] == "14.435,50.075"
```

- [ ] **Step 3: Run tests to verify they fail**

```
poetry run pytest tests/enricher/test_client.py -v
```

Expected: `ImportError: cannot import name 'geocode' from 'enricher.client'`

- [ ] **Step 4: Implement `enricher/client.py`**

```python
import logging
import httpx

logger = logging.getLogger(__name__)

MAPY_BASE = "https://api.mapy.cz/v1"

TRAVEL_MODE_MAP: dict[str, str] = {
    "car": "car_fast_traffic",
    "walk": "foot_fast",
    "bike": "bike_road",
    "transit": "public_transport",
}


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lon) for address, or None on any failure."""
    try:
        resp = httpx.get(
            f"{MAPY_BASE}/geocode",
            params={"apikey": api_key, "query": address, "lang": "cs", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            logger.warning("Geocode returned no results for: %s", address)
            return None
        pos = items[0]["position"]
        return float(pos["lat"]), float(pos["lon"])
    except httpx.TimeoutException:
        logger.warning("Geocode timeout for address: %s", address)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("Geocode HTTP %s for address: %s", exc.response.status_code, address)
        return None


def route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str,
    api_key: str,
    hash_id: int | None = None,
) -> dict | None:
    """Return {"distance_m": int, "duration_s": int} or None on any failure."""
    route_type = TRAVEL_MODE_MAP.get(mode, "car_fast_traffic")
    try:
        resp = httpx.get(
            f"{MAPY_BASE}/routing/route",
            params={
                "apikey": api_key,
                "lang": "cs",
                "routeType": route_type,
                "start": f"{origin_lon},{origin_lat}",
                "end": f"{dest_lon},{dest_lat}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        summary = resp.json()["routeSummary"]
        return {"distance_m": summary["distance"], "duration_s": summary["duration"]}
    except httpx.TimeoutException:
        logger.warning("Route timeout for hash_id=%s", hash_id)
        return None
    except httpx.HTTPStatusError as exc:
        sc = exc.response.status_code
        if sc >= 500:
            logger.warning("Route HTTP 5xx (%s) for hash_id=%s", sc, hash_id)
        else:
            logger.warning("Route HTTP 4xx (%s) for hash_id=%s", sc, hash_id)
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

```
poetry run pytest tests/enricher/test_client.py -v
```

Expected: all 9 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add enricher/__init__.py enricher/client.py tests/enricher/__init__.py tests/enricher/test_client.py
git commit -m "feat: add mapy.cz geocode and routing client"
```

---

## Task 3: Enrichment orchestration

**Files:**
- Create: `enricher/main.py`
- Create: `tests/enricher/test_main.py`

- [ ] **Step 1: Write failing tests in `tests/enricher/test_main.py`**

```python
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
    listing = _make_listing(db, hash_id=9001)
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
    listing = _make_listing(db, hash_id=9002)
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
    listing = _make_listing(db, hash_id=9004)
    _link(db, 9004, config.id)
    db.commit()

    with patch("enricher.main.route") as mock_route:
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")
    mock_route.assert_not_called()


def test_enrich_all_configs_skips_on_route_failure(db):
    config = _make_config(db, name="Enrich4")
    listing = _make_listing(db, hash_id=9005)
    _link(db, 9005, config.id)
    db.commit()

    with patch("enricher.main.route", return_value=None):
        with patch("enricher.main.time.sleep"):
            enrich_all_configs(db, "test-key")

    assert db.query(ListingDistance).filter_by(hash_id=9005).first() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
poetry run pytest tests/enricher/test_main.py -v
```

Expected: `ImportError: cannot import name 'enrich_all_configs' from 'enricher.main'`

- [ ] **Step 3: Implement `enricher/main.py`**

```python
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared.models import Listing, ListingDistance, ListingSearchConfig, SearchConfig
from enricher.client import route

logger = logging.getLogger(__name__)
UTC = timezone.utc
ENRICH_DELAY = 0.2


def _extract_gps(raw_json: dict | None) -> tuple[float, float] | None:
    if not raw_json:
        return None
    map_obj = raw_json.get("map", {})
    if not isinstance(map_obj, dict):
        return None
    lat = map_obj.get("lat")
    lon = map_obj.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def enrich_all_configs(db: Session, api_key: str) -> None:
    configs = (
        db.query(SearchConfig)
        .filter(
            SearchConfig.active == True,
            SearchConfig.destination_lat.isnot(None),
            SearchConfig.destination_lon.isnot(None),
            SearchConfig.travel_mode.isnot(None),
        )
        .all()
    )
    for config in configs:
        _enrich_config(db, config, api_key)


def _enrich_config(db: Session, config: SearchConfig, api_key: str) -> None:
    enriched_ids = {
        row.hash_id
        for row in db.query(ListingDistance.hash_id).filter_by(search_config_id=config.id).all()
    }
    pending_ids = [
        row.hash_id
        for row in db.query(ListingSearchConfig.hash_id).filter_by(search_config_id=config.id).all()
        if row.hash_id not in enriched_ids
    ]
    if not pending_ids:
        return

    listings = {
        lst.hash_id: lst
        for lst in db.query(Listing).filter(Listing.hash_id.in_(pending_ids)).all()
    }
    logger.info("Enriching %d listings for config '%s'", len(pending_ids), config.name)

    for hash_id in pending_ids:
        listing = listings.get(hash_id)
        if listing is None:
            continue
        coords = _extract_gps(listing.raw_json)
        if coords is None:
            logger.warning("No GPS in raw_json for hash_id=%s", hash_id)
            continue
        lat, lon = coords
        time.sleep(ENRICH_DELAY)
        result = route(
            origin_lat=lat,
            origin_lon=lon,
            dest_lat=config.destination_lat,
            dest_lon=config.destination_lon,
            mode=config.travel_mode,
            api_key=api_key,
            hash_id=hash_id,
        )
        if result is None:
            continue
        db.add(ListingDistance(
            hash_id=hash_id,
            search_config_id=config.id,
            travel_mode=config.travel_mode,
            distance_m=result["distance_m"],
            duration_s=result["duration_s"],
            computed_at=datetime.now(UTC),
        ))
        db.commit()
        logger.info(
            "Enriched hash_id=%s: %dm %ds", hash_id, result["distance_m"], result["duration_s"]
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
poetry run pytest tests/enricher/test_main.py -v
```

Expected: all 8 tests `PASSED`

- [ ] **Step 5: Run full suite to check for regressions**

```
poetry run pytest -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add enricher/main.py tests/enricher/test_main.py
git commit -m "feat: add enrichment orchestration for mapy.cz travel distances"
```

---

## Task 4: Scraper pipeline integration

**Files:**
- Modify: `scraper/main.py`
- Modify: `shared/config.py`
- Modify: `tests/scraper/test_main.py`

- [ ] **Step 1: Add `mapy_api_key` to `shared/config.py`**

Add after `bargain_score_threshold`:

```python
mapy_api_key: str = ""
```

- [ ] **Step 2: Write failing tests for junction table recording in `tests/scraper/test_main.py`**

Add these tests at the end of the existing file:

```python
from shared.models import ListingSearchConfig


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
```

- [ ] **Step 3: Run new tests to verify they fail**

```
poetry run pytest tests/scraper/test_main.py::test_upsert_records_listing_search_config_link tests/scraper/test_main.py::test_upsert_does_not_duplicate_link_on_second_call -v
```

Expected: `FAILED` — `AssertionError: assert None is not None`

- [ ] **Step 4: Add junction recording helper and update `upsert_listings` in `scraper/main.py`**

Add import at the top of `scraper/main.py`:

```python
from shared.models import Listing, ListingPriceHistory, SearchConfig, ScrapeRun, ListingSearchConfig
```

Add new helper function before `upsert_listings`:

```python
def _record_config_link(db: Session, hash_id: int, search_config_id: int) -> None:
    exists = db.query(ListingSearchConfig).filter_by(
        hash_id=hash_id, search_config_id=search_config_id
    ).first()
    if not exists:
        db.add(ListingSearchConfig(hash_id=hash_id, search_config_id=search_config_id))
```

In `upsert_listings`, add a call to `_record_config_link` inside the for-loop, after the `if existing is None` / `else` block (i.e., for every listing regardless of new/existing):

```python
    for d in details:
        existing = db.query(Listing).filter_by(hash_id=d["hash_id"]).first()
        if existing is None:
            listing = Listing(...)
            db.add(listing)
            stats["new"] += 1
        else:
            # ... existing update logic ...
            pass
        _record_config_link(db, d["hash_id"], config.id)   # <-- add this line
    db.commit()
    return stats
```

- [ ] **Step 5: Run junction tests to verify they pass**

```
poetry run pytest tests/scraper/test_main.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Replace `scrape_all_configs` with `run_pipeline` in `scraper/main.py`**

Replace the `scrape_all_configs` function and the `__main__` block with:

```python
def run_pipeline() -> None:
    db = SessionLocal()
    try:
        configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
        if settings.mapy_api_key:
            from enricher.main import enrich_all_configs
            enrich_all_configs(db, settings.mapy_api_key)
        try:
            httpx.post(f"{settings.analyzer_url}/run", timeout=30)
        except Exception:
            logger.exception("Failed to trigger analyzer after pipeline")
    except Exception:
        logger.exception("Pipeline failed")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=settings.scrape_interval_hours,
        next_run_time=datetime.now(),
    )
    logger.info("Scraper starting, interval=%dh", settings.scrape_interval_hours)
    scheduler.start()
```

- [ ] **Step 7: Run full test suite**

```
poetry run pytest -v
```

Expected: all tests `PASSED`

- [ ] **Step 8: Commit**

```bash
git add shared/config.py scraper/main.py tests/scraper/test_main.py
git commit -m "feat: record listing-config links in scraper; pipeline triggers enricher then analyzer"
```

---

## Task 5: Dashboard config form — geocoding and display

**Files:**
- Modify: `dashboard/routers/configs.py`
- Modify: `dashboard/templates/configs.html`
- Modify: `tests/dashboard/test_configs.py`

- [ ] **Step 1: Write failing tests in `tests/dashboard/test_configs.py`**

Add at the end of the existing file:

```python
def test_create_config_with_destination_geocodes_and_stores(client, session):
    with patch("dashboard.routers.configs.geocode", return_value=(50.0815, 14.4241)) as mock_geo:
        resp = client.post("/configs", data={
            "name": "Geo Test Config",
            "category_main_cb": "1",
            "category_type_cb": "1",
            "destination_address": "Václavské náměstí, Praha",
            "travel_mode": "car",
        }, follow_redirects=True)
    assert resp.status_code == 200
    mock_geo.assert_called_once_with("Václavské náměstí, Praha", "")
    config = session.query(SearchConfig).filter_by(name="Geo Test Config").first()
    assert config is not None
    assert config.destination_label == "Václavské náměstí, Praha"
    assert config.destination_lat == pytest.approx(50.0815)
    assert config.destination_lon == pytest.approx(14.4241)
    assert config.travel_mode == "car"


def test_create_config_geocode_failure_returns_422(client, session):
    with patch("dashboard.routers.configs.geocode", return_value=None):
        resp = client.post("/configs", data={
            "name": "Bad Geo Config",
            "category_main_cb": "1",
            "category_type_cb": "1",
            "destination_address": "nonexistent xyz 999",
            "travel_mode": "walk",
        }, follow_redirects=False)
    assert resp.status_code == 422
    assert session.query(SearchConfig).filter_by(name="Bad Geo Config").first() is None


def test_create_config_without_destination_skips_geocoding(client, session):
    with patch("dashboard.routers.configs.geocode") as mock_geo:
        resp = client.post("/configs", data={
            "name": "No Dest Config",
            "category_main_cb": "1",
            "category_type_cb": "1",
        }, follow_redirects=True)
    assert resp.status_code == 200
    mock_geo.assert_not_called()
    config = session.query(SearchConfig).filter_by(name="No Dest Config").first()
    assert config is not None
    assert config.destination_lat is None
```

- [ ] **Step 2: Run new tests to verify they fail**

```
poetry run pytest tests/dashboard/test_configs.py::test_create_config_with_destination_geocodes_and_stores tests/dashboard/test_configs.py::test_create_config_geocode_failure_returns_422 tests/dashboard/test_configs.py::test_create_config_without_destination_skips_geocoding -v
```

Expected: `FAILED`

- [ ] **Step 3: Update `dashboard/routers/configs.py`**

Add imports at the top:

```python
from fastapi.responses import HTMLResponse, RedirectResponse
from enricher.client import geocode
```

Update the `create_config` function signature to add new form fields, and add geocoding logic before saving:

```python
@router.post("/configs")
def create_config(
    db: Session = Depends(get_db),
    name: str = Form(...),
    category_main_cb: int = Form(...),
    category_type_cb: int = Form(...),
    category_sub_cb: str = Form(None),
    locality_region_id: str = Form(None),
    locality_district_id: list[str] = Form(None),
    czk_price_min: str = Form(None),
    czk_price_max: str = Form(None),
    usable_area_min: str = Form(None),
    usable_area_max: str = Form(None),
    ownership: str = Form(None),
    no_auction: bool = Form(True),
    destination_address: str = Form(None),
    travel_mode: str = Form(None),
):
    destination_label = None
    destination_lat = None
    destination_lon = None

    if destination_address:
        coords = geocode(destination_address, settings.mapy_api_key)
        if coords is None:
            return HTMLResponse(
                content=(
                    f"<p>Could not geocode destination: <em>{destination_address}</em>. "
                    "Please check the address and try again.</p>"
                    "<p><a href='/configs'>← Go back</a></p>"
                ),
                status_code=422,
            )
        destination_lat, destination_lon = coords
        destination_label = destination_address

    district_value = "|".join(locality_district_id) if locality_district_id else None
    config = SearchConfig(
        name=name,
        category_main_cb=category_main_cb,
        category_type_cb=category_type_cb,
        category_sub_cb=category_sub_cb or None,
        locality_region_id=_to_int(locality_region_id),
        locality_district_id=district_value,
        czk_price_min=_to_int(czk_price_min),
        czk_price_max=_to_int(czk_price_max),
        usable_area_min=_to_int(usable_area_min),
        usable_area_max=_to_int(usable_area_max),
        ownership=_to_int(ownership),
        no_auction=no_auction,
        active=True,
        created_at=datetime.now(UTC),
        destination_label=destination_label,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        travel_mode=travel_mode or None,
    )
    db.add(config)
    db.commit()
    return RedirectResponse(url="/configs", status_code=303)
```

- [ ] **Step 4: Update `dashboard/templates/configs.html`**

Add two columns to the config table header (after "Price range" `<th>`):

```html
<th>Destination</th><th>Travel mode</th>
```

Add corresponding cells inside `{% for config in configs %}` (after the price cell):

```html
<td>{{ config.destination_label or "—" }}</td>
<td>{{ config.travel_mode or "—" }}</td>
```

Add two new form fields inside the `<form>` before the "Add Config" button:

```html
<div class="col-md-8">
  <label class="form-label fw-semibold">Destination address</label>
  <input type="text" name="destination_address" class="form-control"
         placeholder="e.g. Václavské náměstí 1, Praha">
  <div class="form-text">Leave empty to skip travel distance enrichment for this search.</div>
</div>

<div class="col-md-4">
  <label class="form-label fw-semibold">Travel mode</label>
  <select name="travel_mode" class="form-select">
    <option value="">— none —</option>
    <option value="car">Car</option>
    <option value="walk">Walk</option>
    <option value="bike">Bike</option>
    <option value="transit">Public transit</option>
  </select>
</div>
```

- [ ] **Step 5: Run tests to verify they pass**

```
poetry run pytest tests/dashboard/test_configs.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add dashboard/routers/configs.py dashboard/templates/configs.html tests/dashboard/test_configs.py
git commit -m "feat: add destination geocoding to config form and display in config table"
```

---

## Task 6: Listings feed — config filter and distance column

**Files:**
- Modify: `dashboard/routers/listings.py`
- Modify: `dashboard/templates/listings.html`
- Modify: `tests/dashboard/test_listings.py`

- [ ] **Step 1: Write failing tests in `tests/dashboard/test_listings.py`**

Add imports at the top of the existing file:

```python
from shared.models import SearchConfig, ListingSearchConfig, ListingDistance
```

Add these tests at the end:

```python
def _add_config_with_dest(session, name="Work Config"):
    config = SearchConfig(
        name=name,
        category_main_cb=1,
        category_type_cb=1,
        active=True,
        destination_label="Wenceslas Square",
        destination_lat=50.0815,
        destination_lon=14.4241,
        travel_mode="car",
        created_at=datetime.now(UTC),
    )
    session.add(config)
    session.flush()
    return config


def test_listings_feed_config_filter_shows_only_linked_listings(client, session):
    config = _add_config_with_dest(session, name="FilterConfig1")
    add_listing_with_score(session, hash_id=7001, price=4_000_000)
    add_listing_with_score(session, hash_id=7002, price=4_000_000)
    session.add(ListingSearchConfig(hash_id=7001, search_config_id=config.id))
    session.commit()

    resp = client.get(f"/?search_config_id={config.id}")
    assert resp.status_code == 200
    assert "Byt 7001" in resp.text
    assert "Byt 7002" not in resp.text


def test_listings_feed_shows_distance_when_config_selected(client, session):
    config = _add_config_with_dest(session, name="FilterConfig2")
    add_listing_with_score(session, hash_id=7003, price=4_000_000)
    session.add(ListingSearchConfig(hash_id=7003, search_config_id=config.id))
    session.add(ListingDistance(
        hash_id=7003,
        search_config_id=config.id,
        travel_mode="car",
        distance_m=3500,
        duration_s=720,
        computed_at=datetime.now(UTC),
    ))
    session.commit()

    resp = client.get(f"/?search_config_id={config.id}")
    assert resp.status_code == 200
    assert "3.5" in resp.text   # 3500m shown as 3.5 km
    assert "12" in resp.text    # 720s shown as 12 min


def test_listings_feed_no_filter_hides_distance_column(client, session):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Distance" not in resp.text
```

- [ ] **Step 2: Run new tests to verify they fail**

```
poetry run pytest tests/dashboard/test_listings.py::test_listings_feed_config_filter_shows_only_linked_listings tests/dashboard/test_listings.py::test_listings_feed_shows_distance_when_config_selected tests/dashboard/test_listings.py::test_listings_feed_no_filter_hides_distance_column -v
```

Expected: `FAILED`

- [ ] **Step 3: Update `dashboard/routers/listings.py`**

Replace the entire file contents:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import (
    Listing, ListingDistance, ListingPriceHistory, ListingScore,
    ListingSearchConfig, SearchConfig,
)
from dashboard.deps import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def listings_feed(
    request: Request,
    db: Session = Depends(get_db),
    search_config_id: int | None = None,
    category_main_cb: int | None = None,
    locality_district_id: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_score: float | None = None,
    hot_only: bool = False,
    order_by: str | None = None,
    page: int = 1,
):
    PAGE_SIZE = 50
    configs = db.query(SearchConfig).order_by(SearchConfig.name).all()

    if search_config_id:
        query = (
            db.query(Listing, ListingScore, ListingDistance)
            .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
            .join(
                ListingSearchConfig,
                and_(
                    ListingSearchConfig.hash_id == Listing.hash_id,
                    ListingSearchConfig.search_config_id == search_config_id,
                ),
            )
            .outerjoin(
                ListingDistance,
                and_(
                    ListingDistance.hash_id == Listing.hash_id,
                    ListingDistance.search_config_id == search_config_id,
                ),
            )
            .filter(Listing.is_active == True)
        )
    else:
        query = (
            db.query(Listing, ListingScore)
            .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
            .filter(Listing.is_active == True)
        )

    if category_main_cb is not None:
        query = query.filter(Listing.category_main_cb == category_main_cb)
    if locality_district_id is not None:
        query = query.filter(Listing.locality_district_id == locality_district_id)
    if min_price is not None:
        query = query.filter(Listing.price_czk >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price_czk <= max_price)
    if min_score is not None:
        query = query.filter(ListingScore.combined_score >= min_score)
    if hot_only:
        query = query.filter(ListingScore.is_hot == True)

    total = query.count()

    if order_by == "distance" and search_config_id:
        query = query.order_by(ListingDistance.distance_m.asc())
    else:
        query = query.order_by(ListingScore.combined_score.desc())

    raw = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    if search_config_id:
        listings = raw
    else:
        listings = [(lst, score, None) for lst, score in raw]

    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "listings": listings,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "configs": configs,
            "filters": {
                "search_config_id": search_config_id,
                "category_main_cb": category_main_cb,
                "locality_district_id": locality_district_id,
                "min_price": min_price,
                "max_price": max_price,
                "min_score": min_score,
                "hot_only": hot_only,
                "order_by": order_by,
            },
        },
    )


@router.get("/listing/{hash_id}", response_class=HTMLResponse)
def listing_detail(request: Request, hash_id: int, db: Session = Depends(get_db)):
    result = (
        db.query(Listing, ListingScore)
        .outerjoin(ListingScore, Listing.hash_id == ListingScore.hash_id)
        .filter(Listing.hash_id == hash_id)
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    listing, score = result
    history = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.asc())
        .all()
    )
    distances = (
        db.query(ListingDistance, SearchConfig)
        .join(SearchConfig, ListingDistance.search_config_id == SearchConfig.id)
        .filter(ListingDistance.hash_id == hash_id)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"listing": listing, "score": score, "history": history, "distances": distances},
    )
```

- [ ] **Step 4: Update `dashboard/templates/listings.html`**

Replace the full template:

```html
{% extends "base.html" %}
{% block title %}Listings{% endblock %}
{% block content %}
<h2>Listings <small class="text-muted fs-6">({{ total }} results)</small></h2>

<form class="row g-2 mb-3" method="get" action="/">
  <div class="col-auto">
    <select name="search_config_id" class="form-select form-select-sm">
      <option value="">All searches</option>
      {% for config in configs %}
      <option value="{{ config.id }}"
        {% if filters.search_config_id == config.id %}selected{% endif %}>
        {{ config.name }}
      </option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <input type="number" name="min_price" class="form-control form-control-sm"
           placeholder="Min price" value="{{ filters.min_price or '' }}">
  </div>
  <div class="col-auto">
    <input type="number" name="max_price" class="form-control form-control-sm"
           placeholder="Max price" value="{{ filters.max_price or '' }}">
  </div>
  <div class="col-auto">
    <input type="number" name="min_score" class="form-control form-control-sm"
           placeholder="Min score" value="{{ filters.min_score or '' }}">
  </div>
  <div class="col-auto">
    <div class="form-check mt-1">
      <input class="form-check-input" type="checkbox" name="hot_only" value="1"
             id="hotOnly" {% if filters.hot_only %}checked{% endif %}>
      <label class="form-check-label" for="hotOnly">Hot only</label>
    </div>
  </div>
  {% if filters.search_config_id %}
  <div class="col-auto">
    <select name="order_by" class="form-select form-select-sm">
      <option value="">Sort: score</option>
      <option value="distance" {% if filters.order_by == 'distance' %}selected{% endif %}>
        Sort: distance
      </option>
    </select>
  </div>
  {% endif %}
  <div class="col-auto">
    <button class="btn btn-sm btn-primary" type="submit">Filter</button>
    <a class="btn btn-sm btn-outline-secondary" href="/">Reset</a>
  </div>
</form>

<table class="table table-sm table-hover">
  <thead>
    <tr>
      <th>Name</th>
      <th>Price</th>
      <th>Price/m²</th>
      <th>Price pct</th>
      <th>PPM² pct</th>
      <th>Days</th>
      <th>Score</th>
      {% if filters.search_config_id %}<th>Distance</th>{% endif %}
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for listing, score, distance in listings %}
    <tr>
      <td>
        {% if score and score.is_hot %}
          <span class="badge bg-danger me-1">HOT</span>
        {% endif %}
        {{ listing.name }}
      </td>
      <td>{{ "{:,}".format(listing.price_czk or 0).replace(",", " ") }}</td>
      <td>{{ "{:,.0f}".format(listing.price_per_m2 or 0) }}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_per_m2_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ score.days_on_market }}{% endif %}</td>
      <td>{% if score %}<strong>{{ "{:.1f}".format(score.combined_score or 0) }}</strong>{% endif %}</td>
      {% if filters.search_config_id %}
      <td>
        {% if distance %}
          {{ "{:.1f}".format(distance.distance_m / 1000) }} km
          / {{ (distance.duration_s // 60) }} min
        {% else %}—{% endif %}
      </td>
      {% endif %}
      <td>
        <a href="/listing/{{ listing.hash_id }}" class="btn btn-xs btn-outline-primary btn-sm">Detail</a>
        <a href="{{ sreality_url(listing) }}"
           target="_blank" class="btn btn-xs btn-outline-secondary btn-sm">sreality</a>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<div class="d-flex gap-2">
  {% if page > 1 %}
  <a href="?page={{ page - 1 }}&search_config_id={{ filters.search_config_id or '' }}"
     class="btn btn-outline-secondary btn-sm">← Previous</a>
  {% endif %}
  {% if total > page * page_size %}
  <a href="?page={{ page + 1 }}&search_config_id={{ filters.search_config_id or '' }}"
     class="btn btn-outline-secondary btn-sm">Next →</a>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

```
poetry run pytest tests/dashboard/test_listings.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add dashboard/routers/listings.py dashboard/templates/listings.html tests/dashboard/test_listings.py
git commit -m "feat: add search config filter and distance column to listings feed"
```

---

## Task 7: Listing detail — travel distances section

**Files:**
- Modify: `dashboard/templates/detail.html`
- Modify: `tests/dashboard/test_listings.py`

- [ ] **Step 1: Write failing test in `tests/dashboard/test_listings.py`**

Add at the end of the file:

```python
def test_listing_detail_shows_travel_distance(client, session):
    config = _add_config_with_dest(session, name="DetailConfig")
    add_listing_with_score(session, hash_id=7010, price=5_000_000)
    session.add(ListingSearchConfig(hash_id=7010, search_config_id=config.id))
    session.add(ListingDistance(
        hash_id=7010,
        search_config_id=config.id,
        travel_mode="car",
        distance_m=5200,
        duration_s=900,
        computed_at=datetime.now(UTC),
    ))
    session.commit()

    resp = client.get("/listing/7010")
    assert resp.status_code == 200
    assert "Travel distances" in resp.text
    assert "DetailConfig" in resp.text
    assert "5.2" in resp.text   # 5200m shown as 5.2 km
    assert "15" in resp.text    # 900s shown as 15 min


def test_listing_detail_no_distances_hides_section(client, session):
    add_listing_with_score(session, hash_id=7011, price=5_000_000)
    session.commit()

    resp = client.get("/listing/7011")
    assert resp.status_code == 200
    assert "Travel distances" not in resp.text
```

- [ ] **Step 2: Run new tests to verify they fail**

```
poetry run pytest tests/dashboard/test_listings.py::test_listing_detail_shows_travel_distance tests/dashboard/test_listings.py::test_listing_detail_no_distances_hides_section -v
```

Expected: `FAILED`

- [ ] **Step 3: Update `dashboard/templates/detail.html`**

Add a travel distances section after the "Bargain Scores" block (before the sreality link):

```html
    {% if distances %}
    <h5 class="mt-3">Travel distances</h5>
    <table class="table table-sm">
      <thead>
        <tr><th>Search</th><th>Mode</th><th>Distance</th><th>Duration</th></tr>
      </thead>
      <tbody>
        {% for dist, config in distances %}
        <tr>
          <td>{{ config.name }}</td>
          <td>{{ dist.travel_mode }}</td>
          <td>{{ "{:.1f}".format(dist.distance_m / 1000) }} km</td>
          <td>{{ dist.duration_s // 60 }} min</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}
```

- [ ] **Step 4: Run tests to verify they pass**

```
poetry run pytest tests/dashboard/test_listings.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Run full test suite for final verification**

```
poetry run pytest -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add dashboard/templates/detail.html tests/dashboard/test_listings.py
git commit -m "feat: show travel distances section on listing detail page"
```

---

## Deployment notes

Before running in production, set these env vars:

```
MAPY_API_KEY=<your mapy.cz API key>
```

Apply the migration against the production database:

```bash
alembic upgrade head
```

The migration is safe on existing data — all new columns are nullable and new tables start empty. Distance enrichment will populate incrementally on the next pipeline run.
