# Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the two-phase scraper that fetches listings from sreality.cz, upserts them into PostgreSQL, detects price changes, detects removals, and logs each run to `scrape_runs`.

**Architecture:** `scraper/search.py` handles Phase 1 (paginated search sweep), `scraper/detail.py` handles Phase 2 (selective full-detail fetch for new/changed listings). `scraper/main.py` orchestrates both phases per search config, manages `scrape_runs` audit records, and drives the APScheduler job. Functions accept an explicit `Session` parameter for testability — no direct import of `shared.db`.

**Tech Stack:** Python 3.12, httpx (sync), SQLAlchemy 2.x, APScheduler 3.x

**Prerequisite:** Plan 1 (core infra) must be complete. Run `pip install -r requirements-dev.txt` and `pip install httpx==0.27.0 apscheduler==3.10.4` before starting.

---

## API Notes

sreality.cz internal REST API (no auth required, no official docs — these are observed field names):

**Search endpoint:** `GET https://www.sreality.cz/api/cs/v2/estates`
- Params: `category_main_cb`, `category_type_cb`, `category_sub_cb` (pipe-separated), `locality_region_id`, `locality_district_id`, `czk_price_summary_min`, `czk_price_summary_max`, `usable_area`, `ownership`, `no_auction`, `per_page` (max 20), `from` (0-based offset)
- Response: `{ "_embedded": { "estates": [...] }, "result_size": N }`
- Each estate: `{ "hash_id": int, "name": str, "price_czk": int, "locality": str, "is_new": bool, ... }`

**Detail endpoint:** `GET https://www.sreality.cz/api/cs/v2/estates/{hash_id}`
- Response: full object with `locality` as object `{ "address": str, "district_id": int, "region_id": int }`
- `items` array: `[{ "name": "Plocha", "value": "80 m²" }, { "name": "Podlaží", "value": "3. podlaží" }, ...]`
- Item names for extraction: `"Plocha"` → area_m2, `"Podlaží"` → floor, `"Typ budovy"` → building_type, `"Stav objektu"` → condition, `"Vlastnictví"` → ownership

**Heads-up:** The actual API field names may differ slightly. If scraping fails, inspect a raw response and adjust the field name constants at the top of `search.py` and `detail.py`.

---

## File Map

| File | Responsibility |
|------|---------------|
| `scraper/search.py` | `search_page()` and `search_all()` — paginated search sweep, returns list of lightweight dicts |
| `scraper/detail.py` | `fetch_detail()` — fetches full listing detail, returns parsed dict |
| `scraper/main.py` | `run_scrape()` orchestrates one full run per config; APScheduler entry point |
| `tests/scraper/test_search.py` | Unit tests with mocked httpx |
| `tests/scraper/test_detail.py` | Unit tests with mocked httpx |
| `tests/scraper/test_main.py` | Integration tests for upsert, removal detection, scrape_run logging |

---

### Task 1: scraper/search.py + tests

**Files:**
- Create: `scraper/search.py`
- Create: `tests/scraper/test_search.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/scraper/test_search.py
import pytest
from unittest.mock import patch, MagicMock
from scraper.search import search_page, search_all, build_search_params
from shared.models import SearchConfig
from datetime import datetime, timezone


def make_config(**kwargs):
    defaults = dict(
        id=1,
        name="Test",
        category_main_cb=1,
        category_type_cb=1,
        category_sub_cb=None,
        locality_region_id=None,
        locality_district_id=5007,
        czk_price_min=None,
        czk_price_max=None,
        usable_area_min=None,
        usable_area_max=None,
        ownership=None,
        no_auction=True,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    config = MagicMock(spec=SearchConfig)
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


def make_estate(hash_id=1001, price=5_000_000, name="Byt 3+kk", locality="Praha 2"):
    return {
        "hash_id": hash_id,
        "name": name,
        "price_czk": price,
        "locality": locality,
        "is_new": False,
    }


def test_build_search_params_basic():
    config = make_config()
    params = build_search_params(config, from_offset=0)
    assert params["category_main_cb"] == 1
    assert params["category_type_cb"] == 1
    assert params["locality_district_id"] == 5007
    assert params["no_auction"] == 1
    assert params["per_page"] == 20
    assert params["from"] == 0


def test_build_search_params_with_price_range():
    config = make_config(czk_price_min=3_000_000, czk_price_max=6_000_000)
    params = build_search_params(config, from_offset=20)
    assert params["czk_price_summary_min"] == 3_000_000
    assert params["czk_price_summary_max"] == 6_000_000
    assert params["from"] == 20


def test_build_search_params_omits_none_values():
    config = make_config(locality_region_id=None, locality_district_id=None)
    params = build_search_params(config, from_offset=0)
    assert "locality_region_id" not in params
    assert "locality_district_id" not in params


def test_search_page_returns_estates():
    config = make_config()
    fake_response = {
        "_embedded": {"estates": [make_estate(1001), make_estate(1002)]},
        "result_size": 2,
    }
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_client.get.return_value = mock_resp

    estates, total = search_page(mock_client, config, from_offset=0)
    assert len(estates) == 2
    assert estates[0]["hash_id"] == 1001
    assert total == 2


def test_search_page_empty_results():
    config = make_config()
    fake_response = {"_embedded": {"estates": []}, "result_size": 0}
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_client.get.return_value = mock_resp

    estates, total = search_page(mock_client, config, from_offset=0)
    assert estates == []
    assert total == 0


def test_search_all_paginates():
    config = make_config()
    page1 = {"_embedded": {"estates": [make_estate(i) for i in range(20)]}, "result_size": 25}
    page2 = {"_embedded": {"estates": [make_estate(i) for i in range(20, 25)]}, "result_size": 25}

    mock_client = MagicMock()
    responses = []
    for data in [page1, page2]:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = data
        responses.append(mock_resp)
    mock_client.get.side_effect = responses

    all_estates = search_all(mock_client, config)
    assert len(all_estates) == 25
    assert mock_client.get.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/scraper/test_search.py -v
```
Expected: `ImportError: No module named 'scraper.search'`

