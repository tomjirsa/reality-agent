# Design: Extended Scoring Metrics & Configurable Dashboard

**Date:** 2026-05-25
**Status:** Approved

---

## Overview

Extend the listing scoring system with richer per-listing signals (property attributes, price history, market context), make weights configurable per search config in the UI, and allow column visibility to be toggled per browser. The result: the analyzer computes and stores raw signals; the dashboard computes the weighted score live from those signals using user-defined weights.

---

## Architecture

The key architectural shift is separating **signal computation** (analyzer) from **score computation** (dashboard):

- **Analyzer** computes and stores all raw signals into `listing_scores` (and new `market_snapshots`)
- **Dashboard** reads raw signals, applies per-search weights live, and renders the score
- **Alerts** are stored per `SearchConfig` as threshold rules; re-evaluated after each analyzer run and immediately when thresholds change via a new endpoint

This means adding new signals never requires changing the scoring formula stored in the DB — weights can be tuned freely in the UI without re-running the analyzer.

---

## 1. New data extracted from sreality API

The following fields are available in the existing `raw_json` / `items` array but not yet parsed into structured columns. They will be extracted in `scraper/detail.py` (`parse_detail`) and added to the `Listing` model:

| Field | Czech API key | Type | Notes |
|---|---|---|---|
| `energy_class` | `"Energetická náročnost budovy"` | `Text` | A–G string |
| `has_elevator` | `"Výtah"` | `Boolean` | "Ano" → True |
| `has_outdoor_space` | `"Balkón"`, `"Lodžie"`, `"Terasa"` | `Boolean` | True if any present |
| `has_parking` | `"Garáž"`, `"Parkovací místo"` | `Boolean` | True if any present |
| `has_cellar` | `"Sklep"` | `Boolean` | display only |
| `year_built` | `"Rok výstavby"` | `Integer` | nullable |
| `land_area_m2` | `"Plocha pozemku"` | `Integer` | houses only; nullable |

`parse_detail` will be extended to extract all of the above using the existing `extract_item_value` helper. Boolean fields parse "Ano"/"Ne". `energy_class` stores the raw letter(s).

Existing listings in the DB will have these fields as `NULL` until their detail is re-scraped. The scraper's upsert logic already handles partial updates.

---

## 2. New signals in `listing_scores`

Eight new nullable columns added to `listing_scores`. All are computed in `analyzer/signals.py` (`compute_signals`):

| Column | Type | Description |
|---|---|---|
| `condition_score` | `Float` | Numeric encoding: excellent=5, good=4, standard=3, poor=2, wreck=1, null if unknown |
| `condition_price_pct` | `Float` | Price/m² percentile recomputed within same condition bucket + district + category |
| `energy_score` | `Float` | A=5, B=4, C=3, D=2, E=1, F=0.5, G=0 |
| `floor_elevator_penalty` | `Float` | 0 for floors 1–3 or when elevator present; −5 per floor above 3 without elevator; capped at −20 |
| `building_type_score` | `Float` | brick=5, mixed=3, panel=2, wood/other=1, null if unknown |
| `drop_recency_days` | `Integer` | Days since last price drop; null if no drop ever |
| `market_delta_pct` | `Float` | `(listing_price_m2 − market_median_m2) / market_median_m2 × 100`; negative = cheaper than historical norm |
| `land_price_percentile` | `Float` | Price/m² of land vs district peers with land; null for apartments |
| `combined_area_price_pct` | `Float` | Percentile using blended area: `usable_m2 + 0.15 × land_m2`; null for apartments |

### Percentile partitioning

`condition_price_pct` partitions by `(condition_bucket, category_main_cb, category_type_cb, locality_district_id)` using SQL `PERCENT_RANK()` over active listings, same pattern as the existing percentile query in `signals.py`.

`land_price_percentile` and `combined_area_price_pct` only computed for listings where `land_area_m2 IS NOT NULL`.

### Market delta

`market_delta_pct` compares the listing's `price_per_m2` against the median `price_per_m2` from `market_snapshots` for the same `(category_main_cb, category_type_cb, locality_district_id)` bucket, looking back up to 9 months. If no snapshot exists for the bucket, the field is null.

---

## 3. Market snapshots table

New table `market_snapshots` for periodic captures of market statistics:

```
market_snapshots
  id                    Integer PK autoincrement
  snapshot_at           TIMESTAMP WITH TIME ZONE
  category_main_cb      Integer
  category_type_cb      Integer
  locality_district_id  Integer
  listing_count         Integer   -- active listings at snapshot time
  median_price_m2       Float
  avg_price_m2          Float
  p25_price_m2          Float
  p75_price_m2          Float
```

A snapshot is written at the end of each `compute_signals` run (one row per district+category bucket). The `market_snapshots` table thus builds a time series automatically. The market page in the dashboard queries this table for trend charts (see §6). The 9-month lookback window for `market_delta_pct` uses `snapshot_at >= now() − interval '9 months'` and takes the median across all snapshots in that window for each bucket.

