# Reality Agent — Design Spec
_Date: 2026-05-15_

## Overview

A self-hosted real-estate monitoring application that scrapes listings from sreality.cz, stores them in a Postgres database, computes bargain-identification statistics, and surfaces results via a local web dashboard with email notifications. Runs entirely on a Synology NAS using Docker Compose.

---

## Architecture

Four Docker services in a single `docker-compose.yml`:

```
┌─────────────────────────────────────────────────────────┐
│  Synology NAS — Docker Compose                          │
│                                                         │
│  ┌──────────┐  raw       ┌──────────────────────────┐  │
│  │ scraper  │ ─────────► │        postgres          │  │
│  │ (cron)   │  listings  │                          │  │
│  └──────────┘            │  • listings (raw)        │  │
│                          │  • price history         │  │
│  ┌──────────┐  reads  ◄──│  • scores & stats        │  │
│  │ analyzer │            └──────────────────────────┘  │
│  │ (cron)   │  writes ──►            │                  │
│  └────┬─────┘                        │ reads            │
│       │ email alerts                 ▼                  │
│       ▼                 ┌──────────────────────────┐   │
│  ┌──────────┐           │   dashboard              │   │
│  │  SMTP    │           │   (FastAPI + Jinja2)     │   │
│  └──────────┘           │   port 8080              │   │
│                         └──────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Services:**
- `db` — Postgres 16, persistent volume
- `scraper` — Python, runs on schedule (default: every 6h), fetches listings from sreality.cz API
- `analyzer` — Python, runs on the same schedule as the scraper with a fixed offset (e.g. scraper at :00, analyzer at :30), computes scores and sends alerts. Can also be triggered manually via a dashboard button.
- `dashboard` — Python FastAPI + Jinja2, always-on, port 8080

**Shared code:** `scraper`, `analyzer`, and `dashboard` build from the same base image containing shared `models.py` and DB session layer.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| HTTP client | httpx |
| Scheduling | APScheduler |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Web framework | FastAPI + Jinja2 |
| Charts | Chart.js (CDN) |
| Database | Postgres 16 |
| Containerisation | Docker Compose |

---

## Directory Structure

```
reality-agent/
├── docker-compose.yml
├── .env                    ← credentials and config (not committed)
├── .env.example
├── shared/
│   ├── models.py           ← SQLAlchemy models
│   ├── db.py               ← session factory
│   └── config.py           ← settings from env vars
├── scraper/
│   ├── Dockerfile
│   ├── main.py             ← scheduler entrypoint
│   ├── search.py           ← Phase 1: search sweep
│   └── detail.py           ← Phase 2: selective detail fetch
├── analyzer/
│   ├── Dockerfile
│   ├── main.py             ← analyzer entrypoint
│   ├── signals.py          ← per-signal computation
│   ├── scoring.py          ← combined score
│   └── alerts.py           ← email notification logic
├── dashboard/
│   ├── Dockerfile
│   ├── main.py             ← FastAPI app
│   ├── routers/
│   │   ├── listings.py
│   │   ├── market.py
│   │   └── configs.py
│   └── templates/
│       ├── base.html
│       ├── listings.html
│       ├── detail.html
│       ├── market.html
│       └── configs.html
└── migrations/
    └── versions/
