# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the web dashboard via FastAPI + Jinja2 on port 8080 — listings feed with filters, per-listing detail with price history chart, market overview, and search config management.

**Architecture:** `dashboard/main.py` creates the FastAPI app and wires up 3 routers. Each router injects a DB session via `Depends(get_db)`. Templates use Jinja2; Chart.js is loaded from CDN. The "Trigger Analysis" button in the dashboard POSTs to the analyzer service at `settings.analyzer_url/run` using httpx.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLAlchemy 2.x, httpx, Chart.js (CDN)

**Prerequisite:** Plans 1, 2, and 3 must be complete.

---

## File Map

| File | Responsibility |
|------|---------------|
| `dashboard/main.py` | FastAPI app creation, router registration, `get_db` dependency |
| `dashboard/routers/listings.py` | `GET /` (feed with filters), `GET /listing/{hash_id}` (detail) |
| `dashboard/routers/market.py` | `GET /market` (per-district summary) |
| `dashboard/routers/configs.py` | `GET /configs`, `POST /configs`, `POST /configs/{id}/toggle`, `POST /configs/{id}/delete`, `POST /trigger` |
| `dashboard/templates/base.html` | Nav, Bootstrap 5 (CDN), Chart.js (CDN) |
| `dashboard/templates/listings.html` | Filter form, sortable table of active listings |
| `dashboard/templates/detail.html` | Full listing stats + price history Chart.js line chart |
| `dashboard/templates/market.html` | Per-district price/m² chart (Chart.js) + active listing count table |
| `dashboard/templates/configs.html` | Add/edit/toggle search config form |
| `tests/dashboard/test_listings.py` | TestClient route tests for listings feed + detail |
| `tests/dashboard/test_market.py` | TestClient route test for market overview |
| `tests/dashboard/test_configs.py` | TestClient route tests for configs CRUD + trigger |

---

### Task 1: dashboard/main.py

**Files:**
- Create: `dashboard/main.py`

- [ ] **Step 1: Write `dashboard/main.py`**

```python
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from pathlib import Path

from shared.db import get_db  # noqa: F401 — re-exported for routers
from dashboard.routers import listings, market, configs

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Reality Agent")
app.include_router(listings.router)
app.include_router(market.router)
app.include_router(configs.router)
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/main.py
git commit -m "feat: dashboard FastAPI app skeleton"
```

---

### Task 2: dashboard/routers/listings.py + tests

**Files:**
- Create: `dashboard/routers/listings.py`
- Create: `tests/dashboard/test_listings.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_listings.py
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.models import Base, Listing, ListingScore
from shared.db import get_db
from dashboard.main import app

UTC = timezone.utc

TEST_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_listings.py -v
```
Expected: `ImportError: No module named 'dashboard.routers.listings'`

- [ ] **Step 3: Write `dashboard/routers/listings.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import Listing, ListingScore, ListingPriceHistory
from dashboard.main import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def listings_feed(
    request: Request,
    db: Session = Depends(get_db),
    category_main_cb: int | None = None,
    locality_district_id: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_score: float | None = None,
    hot_only: int = 0,
    page: int = 1,
):
    PAGE_SIZE = 50
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
    results = (
        query.order_by(ListingScore.combined_score.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    return templates.TemplateResponse(
        "listings.html",
        {
            "request": request,
            "listings": results,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "filters": {
                "category_main_cb": category_main_cb,
                "locality_district_id": locality_district_id,
                "min_price": min_price,
                "max_price": max_price,
                "min_score": min_score,
                "hot_only": hot_only,
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
    return templates.TemplateResponse(
        "detail.html",
        {"request": request, "listing": listing, "score": score, "history": history},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_listings.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add dashboard/routers/listings.py tests/dashboard/test_listings.py
git commit -m "feat: dashboard listings feed and detail routes"
```

---

### Task 3: dashboard/routers/market.py + tests

