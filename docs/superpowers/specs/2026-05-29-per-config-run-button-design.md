# Per-Config "Run Now" Button — Design Spec

**Date:** 2026-05-29

## Summary

Add a per-config "Run now" button to the scrapes page so users can trigger a scrape for a single search config rather than always running all configs at once. The existing "Run all" button at the top is retained.

## Architecture

Three files change; no new files, no schema changes.

### 1. `scraper/main.py`

`run_pipeline` gains an optional `config_id: int | None = None` parameter.

- When `None` (default): existing behaviour — queries all active configs and scrapes each.
- When set: queries only the single active config with that ID. If the config is not found or inactive, logs a warning and returns without error.

The `POST /run` FastAPI endpoint accepts an optional `config_id` query parameter and passes it to the background task:

```
POST /run            → run_pipeline()           # all active configs
POST /run?config_id=3 → run_pipeline(config_id=3) # single config
```

The `_scrape_lock` is shared — a per-config run blocks and is blocked by any concurrent full-pipeline run.

Enrichment (`enrich_all_configs`) and the downstream analyzer trigger still fire after a single-config run, same as a full run.

### 2. `dashboard/routers/scrapes.py`

- The DB query also selects `SearchConfig.id` alongside `SearchConfig.name`.
- `group_runs` includes `config_id` in each group dict.
- The no-runs fallback loop already has `.id` from the `SearchConfig` ORM object; it sets `config_id` there too.
- New endpoint: `POST /scrapes/run/{config_id}` — calls `POST {scraper_url}/run?config_id={config_id}`, then redirects to `/scrapes?triggered=1`.
- Existing `POST /scrapes/run` is unchanged.

### 3. `dashboard/templates/scrapes.html`

Each accordion header gets a small right-aligned "Run" form button:

```
[Config Name]  N runs  [badge]          [Run ▶]
```

The button is a `<form method="post" action="/scrapes/run/{{ group.config_id }}">` with a `btn-sm` submit button, positioned with `ms-auto` inside the existing flex header. It stops propagation so clicking it doesn't toggle the accordion panel.

The top-level "Run all" button stays unchanged.

## Error Handling

- If the scraper is unreachable during a per-config trigger, the exception is swallowed (same as existing "Run all" behaviour) and the user is redirected back with the triggered banner.
- If `config_id` refers to an inactive or missing config, `run_pipeline` logs a warning and exits cleanly.

## Testing

- Unit test: `run_pipeline(config_id=X)` only scrapes the matching config.
- Unit test: `run_pipeline(config_id=X)` with unknown/inactive config logs warning and does nothing.
- Dashboard route test: `POST /scrapes/run/{config_id}` calls scraper with correct query param.
