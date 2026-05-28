# Scrape Log Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/scrapes` dashboard page that shows scrape run history grouped by search config in Bootstrap collapsible cards.

**Architecture:** A single FastAPI route queries all `ScrapeRun` rows joined with `SearchConfig.name`, groups them in Python via a pure `group_runs()` helper, and passes the result to a Jinja2 template. No new models or migrations needed.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Bootstrap 5.3.3 (collapse component)

---

## File Map

| File | Action |
|---|---|
| `dashboard/routers/scrapes.py` | Create — router + `group_runs()` helper |
| `dashboard/templates/scrapes.html` | Create — Bootstrap collapse cards |
| `dashboard/main.py` | Modify — register scrapes router |
| `dashboard/templates/base.html` | Modify — add Scrapes nav link |
| `tests/dashboard/test_scrapes.py` | Create — unit tests for `group_runs()` |

---

## Task 1: Router and grouping logic

**Files:**
- Create: `dashboard/routers/scrapes.py`
- Create: `tests/dashboard/test_scrapes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/dashboard/test_scrapes.py`:

```python
from datetime import datetime, timezone
from dashboard.routers.scrapes import group_runs
from shared.models import ScrapeRun

UTC = timezone.utc


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
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config B"),
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
        (_make_run(t, t_end), "Config A"),
        (_make_run(t, t_end), "Config A"),
    ]
    groups = group_runs(rows)
    assert len(groups[0]["runs"]) == 2


def test_group_runs_duration_seconds():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)
    rows = [(_make_run(start, end), "Config A")]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] == 90


def test_group_runs_duration_none_when_running():
    start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    rows = [(_make_run(start, None, status="running"), "Config A")]
    groups = group_runs(rows)
    assert groups[0]["runs"][0]["duration"] is None


def test_group_runs_empty():
    assert group_runs([]) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/kali/Repos/reality-agent && poetry run pytest tests/dashboard/test_scrapes.py -v
```

Expected: `ImportError` — `group_runs` does not exist yet.

- [ ] **Step 3: Implement the router**

Create `dashboard/routers/scrapes.py`:

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from shared.db import get_db
from shared.models import ScrapeRun, SearchConfig
from dashboard.deps import templates

router = APIRouter()


def group_runs(rows: list[tuple]) -> list[dict]:
    groups: dict[str, dict] = {}
    for run, config_name in rows:
        if config_name not in groups:
            groups[config_name] = {"config_name": config_name, "runs": []}
        duration = None
        if run.finished_at and run.started_at:
            duration = int((run.finished_at - run.started_at).total_seconds())
        groups[config_name]["runs"].append({
            "started_at": run.started_at,
            "listings_found": run.listings_found,
            "listings_new": run.listings_new,
            "listings_updated": run.listings_updated,
            "listings_removed": run.listings_removed,
            "duration": duration,
            "status": run.status,
            "error_message": run.error_message,
        })
    return list(groups.values())


@router.get("/scrapes", response_class=HTMLResponse)
def scrape_log(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(ScrapeRun, SearchConfig.name)
        .join(SearchConfig, ScrapeRun.search_config_id == SearchConfig.id)
        .order_by(ScrapeRun.started_at.desc())
        .all()
    )
    groups = group_runs(rows)
    return templates.TemplateResponse(request, "scrapes.html", {"groups": groups})
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run pytest tests/dashboard/test_scrapes.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/routers/scrapes.py tests/dashboard/test_scrapes.py
git commit -m "feat: add scrapes router with group_runs helper"
```

---

## Task 2: Template

**Files:**
- Create: `dashboard/templates/scrapes.html`

- [ ] **Step 1: Create the template**

Create `dashboard/templates/scrapes.html`:

```html
{% extends "base.html" %}
{% block title %}Scrape Log{% endblock %}
{% block content %}
<h2>Scrape Log</h2>

{% if not groups %}
  <p class="text-muted">No scrape runs recorded yet.</p>
{% else %}
<div class="accordion" id="scrapeAccordion">
  {% for group in groups %}
  {% set loop_id = "config-" ~ loop.index %}
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button class="accordion-button collapsed" type="button"
              data-bs-toggle="collapse" data-bs-target="#{{ loop_id }}">
        {{ group.config_name }}
        <span class="ms-2 text-muted small">{{ group.runs | length }} run{{ 's' if group.runs | length != 1 }}</span>
        {% set last = group.runs[0] %}
        {% if last.status == "success" %}
          <span class="badge bg-success ms-2">success</span>
        {% elif last.status == "error" %}
          <span class="badge bg-danger ms-2">error</span>
        {% else %}
          <span class="badge bg-warning text-dark ms-2">{{ last.status }}</span>
        {% endif %}
      </button>
    </h2>
    <div id="{{ loop_id }}" class="accordion-collapse collapse">
      <div class="accordion-body p-0">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light">
            <tr>
              <th>Timestamp</th>
              <th>Found</th>
              <th>New</th>
              <th>Updated</th>
              <th>Removed</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {% for run in group.runs %}
            <tr>
              <td>{{ run.started_at.strftime('%Y-%m-%d %H:%M:%S') }}</td>
              <td>{{ run.listings_found }}</td>
              <td>{{ run.listings_new }}</td>
              <td>{{ run.listings_updated }}</td>
              <td>{{ run.listings_removed }}</td>
              <td>{{ run.duration ~ 's' if run.duration is not none else '—' }}</td>
              <td>
                {% if run.status == "success" %}
                  <span class="badge bg-success">success</span>
                {% elif run.status == "error" %}
                  <span class="badge bg-danger">error</span>
                {% else %}
                  <span class="badge bg-warning text-dark">{{ run.status }}</span>
                {% endif %}
              </td>
            </tr>
            {% if run.status == "error" and run.error_message %}
            <tr>
              <td colspan="7" class="text-danger small ps-3">{{ run.error_message }}</td>
            </tr>
            {% endif %}
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/templates/scrapes.html
git commit -m "feat: add scrapes.html template with Bootstrap accordion"
```

---

## Task 3: Wire up router and nav link

**Files:**
- Modify: `dashboard/main.py`
- Modify: `dashboard/templates/base.html`

- [ ] **Step 1: Register the router in main.py**

In `dashboard/main.py`, add the import and `include_router` call:

```python
import uvicorn
from fastapi import FastAPI

from dashboard.routers import listings, market, configs, scrapes

app = FastAPI(title="Reality Agent")
app.include_router(listings.router)
app.include_router(market.router)
app.include_router(configs.router)
app.include_router(scrapes.router)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("dashboard.main:app", host="0.0.0.0", port=8080, log_level="info")
```

- [ ] **Step 2: Add the nav link in base.html**

In `dashboard/templates/base.html`, add the Scrapes link to the navbar:

```html
    <div class="navbar-nav">
      <a class="nav-link" href="/">Listings</a>
      <a class="nav-link" href="/market">Market</a>
      <a class="nav-link" href="/configs">Configs</a>
      <a class="nav-link" href="/scrapes">Scrapes</a>
    </div>
```

- [ ] **Step 3: Run the full test suite**

```bash
poetry run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add dashboard/main.py dashboard/templates/base.html
git commit -m "feat: wire up scrapes page to dashboard nav"
```