**Files:**
- Create: `dashboard/routers/market.py`
- Create: `tests/dashboard/test_market.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_market.py
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.models import Base, Listing, ListingScore
from shared.db import get_db
from dashboard.main import app

UTC = timezone.utc
TEST_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_market.py -v
```
Expected: `ImportError: No module named 'dashboard.routers.market'`

- [ ] **Step 3: Write `dashboard/routers/market.py`**

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import Listing
from dashboard.main import templates

router = APIRouter()


@router.get("/market", response_class=HTMLResponse)
def market_overview(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(
            Listing.locality_district_id,
            Listing.category_main_cb,
            Listing.category_type_cb,
            func.count(Listing.hash_id).label("listing_count"),
            func.avg(Listing.price_per_m2).label("avg_price_per_m2"),
            func.min(Listing.price_per_m2).label("min_price_per_m2"),
            func.max(Listing.price_per_m2).label("max_price_per_m2"),
        )
        .filter(Listing.is_active == True, Listing.price_per_m2 != None)
        .group_by(
            Listing.locality_district_id,
            Listing.category_main_cb,
            Listing.category_type_cb,
        )
        .order_by(Listing.locality_district_id)
        .all()
    )
    summary = [
        {
            "district_id": r.locality_district_id,
            "category_main_cb": r.category_main_cb,
            "category_type_cb": r.category_type_cb,
            "listing_count": r.listing_count,
            "avg_price_per_m2": round(r.avg_price_per_m2 or 0, 0),
            "min_price_per_m2": round(r.min_price_per_m2 or 0, 0),
            "max_price_per_m2": round(r.max_price_per_m2 or 0, 0),
        }
        for r in rows
    ]
    return templates.TemplateResponse(
        "market.html", {"request": request, "summary": summary}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_market.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add dashboard/routers/market.py tests/dashboard/test_market.py
git commit -m "feat: dashboard market overview route"
```

---

### Task 4: dashboard/routers/configs.py + tests

**Files:**
- Create: `dashboard/routers/configs.py`
- Create: `tests/dashboard/test_configs.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_configs.py
import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.models import Base, SearchConfig
from shared.db import get_db
from dashboard.main import app

UTC = timezone.utc
TEST_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_configs.py -v
```
Expected: `ImportError: No module named 'dashboard.routers.configs'`

- [ ] **Step 3: Write `dashboard/routers/configs.py`**

```python
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import get_db
from shared.models import SearchConfig
from dashboard.main import templates

router = APIRouter()
logger = logging.getLogger(__name__)
UTC = timezone.utc


@router.get("/configs", response_class=HTMLResponse)
def list_configs(request: Request, db: Session = Depends(get_db)):
    configs = db.query(SearchConfig).order_by(SearchConfig.id).all()
    return templates.TemplateResponse(
        "configs.html", {"request": request, "configs": configs}
    )


@router.post("/configs")
def create_config(
    db: Session = Depends(get_db),
    name: str = Form(...),
    category_main_cb: int = Form(...),
    category_type_cb: int = Form(...),
    category_sub_cb: str = Form(None),
    locality_region_id: int = Form(None),
    locality_district_id: int = Form(None),
    czk_price_min: int = Form(None),
    czk_price_max: int = Form(None),
    usable_area_min: int = Form(None),
    usable_area_max: int = Form(None),
    ownership: int = Form(None),
    no_auction: bool = Form(True),
):
    config = SearchConfig(
        name=name,
        category_main_cb=category_main_cb,
        category_type_cb=category_type_cb,
        category_sub_cb=category_sub_cb,
        locality_region_id=locality_region_id,
        locality_district_id=locality_district_id,
        czk_price_min=czk_price_min,
        czk_price_max=czk_price_max,
        usable_area_min=usable_area_min,
        usable_area_max=usable_area_max,
        ownership=ownership,
        no_auction=no_auction,
        active=True,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/configs/{config_id}/toggle")
def toggle_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if config:
        config.active = not config.active
        db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/configs/{config_id}/delete")
def delete_config(config_id: int, db: Session = Depends(get_db)):
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if config:
        db.delete(config)
        db.commit()
    return RedirectResponse(url="/configs", status_code=303)


@router.post("/trigger")
def trigger_analysis():
    try:
        resp = httpx.post(f"{settings.analyzer_url}/run", timeout=10)
        resp.raise_for_status()
        logger.info("Analysis triggered successfully")
    except Exception:
        logger.exception("Failed to trigger analysis")
    return RedirectResponse(url="/configs", status_code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_configs.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add dashboard/routers/configs.py tests/dashboard/test_configs.py
git commit -m "feat: dashboard search config management + trigger analysis"
```

---

### Task 5: Templates

**Files:**
- Create: `dashboard/templates/base.html`
- Create: `dashboard/templates/listings.html`
- Create: `dashboard/templates/detail.html`
- Create: `dashboard/templates/market.html`
- Create: `dashboard/templates/configs.html`

- [ ] **Step 1: Write `dashboard/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Reality Agent{% endblock %}</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
  <div class="container">
    <a class="navbar-brand" href="/">Reality Agent</a>
    <div class="navbar-nav">
      <a class="nav-link" href="/">Listings</a>
      <a class="nav-link" href="/market">Market</a>
      <a class="nav-link" href="/configs">Configs</a>
    </div>
  </div>
</nav>
<div class="container mt-4">
  {% block content %}{% endblock %}
</div>
</body>
</html>
```

- [ ] **Step 2: Write `dashboard/templates/listings.html`**

```html
{% extends "base.html" %}
{% block title %}Listings{% endblock %}
{% block content %}
<h2>Listings <small class="text-muted fs-6">({{ total }} results)</small></h2>

<form class="row g-2 mb-3" method="get" action="/">
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
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for listing, score in listings %}
    <tr>
      <td>
        {% if score and score.is_hot %}
          <span class="badge bg-danger me-1">HOT</span>
        {% endif %}
        {{ listing.name }}
      </td>
      <td>{{ "{:,}".format(listing.price_czk or 0).replace(",", " ") }}</td>
      <td>{{ "{:,.0f}".format(listing.price_per_m2 or 0) }}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_per_m2_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ score.days_on_market }}{% endif %}</td>
      <td>{% if score %}<strong>{{ "{:.1f}".format(score.combined_score or 0) }}</strong>{% endif %}</td>
      <td>
        <a href="/listing/{{ listing.hash_id }}" class="btn btn-xs btn-outline-primary btn-sm">Detail</a>
        <a href="https://www.sreality.cz/detail/prodej/byt/{{ listing.hash_id }}"
           target="_blank" class="btn btn-xs btn-outline-secondary btn-sm">sreality</a>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<div class="d-flex gap-2">
  {% if page > 1 %}
  <a href="?page={{ page - 1 }}" class="btn btn-outline-secondary btn-sm">← Previous</a>
  {% endif %}
  {% if total > page * page_size %}
  <a href="?page={{ page + 1 }}" class="btn btn-outline-secondary btn-sm">Next →</a>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Write `dashboard/templates/detail.html`**

