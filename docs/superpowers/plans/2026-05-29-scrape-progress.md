# Scrape Progress Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a live progress bar and "X / Y listings processed" counter on the Scrape Log page while a scrape is running, updating via 5-second page auto-refresh.

**Architecture:** Add two nullable integer columns (`progress_total`, `progress_done`) to `scrape_runs`. The scraper writes them mid-run; the dashboard router reads the active running run and passes it to the template, which conditionally renders the progress banner and a `<meta refresh>` tag.

**Tech Stack:** SQLAlchemy, Alembic, FastAPI/Jinja2, Bootstrap 5

---

## File Map

| File | Change |
|---|---|
| `shared/models.py` | Add `progress_total`, `progress_done` to `ScrapeRun` |
| `migrations/versions/0006_scrape_progress.py` | New Alembic migration |
| `scraper/main.py` | Set `progress_total` after search; increment `progress_done` per listing |
| `dashboard/routers/scrapes.py` | Query running run, add to template context |
| `dashboard/templates/base.html` | Add `{% block head %}` extension point |
| `dashboard/templates/scrapes.html` | Auto-refresh meta tag + progress banner |
| `tests/scraper/test_main.py` | Tests for progress column writes |
| `tests/dashboard/test_scrapes.py` | Test router passes `running_run` |

---

## Task 1: Add columns to ScrapeRun model and migration

**Files:**
- Modify: `shared/models.py`
- Create: `migrations/versions/0006_scrape_progress.py`
- Test: `tests/shared/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/shared/test_models.py`:

```python
def test_scrape_run_has_progress_columns():
    from shared.models import ScrapeRun
    run = ScrapeRun()
    assert hasattr(run, "progress_total")
    assert hasattr(run, "progress_done")
    assert run.progress_total is None
    assert run.progress_done is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/shared/test_models.py::test_scrape_run_has_progress_columns -v
```

Expected: `FAILED` — `AttributeError` or assertion fails.

- [ ] **Step 3: Add columns to ScrapeRun in `shared/models.py`**

In `shared/models.py`, add two lines to `ScrapeRun` after `error_message`:

```python
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    progress_total: Mapped[Optional[int]] = mapped_column(Integer)
    progress_done: Mapped[Optional[int]] = mapped_column(Integer)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/shared/test_models.py::test_scrape_run_has_progress_columns -v
```

Expected: `PASSED`

- [ ] **Step 5: Create migration `migrations/versions/0006_scrape_progress.py`**

```python
"""add progress columns to scrape_runs

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("progress_total", sa.Integer(), nullable=True))
    op.add_column("scrape_runs", sa.Column("progress_done", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_runs", "progress_done")
    op.drop_column("scrape_runs", "progress_total")
```

- [ ] **Step 6: Commit**

```bash
git add shared/models.py migrations/versions/0006_scrape_progress.py tests/shared/test_models.py
git commit -m "feat: add progress_total and progress_done columns to scrape_runs"
```

---

## Task 2: Write progress during scrape

**Files:**
- Modify: `scraper/main.py`
- Test: `tests/scraper/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/scraper/test_main.py`:

```python
def test_run_scrape_sets_progress_total(db):
    config = make_search_config(db)
    raw_estates = [
        {"hash_id": 6001, "price_czk": 5_000_000},
        {"hash_id": 6002, "price_czk": 4_000_000},
    ]
    with patch("scraper.main.browser_client") as mock_bc, \
         patch("scraper.main.search_all", return_value=raw_estates), \
         patch("scraper.main.fetch_detail", side_effect=[
             make_listing_detail(6001), make_listing_detail(6002)
         ]):
        mock_bc.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_bc.return_value.__exit__ = MagicMock(return_value=False)
        run_scrape(db, config)

    run = db.query(ScrapeRun).filter_by(search_config_id=config.id).one()
    assert run.progress_total == 2


def test_run_scrape_increments_progress_done(db):
    config = make_search_config(db)
    raw_estates = [
        {"hash_id": 6003, "price_czk": 5_000_000},
        {"hash_id": 6004, "price_czk": 4_000_000},
    ]
    with patch("scraper.main.browser_client") as mock_bc, \
         patch("scraper.main.search_all", return_value=raw_estates), \
         patch("scraper.main.fetch_detail", side_effect=[
             make_listing_detail(6003), make_listing_detail(6004)
         ]):
        mock_bc.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_bc.return_value.__exit__ = MagicMock(return_value=False)
        run_scrape(db, config)

    run = db.query(ScrapeRun).filter_by(search_config_id=config.id).one()
    assert run.progress_done == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/scraper/test_main.py::test_run_scrape_sets_progress_total tests/scraper/test_main.py::test_run_scrape_increments_progress_done -v
```

