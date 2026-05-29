# Scrape Progress Indicator

**Date:** 2026-05-29
**Status:** Approved

## Goal

Show live progress on the Scrape Log page while a scrape is running: a progress bar and "X / Y listings processed" counter, updating via auto-refresh.

## Schema

Add two nullable integer columns to `scrape_runs`:

| Column | Type | Nullable | Description |
|---|---|---|---|
| `progress_total` | Integer | yes | Total listings found by search; set once after `search_all()` returns |
| `progress_done` | Integer | yes | Count of listings processed so far; incremented per listing |

Null means the run has just started and search results haven't arrived yet. Existing rows are unaffected.

Requires a new Alembic migration.

## Scraper (`scraper/main.py`)

Two additions to `run_scrape`:

1. **After `search_all()` returns:** set `run.progress_total = len(raw_estates)` and commit.
2. **Per-listing loop:** before each existing `db.commit()` (both the `upsert_listings` path and the `last_seen_at`-only path), increment `run.progress_done = (run.progress_done or 0) + 1`. No extra commits — piggybacks on existing ones.

`finish_scrape_run` is unchanged. The `progress_*` columns are only meaningful while `status == "running"`.

## Dashboard

### Router (`dashboard/routers/scrapes.py`)

Pass the active running run to the template:

```python
running_run = (
    db.query(ScrapeRun)
    .filter_by(status="running")
    .order_by(ScrapeRun.started_at.desc())
    .first()
)
```

Include in template context: `running_run` (the ORM object or None), `now` (already present).

### Template (`dashboard/templates/scrapes.html`)

**Auto-refresh:** inject `<meta http-equiv="refresh" content="5">` inside `{% block %}` only when `running_run` is not None. This prevents finished pages from refreshing indefinitely.

**Progress banner:** render above the accordion when `running_run` is not None:

- If `running_run.progress_total` is None: show a spinner and "Starting…"
- Otherwise: show "Scraping… X / Y listings" and a Bootstrap progress bar (`progress_done / progress_total * 100%`), plus elapsed seconds (`(now - running_run.started_at).seconds`).

The accordion history below remains unchanged.

## Out of scope

- JS polling / SSE (auto-refresh is sufficient)
- Per-config progress (single global running indicator is enough)
- Persisting progress columns after the run ends (they're left as-is; the final stats columns are the authoritative record)