```html
{% extends "base.html" %}
{% block title %}{{ listing.name }}{% endblock %}
{% block content %}
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="/">Listings</a></li>
    <li class="breadcrumb-item active">{{ listing.name }}</li>
  </ol>
</nav>

<div class="row">
  <div class="col-md-6">
    <h3>{{ listing.name }}
      {% if score and score.is_hot %}<span class="badge bg-danger">HOT</span>{% endif %}
    </h3>
    <p class="text-muted">{{ listing.locality }}</p>
    <table class="table table-sm">
      <tr><td>Price</td><td><strong>{{ "{:,}".format(listing.price_czk or 0).replace(",", " ") }} CZK</strong></td></tr>
      <tr><td>Area</td><td>{{ listing.area_m2 }} m²</td></tr>
      <tr><td>Price/m²</td><td>{{ "{:,.0f}".format(listing.price_per_m2 or 0) }} CZK/m²</td></tr>
      <tr><td>Floor</td><td>{{ listing.floor or "—" }}</td></tr>
      <tr><td>Building type</td><td>{{ listing.building_type or "—" }}</td></tr>
      <tr><td>Condition</td><td>{{ listing.condition or "—" }}</td></tr>
      <tr><td>Ownership</td><td>{{ listing.ownership or "—" }}</td></tr>
      <tr><td>First seen</td><td>{{ listing.first_seen_at.strftime("%Y-%m-%d") if listing.first_seen_at else "—" }}</td></tr>
    </table>
    {% if score %}
    <h5>Bargain Scores</h5>
    <table class="table table-sm">
      <tr><td>Price percentile</td><td>{{ "{:.1f}".format(score.price_percentile or 0) }}th</td></tr>
      <tr><td>Price/m² percentile</td><td>{{ "{:.1f}".format(score.price_per_m2_percentile or 0) }}th</td></tr>
      <tr><td>Days on market</td><td>{{ score.days_on_market }}</td></tr>
      <tr><td>Price drop</td><td>{% if score.had_price_drop %}{{ "{:.1f}".format(score.price_drop_pct or 0) }}%{% else %}None{% endif %}</td></tr>
      <tr><td>Combined score</td><td><strong>{{ "{:.1f}".format(score.combined_score or 0) }}/100</strong></td></tr>
    </table>
    {% endif %}
    <a href="https://www.sreality.cz/detail/prodej/byt/{{ listing.hash_id }}"
       target="_blank" class="btn btn-primary">View on sreality.cz</a>
  </div>
  <div class="col-md-6">
    {% if history %}
    <h5>Price History</h5>
    <canvas id="priceChart"></canvas>
    <script>
      const labels = [{% for h in history %}"{{ h.recorded_at.strftime('%Y-%m-%d') }}"{% if not loop.last %},{% endif %}{% endfor %}];
      const data = [{% for h in history %}{{ h.price_czk }}{% if not loop.last %},{% endif %}{% endfor %}];
      new Chart(document.getElementById('priceChart'), {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Price (CZK)',
            data: data,
            borderColor: 'rgb(75, 192, 192)',
            tension: 0.1
          }]
        },
        options: { responsive: true }
      });
    </script>
    {% else %}
    <p class="text-muted">No price history recorded.</p>
    {% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Write `dashboard/templates/market.html`**

```html
{% extends "base.html" %}
{% block title %}Market Overview{% endblock %}
{% block content %}
<h2>Market Overview</h2>