Expected: `FAILED` — `AssertionError` (columns are None).

- [ ] **Step 3: Update `run_scrape` in `scraper/main.py`**

Replace the `run_scrape` function body from `raw_estates = search_all(...)` through the end of the per-estate loop with the following (the surrounding try/except and `finish_scrape_run` calls are unchanged):

```python
        with browser_client() as client:
            raw_estates = search_all(client, config)
            run.progress_total = len(raw_estates)
            db.commit()
            current_hash_ids = {e["hash_id"] for e in raw_estates}

            existing_prices = {
                row.hash_id: row.price_czk
                for row in db.query(Listing.hash_id, Listing.price_czk)
                .filter(Listing.hash_id.in_(current_hash_ids))
                .all()
            }
            stats = {"new": 0, "updated": 0}
            for estate in raw_estates:
                hid = estate["hash_id"]
                price = estate.get("price_czk")
                if hid not in existing_prices or existing_prices[hid] != price:
                    detail = fetch_detail(client, hid)
                    if detail is None:
                        continue
                    s = upsert_listings(db, config, [detail])
                    stats["new"] += s["new"]
                    stats["updated"] += s["updated"]
                else:
                    db.query(Listing).filter_by(hash_id=hid).update(
                        {"last_seen_at": datetime.now(UTC)}
                    )
                run.progress_done = (run.progress_done or 0) + 1
                db.commit()

            removed = detect_removals(db, config, current_hash_ids) if current_hash_ids else 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/scraper/test_main.py::test_run_scrape_sets_progress_total tests/scraper/test_main.py::test_run_scrape_increments_progress_done -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full scraper test suite to check for regressions**

```bash
pytest tests/scraper/test_main.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add scraper/main.py tests/scraper/test_main.py
git commit -m "feat: write progress_total and progress_done to scrape run during scrape"
```

---

## Task 3: Pass running run to dashboard template

**Files:**
- Modify: `dashboard/routers/scrapes.py`
- Test: `tests/dashboard/test_scrapes.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/dashboard/test_scrapes.py`:

```python
def test_scrape_log_includes_running_run(db):
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from dashboard.main import app
    from shared.models import SearchConfig, ScrapeRun
    from shared.db import get_db

    UTC = timezone.utc

    config = SearchConfig(
        name="Running Config",
        category_main_cb=1,
        category_type_cb=1,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    run = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC),
        status="running",
        progress_total=100,
        progress_done=42,
    )
    db.add(run)
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    response = client.get("/scrapes")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "42" in response.text
    assert "100" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/dashboard/test_scrapes.py::test_scrape_log_includes_running_run -v
