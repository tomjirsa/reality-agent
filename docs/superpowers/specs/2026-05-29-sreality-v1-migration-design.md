# Sreality v1 API Migration — Design Spec
_Date: 2026-05-29_

## Context

Sreality removed their v2 API (`/api/cs/v2/estates`) in May 2026. All calls now return 404. The replacement is a v1 API (`/api/v1/estates/search`) gated behind Seznam SSO authentication. The scraper is currently broken and must be migrated.

See also: [ADR 001](../../adr/001-scraper-http-client.md) — decision to replace Playwright with plain httpx.

---

## Architecture

The change is contained entirely within the scraper layer. The DB models, migrations, analyzer, dashboard, enricher, and Docker Compose are untouched.

**Files changed:**

| File | Change |
|---|---|
| `scraper/browser.py` | Replace Playwright with httpx; add `_login()` auth helper |
| `scraper/search.py` | New endpoint URL, `limit`/`offset` pagination, v1 response shape |
| `scraper/detail.py` | Unwrap `result` key, direct field access replacing `items[]` parsing |
| `shared/config.py` | Add `sreality_username`, `sreality_password` settings |
| `.env.example` | Add `SREALITY_USERNAME`, `SREALITY_PASSWORD` placeholders |
| `scraper/requirements.txt` | Remove `playwright==1.44.0` |
| `tests/scraper/test_*.py` | Update fixture data to v1 response shape |

---

## Auth & Session

`browser_client()` keeps its existing context manager signature — callers are unchanged.

Internally it becomes a thin httpx session factory:

```python
@contextmanager
def browser_client():
    with httpx.Client() as client:
        _login(client)
        yield client
```

`_login(client)` performs three calls in order:

```
GET  https://login.szn.cz/?service=sreality&return_url=https://www.sreality.cz/
     → acquires regbrowserident2 + initial lps cookies

POST https://login.szn.cz/api/v1/login
     Content-Type: application/json
     body: {username, password, service: "sreality", rememberMe: true}
     → authenticates; raises on non-200

GET  https://login.szn.cz/api/v1/autologin?service=sreality&return_url=https://www.sreality.cz/
     Referer: https://www.sreality.cz/
     → transfers session cookies to .sreality.cz domain
```

Credentials come from `settings.sreality_username` and `settings.sreality_password` (env vars `SREALITY_USERNAME`, `SREALITY_PASSWORD`).

The `httpx.Client` cookie jar persists for the lifetime of one scrape run, then is discarded. No cookie persistence to disk — re-login on every run takes ~1 second and avoids stale session edge cases.

On login failure (wrong credentials, network error, non-200 response), `_login()` raises immediately. The existing `except Exception` handler in `run_scrape()` catches it and writes the error to `scrape_runs.error_message`.

---

## API Migration

### search.py

**Endpoint:** `https://www.sreality.cz/api/v1/estates/search`

**Pagination params:**

| Old | New |
|---|---|
| `per_page` | `limit` |
| `from` | `offset` |

**Response parsing:**

```python
data     = resp.json()
estates  = data["results"]           # was data["_embedded"]["estates"]
total    = data["pagination"]["total"] # was data["result_size"]
```

Each estate in `results` carries `hash_id`, `price_czk`, and `locality` — sufficient for the Phase 1 price-change check in `main.py`. No changes to `main.py`.

### detail.py

**Endpoint:** unchanged — `https://www.sreality.cz/api/v1/estates/{hash_id}`

**Response unwrap:**

```python
data = resp.json()["result"]   # v1 wraps in a "result" key
```

**Field mapping** — the `items[]` array with Czech text keys is replaced by named fields:

| DB field | Old (`items[]`) | New (direct) |
|---|---|---|
| `area_m2` | `extract_item_value(items, "Užitná plocha")` → `_parse_area` | `data["usable_area"]` (int) |
| `floor` | `extract_item_value(items, "Podlaží")` | `data["floor_number"]` (int) |
| `building_type` | `extract_item_value(items, "Stavba")` | `data["building_type"]["name"]` |
| `condition` | `extract_item_value(items, "Stav objektu")` | `data["building_condition"]["name"]` |
| `ownership` | `extract_item_value(items, "Vlastnictví")` | `data["ownership"]["name"]` |
| `has_elevator` | `_parse_bool(items["Výtah"])` | `data["elevator"] is not None and data["elevator"].get("value") == 1` |
| `energy_class` | `extract_item_value(items, "Energetická náročnost budovy")` | `data["energy_efficiency_rating_cb"]["name"]` |
| `has_outdoor_space` | Balkón / Lodžie / Terasa present in items | `data["balcony"] or data["loggia"] or data["terrace"]` (booleans) |
| `has_parking` | Garáž / Parkovací místo present in items | `data["garage"] or data["parking_lots"]` (booleans) |
| `has_cellar` | `_parse_bool(items["Sklep"])` | `data["cellar"]` (bool) |
| `year_built` | `_parse_area(items["Rok výstavby"])` | `data["object_age"]` (int or null) |
| `land_area_m2` | `_parse_area(items["Plocha pozemku"])` | `data["building_area"]` (int or null) |
| `locality` (string) | `locality_obj.get("value")` | `", ".join(filter(None, [street, citypart, city]))` |
| `locality_district_id` | `data["locality_district_id"]` | `data["locality"]["district_id"]` |
| `locality_region_id` | `data["locality_region_id"]` | `data["locality"]["region_id"]` |
| `price_czk` | `data["price_czk"]["value_raw"]` | `data["price_czk"]` (float) |
| `price_per_m2` | computed: `price / area` | computed: `price / area` (unchanged; `price_czk_m2` exists but keep consistent source) |
| `is_new_flag` | `bool(data.get("is_new", False))` | `bool(data.get("is_new_flag", False))` (verify field name; fall back to False) |

Helpers `extract_item_value`, `_parse_area`, and `_parse_bool` are removed from `detail.py` as they are no longer needed.

---

## Error Handling

No new error cases. Existing paths cover everything:

- Login failure → `_login()` raises → caught by `run_scrape` → written to `scrape_runs.error_message`
- Missing `result` key in detail response → `KeyError` → same catch path
- 404/410 on detail → existing `return None` (listing gone, skip)
- 429/503 on detail → existing retry loop with `[5, 15, 30]` second delays
- Search returns empty results → existing guard in `main.py` skips `detect_removals`

---

## Testing

Existing test files (`test_search.py`, `test_detail.py`) mock the HTTP client. The only change is updating fixture data from v2 to v1 response shape:

- `test_search.py` fixtures: wrap results in `{"pagination": {"total": N}, "results": [...]}`
- `test_detail.py` fixtures: wrap estate data in `{"result": {...}}`; use named fields instead of `items[]`

New test: `test_browser.py` — unit test for `_login()`:
- Asserts three calls happen in order with correct URLs
- Asserts a non-200 login response raises an exception
- Asserts cookies are carried from call 1 into calls 2 and 3