<table class="table table-sm table-hover">
  <thead>
    <tr>
      <th>District ID</th>
      <th>Category</th>
      <th>Type</th>
      <th>Active listings</th>
      <th>Avg price/m²</th>
      <th>Min price/m²</th>
      <th>Max price/m²</th>
    </tr>
  </thead>
  <tbody>
    {% for row in summary %}
    <tr>
      <td>{{ row.district_id }}</td>
      <td>{{ "Byty" if row.category_main_cb == 1 else "Domy" }}</td>
      <td>{{ "Prodej" if row.category_type_cb == 1 else "Pronájem" }}</td>
      <td>{{ row.listing_count }}</td>
      <td>{{ "{:,.0f}".format(row.avg_price_per_m2) }}</td>
      <td>{{ "{:,.0f}".format(row.min_price_per_m2) }}</td>
      <td>{{ "{:,.0f}".format(row.max_price_per_m2) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Write `dashboard/templates/configs.html`**

```html
{% extends "base.html" %}
{% block title %}Search Configs{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h2>Search Configs</h2>
  <form method="post" action="/trigger">
    <button class="btn btn-warning" type="submit">▶ Run Analysis Now</button>
  </form>
</div>

<table class="table table-sm mb-4">
  <thead>
    <tr>
      <th>ID</th><th>Name</th><th>Category</th><th>District</th><th>Price range</th><th>Active</th><th>Actions</th>
    </tr>
  </thead>
  <tbody>
    {% for config in configs %}
    <tr class="{% if not config.active %}text-muted{% endif %}">
      <td>{{ config.id }}</td>
      <td>{{ config.name }}</td>
      <td>{{ "Byty" if config.category_main_cb == 1 else "Domy" }} / {{ "Prodej" if config.category_type_cb == 1 else "Pronájem" }}</td>
      <td>{{ config.locality_district_id or "Any" }}</td>
      <td>
        {% if config.czk_price_min or config.czk_price_max %}
          {{ "{:,}".format(config.czk_price_min or 0) }} – {{ "{:,}".format(config.czk_price_max or 0) }}
        {% else %}Any{% endif %}
      </td>
      <td>{% if config.active %}<span class="badge bg-success">Active</span>{% else %}<span class="badge bg-secondary">Paused</span>{% endif %}</td>
      <td>
        <form method="post" action="/configs/{{ config.id }}/toggle" class="d-inline">
          <button class="btn btn-sm btn-outline-secondary">
            {% if config.active %}Pause{% else %}Resume{% endif %}
          </button>
        </form>
        <form method="post" action="/configs/{{ config.id }}/delete" class="d-inline"
              onsubmit="return confirm('Delete {{ config.name }}?')">
          <button class="btn btn-sm btn-outline-danger">Delete</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h4>Add Search Config</h4>
<form method="post" action="/configs" class="row g-3">
  <div class="col-md-4">
    <label class="form-label">Name</label>
    <input type="text" name="name" class="form-control" required placeholder="e.g. Praha 2 byty 3+kk">
  </div>
  <div class="col-md-2">
    <label class="form-label">Category</label>
    <select name="category_main_cb" class="form-select">
      <option value="1">Byty</option>
      <option value="2">Domy</option>
    </select>
  </div>
  <div class="col-md-2">
    <label class="form-label">Type</label>
    <select name="category_type_cb" class="form-select">
      <option value="1">Prodej</option>
      <option value="2">Pronájem</option>
    </select>
  </div>
  <div class="col-md-2">
    <label class="form-label">District ID</label>
    <input type="number" name="locality_district_id" class="form-control" placeholder="e.g. 5007">
  </div>
  <div class="col-md-2">
    <label class="form-label">Layout codes</label>
    <input type="text" name="category_sub_cb" class="form-control" placeholder="e.g. 4|5|6">
  </div>
  <div class="col-md-2">
    <label class="form-label">Min price (CZK)</label>
    <input type="number" name="czk_price_min" class="form-control">
  </div>
  <div class="col-md-2">
    <label class="form-label">Max price (CZK)</label>
    <input type="number" name="czk_price_max" class="form-control">
  </div>
  <div class="col-md-2 d-flex align-items-end">
    <button class="btn btn-primary" type="submit">Add Config</button>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 6: Run all dashboard tests**

```bash
pytest tests/dashboard/ -v
```
Expected: 13 PASSED

- [ ] **Step 7: Commit**

```bash
git add dashboard/templates/
git commit -m "feat: dashboard Jinja2 templates"
```

---

### Task 6: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```
Expected: ~48 PASSED across all 4 test suites (exact count depends on fixture overlap between modules)

- [ ] **Step 2: Final commit if any fixes**

```bash
git add -p
git commit -m "fix: full test suite green"
```

---

## Deployment Checklist (manual)

After all 4 plans are complete:

- [ ] Copy `.env.example` → `.env`, fill in real credentials
- [ ] `docker compose build`
- [ ] `docker compose up -d db` (wait for healthy)
- [ ] `docker compose run --rm scraper alembic upgrade head` (run migrations)
- [ ] `docker compose up -d`
- [ ] Open `http://localhost:8080` and verify listings page loads
- [ ] Add at least one search config via the Configs page
- [ ] Click "Run Analysis Now" to trigger the analyzer
- [ ] Check logs: `docker compose logs scraper` and `docker compose logs analyzer`