```

---

## Data Model

### `search_configs`
Configuration for each scrape job. One row per search (e.g. "Praha apartments for sale").

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| name | text | Human label |
| category_main_cb | int | 1=byty, 2=domy |
| category_type_cb | int | 1=prodej, 2=pronájem |
| category_sub_cb | text | Pipe-separated layout codes (e.g. "4\|5\|6") |
| locality_region_id | int | nullable |
| locality_district_id | int | nullable |
| czk_price_min | int | nullable |
| czk_price_max | int | nullable |
| usable_area_min | int | nullable |
| usable_area_max | int | nullable |
| ownership | int | nullable (1=osobní, 2=družstevní) |
| no_auction | bool | default true |
| active | bool | default true |
| created_at | timestamptz | |

### `listings`
One row per unique property. Upserted on each scrape.

| Column | Type | Notes |
|--------|------|-------|
| hash_id | bigint PK | sreality.cz unique ID |
| name | text | |
| price_czk | int | Current price |
| area_m2 | int | Usable area |
| price_per_m2 | float | Computed: price_czk / area_m2 |
| locality | text | Human-readable address |
| locality_district_id | int | For peer grouping |
| locality_region_id | int | |
| floor | text | nullable |
| building_type | text | e.g. Cihlová, Panelová |
| ownership | text | |
| condition | text | |
| category_main_cb | int | |
| category_type_cb | int | |
| is_active | bool | false when removed from search results |
| is_new_flag | bool | `new` field from API |
| first_seen_at | timestamptz | Set on first insert |
| last_seen_at | timestamptz | Updated every scrape it appears |
| removed_at | timestamptz | nullable, set when is_active flips false |
| days_to_sell | int | nullable, computed when removed_at is set |
| raw_json | jsonb | Full API detail response |

### `listing_price_history`
Append-only. One row recorded whenever a price change is detected.

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| hash_id | bigint FK | → listings |
| price_czk | int | |
| price_per_m2 | int | |
| recorded_at | timestamptz | |

### `listing_scores`
Written by the analyzer. One row per listing, overwritten on each analysis run.

| Column | Type | Notes |
|--------|------|-------|
| hash_id | bigint FK PK | → listings |
| price_percentile | float | Percentile rank within peer group (lower = cheaper) |
| price_per_m2_percentile | float | Percentile rank within peer group |
| days_on_market | int | today - first_seen_at |
| had_price_drop | bool | |
| price_drop_pct | float | nullable, total % drop from first recorded price |
| is_hot | bool | new (< HOT_OFFER_MAX_DAYS) + low price_per_m2_percentile |
| combined_score | float | 0–100, higher = better bargain |
| alerted_at | timestamptz | nullable, last time a hot-offer alert was sent |
| computed_at | timestamptz | |

### `scrape_runs`
Audit log for each scrape execution.

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| search_config_id | int FK | → search_configs |
| started_at | timestamptz | |
| finished_at | timestamptz | nullable |
| listings_found | int | |
| listings_new | int | |
| listings_updated | int | Price-changed detail re-fetches |
| listings_removed | int | Flipped to is_active=false |
| status | text | 'running', 'success', 'error' |
| error_message | text | nullable |

---

## Scraper — Two-Phase Strategy

**Phase 1 — Search sweep (always runs)**
- Paginate through all search result pages for each active `search_config`
- Each page returns lightweight listing data: `hash_id`, `price`, `locality`, `name`, basic flags
- Record all seen `hash_ids` for this run

**Phase 2 — Selective detail fetch**
For each listing from Phase 1:
- `hash_id` not in DB → fetch full detail, insert new listing
- `hash_id` in DB + price changed → fetch full detail, update listing, append to `listing_price_history`
- `hash_id` in DB + price unchanged → skip detail call; update `last_seen_at` only

**Removal detection**
Any `hash_id` that was `is_active=true` before the run but absent from Phase 1 results → set `is_active=false`, stamp `removed_at`, compute `days_to_sell`.

This ensures detail API calls are only made for new or changed listings.

---

## Analyzer — Bargain Scoring

Runs after each scraper run (or triggered manually from the dashboard).

**Peer group definition:** listings sharing the same `(category_main_cb, category_type_cb, locality_district_id)` that are currently `is_active=true`.

**Signal 1 — Price percentile rank**
Rank of this listing's `price_czk` within its peer group. A listing at the 10th percentile is cheaper than 90% of peers.

**Signal 2 — Price/m² percentile rank**
Same as Signal 1 but on `price_per_m2`. Primary bargain signal.

**Signal 3 — Days on market + price drop**
Normalised 0–100 score: `days_on_market` capped at 180 days (180+ = 100), plus a bonus of up to 30 points for `price_drop_pct` (capped at 20% drop = full bonus). Combined and re-normalised to 0–100.

**Hot offer flag**
Set when: `days_on_market < HOT_OFFER_MAX_DAYS` (default: 7) AND `price_per_m2_percentile < 25`.

**Combined score (0–100)**
```
combined_score =
    0.35 × (100 - price_percentile)
  + 0.40 × (100 - price_per_m2_percentile)
  + 0.25 × days_and_drop_signal
```
Weights are configurable constants. All signals normalised 0–100 before weighting.

**Future enhancement (not in scope now):** Correlate bargain indicators with quick-sale listings to identify which signals best predict fast sales, and analyse property characteristics of quickly-sold listings.

---

## Email Notifications

**Hot offer alert**
Triggered immediately post-analysis for listings where:
- `is_hot = true` AND `combined_score ≥ BARGAIN_SCORE_THRESHOLD` (default: 70)
- `alerted_at` is null or listing had a further price drop since last alert

Email contains: name, price, price/m², percentile ranks, district, direct sreality.cz link.

**Daily digest**
One email per day summarising:
- New listings added in last 24h
- Listings with price drops
- Top 10 bargains by combined score

**Delivery:** SMTP. Credentials in `.env`. Compatible with Gmail, Seznam, or any SMTP relay.

---

## Web Dashboard

**Listings feed (default view)**
Paginated cards/table of active listings sorted by `combined_score` descending. Filters: category, district, price range, min score, hot-only toggle. Each row shows: name, price, price/m², percentile ranks, days on market, price drop badge, hot flag, combined score. Links through to sreality.cz.

**Listing detail**
Full stats for a single listing: price history chart (Chart.js), all scraped fields, per-signal score breakdown.

**Market overview**
Per district/category summary: price/m² distribution chart, median days-to-sell from closed ads, active listing count.

**Search configs**
Admin page to add, edit, and disable search configs. No separate admin tool.

---

## Configuration (`.env`)

```
POSTGRES_URL=postgresql://user:pass@db:5432/reality

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=...
ALERT_EMAIL=you@gmail.com

SCRAPE_INTERVAL_HOURS=6
BARGAIN_SCORE_THRESHOLD=70
HOT_OFFER_MAX_DAYS=7
```

---

## Deployment on Synology NAS

1. Upload project folder via File Station (or SCP)
2. Copy `.env.example` → `.env`, fill in credentials
3. Open **Container Manager → Project → Create**, point at the project folder
4. Container Manager runs `docker compose up -d`

Dashboard accessible at `http://<nas-ip>:8080` from any device on the home network.

---

## Out of Scope (this iteration)

- Authentication on the dashboard
- Mobile-optimised UI
- Public internet access (no reverse proxy / DDNS)
- Quick-sale correlation analysis (planned future enhancement)
- GitHub Actions / cloud deployment