- [ ] **Step 3: Write `scraper/search.py`**

```python
import httpx
from typing import Any
from shared.models import SearchConfig

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"
PER_PAGE = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def build_search_params(config: SearchConfig, from_offset: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "category_main_cb": config.category_main_cb,
        "category_type_cb": config.category_type_cb,
        "per_page": PER_PAGE,
        "from": from_offset,
    }
    if config.category_sub_cb:
        params["category_sub_cb"] = config.category_sub_cb
    if config.locality_region_id is not None:
        params["locality_region_id"] = config.locality_region_id
    if config.locality_district_id is not None:
        params["locality_district_id"] = config.locality_district_id
    if config.czk_price_min is not None:
        params["czk_price_summary_min"] = config.czk_price_min
    if config.czk_price_max is not None:
        params["czk_price_summary_max"] = config.czk_price_max
    if config.usable_area_min is not None:
        params["usable_area_min"] = config.usable_area_min
    if config.usable_area_max is not None:
        params["usable_area_max"] = config.usable_area_max
    if config.ownership is not None:
        params["ownership"] = config.ownership
    if config.no_auction:
        params["no_auction"] = 1
    return params


def search_page(
    client: httpx.Client, config: SearchConfig, from_offset: int
) -> tuple[list[dict], int]:
    params = build_search_params(config, from_offset)
    resp = client.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    estates = data.get("_embedded", {}).get("estates", [])
    total = data.get("result_size", 0)
    return estates, total


def search_all(client: httpx.Client, config: SearchConfig) -> list[dict]:
    all_estates = []
    offset = 0
    while True:
        estates, total = search_page(client, config, from_offset=offset)
        all_estates.extend(estates)
        offset += PER_PAGE
        if offset >= total or not estates:
            break
    return all_estates
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/scraper/test_search.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add scraper/search.py tests/scraper/test_search.py
git commit -m "feat: scraper Phase 1 search sweep"
```

---

### Task 2: scraper/detail.py + tests

**Files:**
- Create: `scraper/detail.py`
- Create: `tests/scraper/test_detail.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/scraper/test_detail.py
import pytest
from unittest.mock import MagicMock
from scraper.detail import fetch_detail, parse_detail, extract_item_value


SAMPLE_DETAIL_RESPONSE = {
    "hash_id": 1234567890,
    "name": "Prodej bytu 3+kk, 80 m²",
    "price_czk": 5_900_000,
    "is_new": False,
    "locality": {
        "address": "Praha 2 - Vinohrady, Blanická",
        "district_id": 5007,
        "region_id": 10,
    },
    "items": [
        {"name": "Plocha", "value": "80 m²"},
        {"name": "Podlaží", "value": "3. podlaží z 6"},
        {"name": "Typ budovy", "value": "Cihlová"},
        {"name": "Stav objektu", "value": "Velmi dobrý"},
        {"name": "Vlastnictví", "value": "Osobní"},
    ],
}


def test_extract_item_value_found():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Plocha") == "80 m²"
    assert extract_item_value(items, "Typ budovy") == "Cihlová"


def test_extract_item_value_missing():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Neexistuje") is None


def test_parse_detail_maps_fields():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE)
    assert result["hash_id"] == 1234567890
    assert result["name"] == "Prodej bytu 3+kk, 80 m²"
    assert result["price_czk"] == 5_900_000
    assert result["area_m2"] == 80
    assert result["locality"] == "Praha 2 - Vinohrady, Blanická"
    assert result["locality_district_id"] == 5007
    assert result["locality_region_id"] == 10
    assert result["floor"] == "3. podlaží z 6"
    assert result["building_type"] == "Cihlová"
    assert result["condition"] == "Velmi dobrý"
    assert result["ownership"] == "Osobní"
    assert result["is_new_flag"] is False
    assert result["raw_json"] == SAMPLE_DETAIL_RESPONSE


def test_parse_detail_area_extraction():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = [{"name": "Plocha", "value": "120 m²"}]
    result = parse_detail(response)
    assert result["area_m2"] == 120


def test_parse_detail_missing_area_returns_none():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response)
    assert result["area_m2"] is None


def test_fetch_detail_calls_correct_url():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
    mock_client.get.return_value = mock_resp

    result = fetch_detail(mock_client, 1234567890)
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert "1234567890" in call_args[0][0]
    assert result["hash_id"] == 1234567890


def test_parse_detail_price_per_m2_computed():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE)
    assert result["price_per_m2"] == pytest.approx(5_900_000 / 80)


def test_parse_detail_price_per_m2_none_if_no_area():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response)
    assert result["price_per_m2"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/scraper/test_detail.py -v
```
Expected: `ImportError: No module named 'scraper.detail'`