---

## 4. Scoring weights per SearchConfig

New `scoring_weights` JSON column on `search_configs` (nullable; defaults applied in code when null):

```json
{
  "price_pct":            0.25,
  "price_m2_pct":         0.30,
  "condition_price_pct":  0.10,
  "energy_score":         0.05,
  "building_type_score":  0.05,
  "floor_elevator":       0.05,
  "drop_recency":         0.05,
  "market_delta":         0.10,
  "land_pct":             0.05
}
```

Weights sum to 1.0 by convention but the dashboard normalises them at render time so partial configs work. The `days_and_drop_signal` in the current combined score is replaced by `drop_recency_days` (inverted: fewer days since drop = higher signal).

Score formula computed in the dashboard (Python, not SQL):

```
score = Σ weight_i × normalised_signal_i
```

Each signal is normalised to 0–100 before weighting:
- Percentile signals (`price_pct`, `condition_price_pct`, `land_pct`, `combined_area_pct`): already 0–100; inverted for "lower = better" signals → `100 − pct`
- Score signals (`condition_score`, `energy_score`, `building_type_score`): scaled from their range to 0–100
- `floor_elevator_penalty`: mapped from [−20, 0] to [0, 100]
- `drop_recency_days`: inverted decay — 0 days = 100, 90+ days = 0 (linear)
- `market_delta_pct`: negative (cheaper than market) = high score; clamped to ±30%

---

## 5. Alert thresholds per SearchConfig

New `alert_thresholds` JSON column on `search_configs`:

```json
{
  "min_score": 70.0,
  "max_price_m2_percentile": 25,
  "min_condition": "standard",
  "max_drop_recency_days": 14
}
```

Alert evaluation uses the same weights stored in `scoring_weights`. Alerts fire when a listing meets **all** configured thresholds (AND logic). New endpoint:

```
POST /alerts/evaluate/{search_config_id}
```

Called immediately when thresholds are saved in the UI. The analyzer also calls this after each `compute_scores` run for all active search configs (replacing the current `send_hot_alerts` call). Email sending logic is unchanged.

---

## 6. Dashboard changes

### Score column

The listings table's `Score` column now shows the live-computed weighted score. The `combined_score` stored in `listing_scores` is kept for backward compatibility (alert history, etc.) but is no longer the primary display value.

### Configurable weights UI

A collapsible "Score weights" panel above the listings table (per search config when one is selected, global defaults otherwise). Each signal gets a range slider (0–100) with its current weight shown as a percentage. Sliders auto-normalise on change so they always sum to 100. Weights are saved to `SearchConfig.scoring_weights` via `PATCH /config/{id}/weights`. Changing weights immediately re-renders the score column (client-side re-computation in JS using the signal values embedded in the table rows as `data-` attributes).

### Column visibility

A "Columns" dropdown button (Bootstrap dropdown with checkboxes) controls which columns are shown. Visibility state stored in `localStorage` keyed by a stable column name. New columns exposed by this feature (all hideable):

- City (already added)
- Condition
- Energy class
- Floor
- Parking
- Outdoor space
- Has elevator
- Land area (shown for houses)
- Building type

### Market page — trend charts

The market page gains a time-series chart per district+category bucket using data from `market_snapshots`. Chart library: Chart.js (already a Bootstrap-friendly, lightweight option; no new heavy dependency). Shows median price/m² over the last 12 months with the current listing's price/m² overlaid as a horizontal line when drilling into a specific bucket.

---

## 7. Database migrations

Two migrations required:

**Migration 1** — new `Listing` columns (nullable, no default needed):
`energy_class`, `has_elevator`, `has_outdoor_space`, `has_parking`, `has_cellar`, `year_built`, `land_area_m2`

**Migration 2** — new `listing_scores` columns + new `market_snapshots` table + new `search_configs` columns:
- `listing_scores`: 9 new nullable float/int columns
- `market_snapshots`: new table (schema above)
- `search_configs`: `scoring_weights` JSON (nullable), `alert_thresholds` JSON (nullable)

---

## 8. Testing

- `tests/analyzer/test_signals.py`: extend with tests for each new signal computation; use existing fixture pattern with in-memory SQLite
- `tests/analyzer/test_scoring.py`: test normalisation of each signal type and the weighted sum
- `tests/scraper/test_detail.py`: extend `parse_detail` tests for each new extracted field
- `tests/dashboard/test_listings.py`: test that score is computed correctly from signal data attributes; test weight normalisation
- Market snapshot creation tested in a new `tests/analyzer/test_snapshots.py`

---

## Out of scope

- Machine learning / regression-based price prediction
- External data sources (transport APIs, school proximity)
- Per-user auth or multi-user weight profiles
- Mobile layout for the weights panel