```

Expected: `FAILED` — "42" / "100" not in response (template doesn't render them yet).

- [ ] **Step 3: Update `scrape_log` in `dashboard/routers/scrapes.py`**

Add a `running_run` query and pass it to the template. The full updated `scrape_log` function:

```python
@router.get("/scrapes", response_class=HTMLResponse)
def scrape_log(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(ScrapeRun, SearchConfig.name)
        .join(SearchConfig, ScrapeRun.search_config_id == SearchConfig.id)
        .order_by(ScrapeRun.started_at.desc())
        .all()
    )
    groups = group_runs(rows)

    last_run = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).first()
    next_run = None
    if last_run:
        next_run = last_run.started_at + timedelta(hours=settings.scrape_interval_hours)

    running_run = (
        db.query(ScrapeRun)
        .filter_by(status="running")
        .order_by(ScrapeRun.started_at.desc())
        .first()
    )

    return templates.TemplateResponse(request, "scrapes.html", {
        "groups": groups,
        "next_run": next_run,
        "now": datetime.now(UTC),
        "interval_hours": settings.scrape_interval_hours,
        "running_run": running_run,
    })
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/dashboard/test_scrapes.py::test_scrape_log_includes_running_run -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full dashboard test suite**

```bash
pytest tests/dashboard/test_scrapes.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add dashboard/routers/scrapes.py tests/dashboard/test_scrapes.py
git commit -m "feat: pass running_run to scrape log template"
```

---

## Task 4: Add progress banner and auto-refresh to template

**Files:**
- Modify: `dashboard/templates/base.html`
- Modify: `dashboard/templates/scrapes.html`

- [ ] **Step 1: Add `{% block head %}` to `base.html`**

In `dashboard/templates/base.html`, add a `{% block head %}{% endblock %}` inside `<head>`, after the existing `<script>` tag:

```html
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>
  {% block head %}{% endblock %}
</head>
```

- [ ] **Step 2: Add auto-refresh and progress banner to `scrapes.html`**

At the very top of `{% block content %}` in `dashboard/templates/scrapes.html`, insert:

```html
{% block head %}
{% if running_run %}<meta http-equiv="refresh" content="5">{% endif %}
{% endblock %}
```

Then, between the "triggered" alert block and the `{% if next_run %}` block, insert the progress banner:

```html
{% if running_run %}
<div class="card mb-3 border-primary">
  <div class="card-body py-2">
    {% if running_run.progress_total %}
      {% set done = running_run.progress_done or 0 %}
      {% set total = running_run.progress_total %}
      {% set pct = ((done / total) * 100) | int %}
      {% set elapsed = (now - running_run.started_at).seconds %}
      <div class="d-flex justify-content-between align-items-center mb-1">
        <span class="fw-semibold text-primary">Scraping…</span>
        <span class="text-muted small">{{ done }} / {{ total }} listings &nbsp;·&nbsp; {{ elapsed }}s elapsed</span>
      </div>
      <div class="progress" style="height: 8px;">
        <div class="progress-bar progress-bar-striped progress-bar-animated"
             role="progressbar"
             style="width: {{ pct }}%"
             aria-valuenow="{{ pct }}" aria-valuemin="0" aria-valuemax="100">
        </div>
      </div>
    {% else %}
      <div class="d-flex align-items-center gap-2">
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <span class="text-muted">Starting scrape…</span>
      </div>
    {% endif %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: Run the full test suite to check nothing is broken**

```bash
pytest tests/dashboard/ -v
```

Expected: all tests `PASSED`.

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/base.html dashboard/templates/scrapes.html
git commit -m "feat: show live progress bar on scrape log page during active scrape"
```

---

## Task 5: Apply migration and verify end-to-end

- [ ] **Step 1: Apply the migration**

```bash
docker compose exec dashboard alembic upgrade head
```

Expected output ends with: `Running upgrade 0005 -> 0006, add progress columns to scrape_runs`

- [ ] **Step 2: Trigger a scrape and watch progress**

Open the dashboard at `http://localhost:<port>/scrapes`, click "Run now", then refresh the page within the first few seconds. Verify:
- A blue card appears above the accordion with "Starting scrape…" spinner (before search completes)
- Within a few seconds: progress bar appears with "X / Y listings" and elapsed seconds
- Page auto-refreshes every 5 seconds
- After the scrape finishes: progress banner disappears and auto-refresh stops

- [ ] **Step 3: Push**

```bash
git push
```