- [ ] **Step 3: Write `scraper/detail.py`**

```python
import re
import httpx
from typing import Any, Optional

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def extract_item_value(items: list[dict], name: str) -> Optional[str]:
    for item in items:
        if item.get("name") == name:
            return item.get("value")
    return None


def _parse_area(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else None


def parse_detail(data: dict) -> dict[str, Any]:
    items = data.get("items", [])
    locality = data.get("locality", {})
    if isinstance(locality, str):
        locality_address = locality
        district_id = None
        region_id = None
    else:
        locality_address = locality.get("address")
        district_id = locality.get("district_id")
        region_id = locality.get("region_id")

    area_raw = extract_item_value(items, "Plocha")
    area_m2 = _parse_area(area_raw)
    price_czk = data.get("price_czk")
    price_per_m2 = price_czk / area_m2 if (price_czk and area_m2) else None

    return {
        "hash_id": data["hash_id"],
        "name": data.get("name", ""),
        "price_czk": price_czk,
        "area_m2": area_m2,
        "price_per_m2": price_per_m2,
        "locality": locality_address,
        "locality_district_id": district_id,
        "locality_region_id": region_id,
        "floor": extract_item_value(items, "Podlaží"),
        "building_type": extract_item_value(items, "Typ budovy"),
        "condition": extract_item_value(items, "Stav objektu"),
        "ownership": extract_item_value(items, "Vlastnictví"),
        "is_new_flag": bool(data.get("is_new", False)),
        "raw_json": data,
    }


def fetch_detail(client: httpx.Client, hash_id: int) -> dict[str, Any]:
    url = f"{BASE_URL}/{hash_id}"
    resp = client.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_detail(resp.json())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/scraper/test_detail.py -v
```
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add scraper/detail.py tests/scraper/test_detail.py
git commit -m "feat: scraper Phase 2 detail fetch and parsing"
```

---

### Task 3: scraper/main.py + orchestration tests

**Files:**
- Create: `scraper/main.py`
- Create: `tests/scraper/test_main.py`

The orchestration logic lives in `run_scrape(db, config)`. `main.py` also contains the APScheduler setup. Tests cover the DB logic (upsert, removal, scrape_run) using the SQLite fixture from `tests/conftest.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scraper/test_main.py
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from shared.models import SearchConfig, Listing, ListingPriceHistory, ScrapeRun
from scraper.main import upsert_listings, detect_removals, create_scrape_run, finish_scrape_run

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
    config = make_search_config(db)
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=3001,
        name="Old listing",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
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
    config = make_search_config(db)
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=3002,
        name="Active listing",
        price_czk=4_000_000,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/scraper/test_main.py -v
```
Expected: `ImportError: No module named 'scraper.main'`

- [ ] **Step 3: Write `scraper/main.py`**

```python
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import SessionLocal
from shared.models import Listing, ListingPriceHistory, SearchConfig, ScrapeRun
from scraper.search import search_all
from scraper.detail import fetch_detail

logger = logging.getLogger(__name__)
UTC = timezone.utc


def create_scrape_run(db: Session, config: SearchConfig) -> ScrapeRun:
    run = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_scrape_run(
    db: Session,
    run: ScrapeRun,
    listings_found: int,
    listings_new: int,
    listings_updated: int,
    listings_removed: int,
    error: str | None = None,
) -> None:
    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    run.listings_updated = listings_updated
    run.listings_removed = listings_removed
    run.status = "error" if error else "success"
    run.error_message = error
    db.commit()


