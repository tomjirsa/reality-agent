# Travel Distance Enrichment — Design Spec

**Date:** 2026-05-21
**Branch:** `distance`

## Overview

Add travel distance and duration from each listing to a user-defined destination, computed via the mapy.cz Routing API. Distance is stored as a per-listing, per-search-config enrichment field — not used for filtering at scrape time, but available for display, ordering, and filtering in the dashboard, and as an input to future score computation.

## Data Model

### `SearchConfig` — 4 new columns

| column | type | notes |
|---|---|---|
| `destination_label` | text, nullable | human-readable address entered by user |
| `destination_lat` | float, nullable | resolved by mapy.cz Geocode API on config save |
| `destination_lon` | float, nullable | resolved by mapy.cz Geocode API on config save |
| `travel_mode` | text, nullable | one of: `car`, `walk`, `bike`, `transit` |

If `destination_lat`/`destination_lon` are null, enrichment is skipped for that config.

### New table: `listing_search_configs`

Records which listings were found by which search config (many-to-many, populated at scrape time).

| column | type |
|---|---|
| `hash_id` | bigint, FK → listings |
| `search_config_id` | int, FK → search_configs |

Primary key: `(hash_id, search_config_id)`.

### New table: `listing_distances`

Stores computed travel distances, keyed per listing × search config.

| column | type | notes |
|---|---|---|
| `hash_id` | bigint, FK → listings | |
| `search_config_id` | int, FK → search_configs | |
| `travel_mode` | text | mode used at computation time |
| `distance_m` | integer | meters |
| `duration_s` | integer | seconds |
| `computed_at` | timestamptz | |

Primary key: `(hash_id, search_config_id)`.

## Architecture

### Pipeline (scraper-orchestrated)

```
scrape_all_configs()  →  enrich_all_configs()  →  POST analyzer/run
```

The scraper's `BlockingScheduler` drives the full cycle. The analyzer retains its own HTTP endpoint and schedule as an independent fallback.

### New `enricher/` package

Single public function: `enrich_all_configs(db: Session) -> None`

For each active `SearchConfig` with destination set:
1. Query `listing_search_configs` for listings linked to this config that have no `listing_distances` row yet — enrichment is incremental and idempotent.
2. Extract GPS coordinates from `raw_json` (`map.lat`, `map.lon` from sreality.cz detail response).
3. Call mapy.cz Routing API.
4. Upsert result into `listing_distances`.

A short inter-request delay (same pattern as `scraper/detail.py`'s `DETAIL_DELAY`) is applied between calls.

### mapy.cz Routing API

```
GET https://api.mapy.cz/v1/routing/route
  ?apikey={MAPY_API_KEY}
  &lang=cs
  &routeType={routeType}
  &start={listing_lon},{listing_lat}
  &end={destination_lon},{destination_lat}
```

Travel mode mapping:

| config value | routeType |
|---|---|
| `car` | `car_fast_traffic` |
| `walk` | `foot_fast` |
| `bike` | `bike_road` |
| `transit` | `public_transport` |

Response fields used: `routeSummary.distance` (→ `distance_m`), `routeSummary.duration` (→ `duration_s`).

### mapy.cz Geocode API (used at config save time)

```
GET https://api.mapy.cz/v1/geocode
  ?apikey={MAPY_API_KEY}
  &query={address}
  &lang=cs
```

Called by the dashboard when a new config is saved with a destination address. Resolved lat/lon is stored; `destination_label` retains the original user-entered string.

### Config change

Add `mapy_api_key: str = ""` to `shared/config.py` (read from `.env`). Enrichment and geocoding are skipped if the key is empty.

## Scraper changes

`scraper/main.py` `upsert_listings()` records the `(hash_id, search_config_id)` pair into `listing_search_configs` for every listing upserted.

After `scrape_all_configs()` completes, `enrich_all_configs(db)` is called, then `POST {analyzer_url}/run`.

## Dashboard changes

### Config form (`/configs`)

- New fields: "Destination address" (text) + "Travel mode" (dropdown: car / walk / bike / transit).
- On POST, if address is provided: geocode via mapy.cz, store lat/lon + label. If geocoding fails, return HTTP 422 with a user-visible error message.
- Config list displays `destination_label` and `travel_mode` per config.

### Listings feed (`/`)

- New "Search config" filter dropdown (default: all configs).
- When a specific config is selected, `distance_m` and `duration_s` columns appear in the listing table (hidden when showing all, since distances are config-specific).
- Ordering by distance is available when a config filter is active.
- All existing filters (price, score, hot_only, district, category) remain operative alongside the config filter.

### Listing detail page (`/listing/{hash_id}`)

- "Travel distances" section lists each config the listing belongs to that has a computed distance: config name, travel mode, distance (km), duration (min).

## Error Handling

| scenario | behaviour |
|---|---|
| mapy.cz routing timeout | log warning with `hash_id` and exception type; skip listing; retry next cycle |
| mapy.cz routing 4xx | log warning with `hash_id` and HTTP status code; skip listing |
| mapy.cz routing 5xx | log warning with `hash_id` and HTTP status code; skip listing |
| listing has no GPS in `raw_json` | log warning with `hash_id`; skip listing |
| geocoding fails on config save | return 422 with user-visible message; do not save config |
| analyzer call fails after enrichment | log error; scraper cycle still completes normally |

## Testing

- Unit tests for `enricher/` mock the mapy.cz HTTP calls.
- Unit tests for geocoding path in the configs router mock the mapy.cz Geocode API.
- Integration tests use the real DB (no DB mocking, per project convention).
- Existing analyzer and scraper tests unaffected.

## Migration

New Alembic migration adds:
1. Four columns to `search_configs`: `destination_label`, `destination_lat`, `destination_lon`, `travel_mode`.
2. New table `listing_search_configs`.
3. New table `listing_distances`.
