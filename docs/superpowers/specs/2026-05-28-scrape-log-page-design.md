# Scrape Log Page — Design Spec

**Date:** 2026-05-28

## Overview

Add a `/scrapes` page to the dashboard that displays scrape run history grouped by search config, using Bootstrap collapsible cards. No new models or migrations are needed — `ScrapeRun` already captures all required fields.

## Files Touched

| File | Change |
|---|---|
| `dashboard/routers/scrapes.py` | New — single `GET /scrapes` route |
| `dashboard/templates/scrapes.html` | New — Bootstrap collapse cards |
| `dashboard/main.py` | Register `scrapes` router |
| `dashboard/templates/base.html` | Add "Scrapes" nav link |

## Route

```
GET /scrapes
```

Queries all `ScrapeRun` rows joined with `SearchConfig.name`, ordered by `started_at DESC`. Groups by config name in Python. Passes `groups: list[{config_name, runs[]}]` to the template.

## Template Layout

One Bootstrap card per config. Cards are collapsed by default.

**Card header** shows:
- Config name
- Total run count
- Status badge of the most recent run

**Card body** — a table with columns:

| Timestamp | Found | New | Updated | Removed | Duration | Status |
|---|---|---|---|---|---|---|

- **Timestamp**: `started_at` formatted as local datetime
- **Duration**: `finished_at - started_at` in seconds; `—` if still running
- **Status**: Bootstrap badge — `success` (green), `error` (red), `running` (yellow)
- **Error row**: if status is `error`, a small red text row beneath shows `error_message`

## Data Model (existing)

`ScrapeRun` fields used:
- `search_config_id` → joined to `SearchConfig.name`
- `started_at`, `finished_at`
- `listings_found`, `listings_new`, `listings_updated`, `listings_removed`
- `status`, `error_message`

## Out of Scope

- Pagination (run count is bounded)
- Delete / clear history
- Auto-refresh