def upsert_listings(
    db: Session, config: SearchConfig, details: list[dict[str, Any]]
) -> dict[str, int]:
    stats = {"new": 0, "updated": 0}
    now = datetime.now(UTC)
    for d in details:
        existing = db.query(Listing).filter_by(hash_id=d["hash_id"]).first()
        if existing is None:
            listing = Listing(
                hash_id=d["hash_id"],
                name=d["name"],
                price_czk=d["price_czk"],
                area_m2=d["area_m2"],
                price_per_m2=d["price_per_m2"],
                locality=d["locality"],
                locality_district_id=d["locality_district_id"],
                locality_region_id=d["locality_region_id"],
                floor=d["floor"],
                building_type=d["building_type"],
                condition=d["condition"],
                ownership=d["ownership"],
                category_main_cb=config.category_main_cb,
                category_type_cb=config.category_type_cb,
                is_active=True,
                is_new_flag=d["is_new_flag"],
                first_seen_at=now,
                last_seen_at=now,
                raw_json=d["raw_json"],
            )
            db.add(listing)
            stats["new"] += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            existing.raw_json = d["raw_json"]
            if existing.price_czk != d["price_czk"]:
                history = ListingPriceHistory(
                    hash_id=existing.hash_id,
                    price_czk=existing.price_czk,
                    price_per_m2=existing.price_per_m2,
                    recorded_at=now,
                )
                db.add(history)
                existing.price_czk = d["price_czk"]
                existing.price_per_m2 = d["price_per_m2"]
                stats["updated"] += 1
    db.commit()
    return stats


def detect_removals(
    db: Session, config: SearchConfig, current_hash_ids: set[int]
) -> int:
    query = (
        db.query(Listing)
        .filter(
            Listing.is_active == True,
            Listing.category_main_cb == config.category_main_cb,
            Listing.category_type_cb == config.category_type_cb,
            ~Listing.hash_id.in_(current_hash_ids),
        )
    )
    if config.locality_district_id is not None:
        query = query.filter(Listing.locality_district_id == config.locality_district_id)
    elif config.locality_region_id is not None:
        query = query.filter(Listing.locality_region_id == config.locality_region_id)

    removed = query.all()
    now = datetime.now(UTC)
    for listing in removed:
        listing.is_active = False
        listing.removed_at = now
        if listing.first_seen_at:
            listing.days_to_sell = (now.replace(tzinfo=None) - listing.first_seen_at.replace(tzinfo=None)).days
    db.commit()
    return len(removed)


def run_scrape(db: Session, config: SearchConfig) -> None:
    run = create_scrape_run(db, config)
    logger.info("Starting scrape for config: %s", config.name)
    try:
        with httpx.Client() as client:
            # Phase 1
            raw_estates = search_all(client, config)
            current_hash_ids = {e["hash_id"] for e in raw_estates}

            # Phase 2 — fetch detail only for new or price-changed listings
            existing_prices = {
                row.hash_id: row.price_czk
                for row in db.query(Listing.hash_id, Listing.price_czk)
                .filter(Listing.hash_id.in_(current_hash_ids))
                .all()
            }
            details = []
            for estate in raw_estates:
                hid = estate["hash_id"]
                price = estate.get("price_czk")
                if hid not in existing_prices or existing_prices[hid] != price:
                    details.append(fetch_detail(client, hid))
                else:
                    # Only touch last_seen_at
                    db.query(Listing).filter_by(hash_id=hid).update(
                        {"last_seen_at": datetime.now(UTC)}
                    )
            db.commit()

            stats = upsert_listings(db, config, details)
            removed = detect_removals(db, config, current_hash_ids)

        finish_scrape_run(
            db,
            run,
            listings_found=len(current_hash_ids),
            listings_new=stats["new"],
            listings_updated=stats["updated"],
            listings_removed=removed,
        )
        logger.info(
            "Scrape complete for %s: found=%d new=%d updated=%d removed=%d",
            config.name,
            len(current_hash_ids),
            stats["new"],
            stats["updated"],
            removed,
        )
    except Exception as exc:
        finish_scrape_run(
            db, run,
            listings_found=0, listings_new=0, listings_updated=0, listings_removed=0,
            error=str(exc),
        )
        logger.exception("Scrape failed for config %s", config.name)


def scrape_all_configs() -> None:
    db = SessionLocal()
    try:
        configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        scrape_all_configs,
        "interval",
        hours=settings.scrape_interval_hours,
        next_run_time=datetime.now(),
    )
    logger.info("Scraper starting, interval=%dh", settings.scrape_interval_hours)
    scheduler.start()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/scraper/test_main.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Run all scraper tests**

```bash
poetry run pytest tests/scraper/ -v
```
Expected: 22 PASSED

- [ ] **Step 6: Commit**

```bash
git add scraper/main.py tests/scraper/test_main.py
git commit -m "feat: scraper orchestration — upsert, removal detection, APScheduler"
```
