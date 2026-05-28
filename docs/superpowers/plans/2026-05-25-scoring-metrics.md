# Scoring Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend listing scoring with property attribute signals (condition, energy class, floor/elevator, building type), price history recency, market trend context, and land-area metrics for houses — all configurable via per-search weight sliders in the dashboard.

**Architecture:** The analyzer computes and stores raw signals in `listing_scores`; the dashboard computes the weighted score live in Python using per-`SearchConfig` weights. A new `market_snapshots` table records periodic market statistics, feeding both trend charts on the market page and a historical-delta signal per listing. Column visibility in the listings table is stored in `localStorage` (no backend).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Jinja2, Bootstrap 5, vanilla JS, Chart.js (CDN)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `shared/models.py` | Modify | New fields on `Listing`, `ListingScore`, `SearchConfig`; new `MarketSnapshot` model |
| `migrations/versions/0002_listing_attributes.py` | Create | Adds 7 new columns to `listings` |
| `migrations/versions/0003_signals_snapshots_weights.py` | Create | Adds 9 signal columns to `listing_scores`, `market_snapshots` table, 2 JSON columns to `search_configs` |
| `scraper/detail.py` | Modify | Extract new fields from sreality items array |
| `tests/scraper/test_detail.py` | Modify | Tests for new extracted fields |
| `analyzer/signals.py` | Modify | Compute all new signals in `compute_signals` |
| `tests/analyzer/test_signals.py` | Modify | Tests for each new signal |
| `analyzer/snapshots.py` | Create | `create_market_snapshot` function |
| `tests/analyzer/test_snapshots.py` | Create | Snapshot creation tests |
| `analyzer/main.py` | Modify | Wire in `create_market_snapshot`; add `POST /alerts/evaluate/{id}` |
| `dashboard/scoring.py` | Create | `compute_live_score`, `_normalise`, `DEFAULT_WEIGHTS` |
| `tests/dashboard/test_scoring.py` | Create | Live score computation tests |
| `dashboard/routers/listings.py` | Modify | Use `compute_live_score`; inject signal data attrs; `PATCH /config/{id}/weights` |
| `dashboard/routers/market.py` | Modify | Add `GET /market/snapshots` JSON endpoint for chart data |
| `dashboard/templates/listings.html` | Modify | New columns, column-visibility dropdown, weights panel |
| `dashboard/templates/market.html` | Modify | Trend chart per bucket using Chart.js |

---

## Phase 1 — Data Foundation

### Task 1: Add new Listing fields to model and Migration 1

**Files:**
- Modify: `shared/models.py`
- Create: `migrations/versions/0002_listing_attributes.py`

- [ ] **Step 1: Add fields to the `Listing` model**

In `shared/models.py`, after `is_new_flag` (line 54), add:

```python
    energy_class: Mapped[Optional[str]] = mapped_column(Text)
    has_elevator: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_outdoor_space: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_parking: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_cellar: Mapped[Optional[bool]] = mapped_column(Boolean)
    year_built: Mapped[Optional[int]] = mapped_column(Integer)
    land_area_m2: Mapped[Optional[int]] = mapped_column(Integer)
```

- [ ] **Step 2: Write the migration file**

Create `migrations/versions/0002_listing_attributes.py`:

```python
"""add listing attribute columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("energy_class", sa.Text(), nullable=True))
    op.add_column("listings", sa.Column("has_elevator", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_outdoor_space", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_parking", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("has_cellar", sa.Boolean(), nullable=True))
    op.add_column("listings", sa.Column("year_built", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("land_area_m2", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ["land_area_m2", "year_built", "has_cellar", "has_parking",
                "has_outdoor_space", "has_elevator", "energy_class"]:
        op.drop_column("listings", col)
```

- [ ] **Step 3: Run existing tests to confirm model change is backward-compatible**

```bash
poetry run pytest tests/shared/ tests/scraper/ -v
```

Expected: all pass (new fields are nullable, no existing tests break).

- [ ] **Step 4: Commit**

```bash
git add shared/models.py migrations/versions/0002_listing_attributes.py
git commit -m "feat: add listing attribute columns to model and migration"
```

---

### Task 2: Extend scraper to extract new fields

**Files:**
- Modify: `scraper/detail.py`
- Modify: `tests/scraper/test_detail.py`

- [ ] **Step 1: Write failing tests for new extracted fields**

Add to `tests/scraper/test_detail.py`:

```python
FULL_DETAIL_RESPONSE = {
    "name": "Prodej bytu 3+kk, 80 m²",
    "price_czk": {"value_raw": 5_900_000, "name": "Celková cena", "value": "5 900 000", "unit": ""},
    "is_new": False,
    "locality": {"name": "Adresa", "value": "Praha 2 - Vinohrady, Blanická", "accuracy": "address"},
    "locality_district_id": 5007,
    "items": [
        {"name": "Užitná ploch", "value": "80"},
        {"name": "Podlaží", "value": "5. podlaží z 7"},
        {"name": "Stavba", "value": "Cihlová"},
        {"name": "Stav objektu", "value": "Velmi dobrý"},
        {"name": "Vlastnictví", "value": "Osobní"},
        {"name": "Energetická náročnost budovy", "value": "B"},
        {"name": "Výtah", "value": "Ano"},
        {"name": "Balkón", "value": "8 m²"},
        {"name": "Garáž", "value": "Ano"},
        {"name": "Sklep", "value": "Ano"},
        {"name": "Rok výstavby", "value": "1998"},
    ],
}

HOUSE_DETAIL_RESPONSE = {
    "name": "Prodej rodinného domu 180 m²",
    "price_czk": {"value_raw": 8_500_000, "name": "Celková cena", "value": "8 500 000", "unit": ""},
    "is_new": False,
    "locality": {"name": "Adresa", "value": "Brno - Líšeň", "accuracy": "address"},
    "locality_district_id": 6202,
    "items": [
        {"name": "Užitná ploch", "value": "180"},
        {"name": "Stavba", "value": "Cihlová"},
        {"name": "Stav objektu", "value": "Dobrý"},
        {"name": "Vlastnictví", "value": "Osobní"},
        {"name": "Plocha pozemku", "value": "650"},
    ],
}


def test_parse_detail_extracts_energy_class():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["energy_class"] == "B"


def test_parse_detail_extracts_elevator_true():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["has_elevator"] is True


def test_parse_detail_extracts_outdoor_space_from_balcony():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["has_outdoor_space"] is True


def test_parse_detail_extracts_parking():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["has_parking"] is True


def test_parse_detail_extracts_cellar():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["has_cellar"] is True


def test_parse_detail_extracts_year_built():
    result = parse_detail(FULL_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["year_built"] == 1998


def test_parse_detail_extracts_land_area():
    result = parse_detail(HOUSE_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["land_area_m2"] == 650


def test_parse_detail_new_fields_none_when_absent():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["energy_class"] is None
    assert result["has_elevator"] is None
    assert result["has_outdoor_space"] is None
    assert result["has_parking"] is None
    assert result["has_cellar"] is None
    assert result["year_built"] is None
    assert result["land_area_m2"] is None


def test_parse_detail_outdoor_space_from_loggia():
    response = dict(FULL_DETAIL_RESPONSE)
    response["items"] = [{"name": "Lodžie", "value": "5 m²"}]
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["has_outdoor_space"] is True


def test_parse_detail_elevator_false_when_ne():
    response = dict(FULL_DETAIL_RESPONSE)
    response["items"] = [{"name": "Výtah", "value": "Ne"}]
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["has_elevator"] is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run pytest tests/scraper/test_detail.py::test_parse_detail_extracts_energy_class -v
```

Expected: `FAILED` — `KeyError` or `AssertionError` because new keys not yet returned.

- [ ] **Step 3: Add `_parse_bool` helper and extract new fields in `parse_detail`**

In `scraper/detail.py`, add after `_parse_area`:

```python
def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    return value.strip().lower() in ("ano", "yes", "true", "1")
```

In `parse_detail`, after the existing extractions (before the `return` dict), add:

```python
    has_elevator_raw = extract_item_value(items, "Výtah")
    outdoor_raw = (
        extract_item_value(items, "Balkón")
        or extract_item_value(items, "Lodžie")
        or extract_item_value(items, "Terasa")
    )
    parking_raw = (
        extract_item_value(items, "Garáž")
        or extract_item_value(items, "Parkovací místo")
    )
```

Add to the returned dict:

```python
        "energy_class": extract_item_value(items, "Energetická náročnost budovy"),
        "has_elevator": _parse_bool(has_elevator_raw),
        "has_outdoor_space": True if outdoor_raw is not None else None,
        "has_parking": True if parking_raw is not None else None,
        "has_cellar": _parse_bool(extract_item_value(items, "Sklep")),
        "year_built": _parse_area(extract_item_value(items, "Rok výstavby")),
        "land_area_m2": _parse_area(extract_item_value(items, "Plocha pozemku")),
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
poetry run pytest tests/scraper/test_detail.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scraper/detail.py tests/scraper/test_detail.py
git commit -m "feat: extract energy class, elevator, outdoor, parking, land area from sreality API"
```

---

### Task 3: Extend ListingScore and SearchConfig models, add MarketSnapshot, Migration 2

**Files:**
- Modify: `shared/models.py`
- Create: `migrations/versions/0003_signals_snapshots_weights.py`

- [ ] **Step 1: Add new columns to `ListingScore` in `shared/models.py`**

After `alerted_at` in the `ListingScore` class, add:

```python
    condition_score: Mapped[Optional[float]] = mapped_column(Float)
    condition_price_pct: Mapped[Optional[float]] = mapped_column(Float)
    energy_score: Mapped[Optional[float]] = mapped_column(Float)
    floor_elevator_penalty: Mapped[Optional[float]] = mapped_column(Float)
    building_type_score: Mapped[Optional[float]] = mapped_column(Float)
    drop_recency_days: Mapped[Optional[int]] = mapped_column(Integer)
    market_delta_pct: Mapped[Optional[float]] = mapped_column(Float)
    land_price_percentile: Mapped[Optional[float]] = mapped_column(Float)
    combined_area_price_pct: Mapped[Optional[float]] = mapped_column(Float)
```

- [ ] **Step 2: Add `scoring_weights` and `alert_thresholds` to `SearchConfig`**

After `travel_mode` in the `SearchConfig` class, add:

```python
    scoring_weights: Mapped[Optional[dict]] = mapped_column(JSON)
    alert_thresholds: Mapped[Optional[dict]] = mapped_column(JSON)
```

- [ ] **Step 3: Add `MarketSnapshot` model at the end of `shared/models.py`**

```python
class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    category_main_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    category_type_cb: Mapped[int] = mapped_column(Integer, nullable=False)
    locality_district_id: Mapped[Optional[int]] = mapped_column(Integer)
    listing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    median_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    avg_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    p25_price_m2: Mapped[Optional[float]] = mapped_column(Float)
    p75_price_m2: Mapped[Optional[float]] = mapped_column(Float)
```

- [ ] **Step 4: Create Migration 2**

Create `migrations/versions/0003_signals_snapshots_weights.py`:

```python
"""add signal columns, market_snapshots table, scoring weights

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from typing import Sequence, Union

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in [
        "condition_score", "condition_price_pct", "energy_score",
        "floor_elevator_penalty", "building_type_score", "market_delta_pct",
        "land_price_percentile", "combined_area_price_pct",
    ]:
        op.add_column("listing_scores", sa.Column(col, sa.Float(), nullable=True))
    op.add_column("listing_scores", sa.Column("drop_recency_days", sa.Integer(), nullable=True))

    op.add_column("search_configs", sa.Column("scoring_weights", JSONB(), nullable=True))
    op.add_column("search_configs", sa.Column("alert_thresholds", JSONB(), nullable=True))

    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("category_main_cb", sa.Integer(), nullable=False),
        sa.Column("category_type_cb", sa.Integer(), nullable=False),
        sa.Column("locality_district_id", sa.Integer(), nullable=True),
        sa.Column("listing_count", sa.Integer(), nullable=False),
        sa.Column("median_price_m2", sa.Float(), nullable=True),
        sa.Column("avg_price_m2", sa.Float(), nullable=True),
        sa.Column("p25_price_m2", sa.Float(), nullable=True),
        sa.Column("p75_price_m2", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("market_snapshots")
    op.drop_column("search_configs", "alert_thresholds")
    op.drop_column("search_configs", "scoring_weights")
    for col in [
        "drop_recency_days", "combined_area_price_pct", "land_price_percentile",
        "market_delta_pct", "building_type_score", "floor_elevator_penalty",
        "energy_score", "condition_price_pct", "condition_score",
    ]:
        op.drop_column("listing_scores", col)
```

- [ ] **Step 5: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: all pass (new model fields are nullable).

- [ ] **Step 6: Commit**

```bash
git add shared/models.py migrations/versions/0003_signals_snapshots_weights.py
git commit -m "feat: add ListingScore signal columns, MarketSnapshot model, scoring weights to SearchConfig"
```

---

## Phase 2 — Analyzer Signals

### Task 4: Add condition signals to `compute_signals`

**Files:**
- Modify: `analyzer/signals.py`
- Modify: `tests/analyzer/test_signals.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_signals.py`:

```python
def add_listing_with_condition(db, hash_id, price, condition, area=80, district=5007):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=price,
        area_m2=area,
        price_per_m2=price / area,
        condition=condition,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=district,
        is_active=True,
        first_seen_at=now - timedelta(days=5),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    return listing


def test_condition_score_excellent(db):
    add_config(db)
    add_listing_with_condition(db, 6001, 4_000_000, "Novostavba")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=6001).one()
    assert score.condition_score == 5.0


def test_condition_score_good(db):
    add_config(db)
    add_listing_with_condition(db, 6002, 4_000_000, "Velmi dobrý")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=6002).one()
    assert score.condition_score == 4.0


def test_condition_score_none_when_unknown(db):
    add_config(db)
    add_listing(db, hash_id=6003, price=4_000_000)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=6003).one()
    assert score.condition_score is None


def test_condition_price_pct_lower_for_cheaper_in_same_condition(db):
    add_config(db)
    add_listing_with_condition(db, 6011, 3_000_000, "Dobrý")
    add_listing_with_condition(db, 6012, 5_000_000, "Dobrý")
    add_listing_with_condition(db, 6013, 7_000_000, "Dobrý")
    db.commit()
    compute_signals(db)
    scores = {s.hash_id: s for s in db.query(ListingScore).filter(
        ListingScore.hash_id.in_([6011, 6012, 6013])
    ).all()}
    assert scores[6011].condition_price_pct < scores[6012].condition_price_pct
    assert scores[6012].condition_price_pct < scores[6013].condition_price_pct
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/analyzer/test_signals.py::test_condition_score_excellent -v
```

Expected: `FAILED` — `assert None == 5.0`.

- [ ] **Step 3: Add condition scoring constants and logic to `analyzer/signals.py`**

After the imports at the top of `analyzer/signals.py`, add:

```python
CONDITION_SCORES: dict[str, float] = {
    "Novostavba": 5.0,
    "Po rekonstrukci": 5.0,
    "Ve výstavbě": 4.0,
    "Velmi dobrý": 4.0,
    "Dobrý": 3.0,
    "Před rekonstrukcí": 2.0,
    "Špatný": 1.0,
    "Demolice": 0.0,
}

CONDITION_BUCKETS: dict[str, str] = {
    "Novostavba": "excellent",
    "Po rekonstrukci": "excellent",
    "Ve výstavbě": "good",
    "Velmi dobrý": "good",
    "Dobrý": "good",
    "Před rekonstrukcí": "poor",
    "Špatný": "poor",
    "Demolice": "poor",
}
```

In `compute_signals`, after the existing `percentile_sql` query, add a second query for condition percentiles:

```python
    condition_pct_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY
                    CASE condition
                        WHEN 'Novostavba'       THEN 'excellent'
                        WHEN 'Po rekonstrukci'  THEN 'excellent'
                        WHEN 'Ve výstavbě'      THEN 'good'
                        WHEN 'Velmi dobrý'      THEN 'good'
                        WHEN 'Dobrý'            THEN 'good'
                        WHEN 'Před rekonstrukcí' THEN 'poor'
                        WHEN 'Špatný'           THEN 'poor'
                        WHEN 'Demolice'         THEN 'poor'
                        ELSE NULL
                    END,
                    category_main_cb,
                    category_type_cb,
                    locality_district_id
                ORDER BY price_per_m2
            ) * 100 AS condition_price_pct
        FROM listings
        WHERE is_active = TRUE AND condition IS NOT NULL AND price_per_m2 IS NOT NULL
    """)
    condition_pcts = {r[0]: r[1] for r in db.execute(condition_pct_sql).fetchall()}
```

In the listing loop, when setting/updating the score object, add:

```python
        cond_score = CONDITION_SCORES.get(listing.condition) if listing.condition else None
        cond_pct = condition_pcts.get(listing.hash_id)

        # ... (set on existing or new score object):
        score_obj.condition_score = cond_score
        score_obj.condition_price_pct = cond_pct
```

Refactor the loop to use a `score_obj` variable for both the create and update branches to avoid repetition:

```python
        existing = db.query(ListingScore).filter_by(hash_id=listing.hash_id).first()
        if existing is None:
            score_obj = ListingScore(
                hash_id=listing.hash_id,
                is_hot=False,
                computed_at=now,
            )
            db.add(score_obj)
        else:
            score_obj = existing
            score_obj.computed_at = now

        score_obj.price_percentile = price_pct
        score_obj.price_per_m2_percentile = ppm2_pct
        score_obj.days_on_market = days_on_market
        score_obj.had_price_drop = had_price_drop
        score_obj.price_drop_pct = price_drop_pct
        score_obj.condition_score = cond_score
        score_obj.condition_price_pct = cond_pct
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/analyzer/test_signals.py -v
```

Expected: all pass including new tests.

- [ ] **Step 5: Commit**

```bash
git add analyzer/signals.py tests/analyzer/test_signals.py
git commit -m "feat: add condition_score and condition_price_pct signals"
```

---

### Task 5: Add property attribute signals (energy, floor/elevator, building type)

**Files:**
- Modify: `analyzer/signals.py`
- Modify: `tests/analyzer/test_signals.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_signals.py`:

```python
def add_listing_with_attrs(db, hash_id, price, energy_class=None,
                            floor=None, has_elevator=None, building_type=None, area=80):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=price,
        area_m2=area,
        price_per_m2=price / area,
        energy_class=energy_class,
        floor=floor,
        has_elevator=has_elevator,
        building_type=building_type,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
        is_active=True,
        first_seen_at=now - timedelta(days=5),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    return listing


def test_energy_score_A_is_5(db):
    add_config(db)
    add_listing_with_attrs(db, 7001, 4_000_000, energy_class="A")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7001).one()
    assert score.energy_score == 5.0


def test_energy_score_G_is_0(db):
    add_config(db)
    add_listing_with_attrs(db, 7002, 4_000_000, energy_class="G")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7002).one()
    assert score.energy_score == 0.0


def test_energy_score_none_when_absent(db):
    add_config(db)
    add_listing(db, hash_id=7003, price=4_000_000)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7003).one()
    assert score.energy_score is None


def test_floor_elevator_penalty_zero_with_elevator(db):
    add_config(db)
    add_listing_with_attrs(db, 7011, 4_000_000, floor="5. podlaží z 7", has_elevator=True)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7011).one()
    assert score.floor_elevator_penalty == 0.0


def test_floor_elevator_penalty_negative_high_floor_no_elevator(db):
    add_config(db)
    add_listing_with_attrs(db, 7012, 4_000_000, floor="5. podlaží z 7", has_elevator=False)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7012).one()
    assert score.floor_elevator_penalty == -10.0  # (5-3) * -5


def test_floor_elevator_penalty_capped_at_minus_20(db):
    add_config(db)
    add_listing_with_attrs(db, 7013, 4_000_000, floor="9. podlaží z 10", has_elevator=False)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7013).one()
    assert score.floor_elevator_penalty == -20.0


def test_building_type_score_brick_is_5(db):
    add_config(db)
    add_listing_with_attrs(db, 7021, 4_000_000, building_type="Cihlová")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7021).one()
    assert score.building_type_score == 5.0


def test_building_type_score_panel_is_2(db):
    add_config(db)
    add_listing_with_attrs(db, 7022, 4_000_000, building_type="Panelová")
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=7022).one()
    assert score.building_type_score == 2.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/analyzer/test_signals.py::test_energy_score_A_is_5 -v
```

Expected: `FAILED`.

- [ ] **Step 3: Add constants and helper functions to `analyzer/signals.py`**

After `CONDITION_BUCKETS`, add:

```python
import re

ENERGY_SCORES: dict[str, float] = {
    "A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0, "F": 0.5, "G": 0.0,
}

BUILDING_TYPE_SCORES: dict[str, float] = {
    "Cihlová": 5.0, "Kamenná": 5.0,
    "Smíšená": 3.0,
    "Panelová": 2.0, "Dřevostavba": 2.0, "Skelet": 2.0,
}


def _parse_floor_number(floor_str: Optional[str]) -> Optional[int]:
    if not floor_str:
        return None
    if "přízemí" in floor_str.lower():
        return 0
    match = re.search(r"(\d+)\.", floor_str)
    return int(match.group(1)) if match else None


def _floor_elevator_penalty(floor_str: Optional[str], has_elevator: Optional[bool]) -> float:
    if has_elevator:
        return 0.0
    floor_num = _parse_floor_number(floor_str)
    if floor_num is None or floor_num <= 3:
        return 0.0
    return max(-20.0, -5.0 * (floor_num - 3))
```

In the listing loop in `compute_signals`, add after the condition signals:

```python
        score_obj.energy_score = ENERGY_SCORES.get(listing.energy_class) if listing.energy_class else None
        score_obj.floor_elevator_penalty = _floor_elevator_penalty(listing.floor, listing.has_elevator)
        score_obj.building_type_score = BUILDING_TYPE_SCORES.get(listing.building_type) if listing.building_type else None
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/analyzer/test_signals.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add analyzer/signals.py tests/analyzer/test_signals.py
git commit -m "feat: add energy_score, floor_elevator_penalty, building_type_score signals"
```

---

### Task 6: Add `drop_recency_days` signal

**Files:**
- Modify: `analyzer/signals.py`
- Modify: `tests/analyzer/test_signals.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_signals.py`:

```python
def test_drop_recency_days_reflects_most_recent_drop(db):
    add_config(db)
    add_listing(db, hash_id=8001, price=3_800_000, days_ago=30)
    db.add(ListingPriceHistory(
        hash_id=8001, price_czk=4_200_000, price_per_m2=4_200_000/80,
        recorded_at=datetime.now(UTC) - timedelta(days=30),
    ))
    db.add(ListingPriceHistory(
        hash_id=8001, price_czk=4_000_000, price_per_m2=4_000_000/80,
        recorded_at=datetime.now(UTC) - timedelta(days=10),
    ))
    db.add(ListingPriceHistory(
        hash_id=8001, price_czk=3_800_000, price_per_m2=3_800_000/80,
        recorded_at=datetime.now(UTC) - timedelta(days=3),
    ))
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=8001).one()
    assert score.drop_recency_days is not None
    assert 3 <= score.drop_recency_days <= 4


def test_drop_recency_days_none_when_no_history(db):
    add_config(db)
    add_listing(db, hash_id=8002, price=4_000_000, days_ago=10)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=8002).one()
    assert score.drop_recency_days is None


def test_drop_recency_days_none_when_price_never_dropped(db):
    add_config(db)
    add_listing(db, hash_id=8003, price=4_500_000, days_ago=20)
    db.add(ListingPriceHistory(
        hash_id=8003, price_czk=4_000_000, price_per_m2=50_000.0,
        recorded_at=datetime.now(UTC) - timedelta(days=20),
    ))
    db.add(ListingPriceHistory(
        hash_id=8003, price_czk=4_500_000, price_per_m2=56_250.0,
        recorded_at=datetime.now(UTC) - timedelta(days=5),
    ))
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=8003).one()
    assert score.drop_recency_days is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/analyzer/test_signals.py::test_drop_recency_days_reflects_most_recent_drop -v
```

Expected: `FAILED`.

- [ ] **Step 3: Add `_drop_recency_days` helper and wire into `compute_signals`**

Add to `analyzer/signals.py` after `_floor_elevator_penalty`:

```python
def _drop_recency_days(db: Session, hash_id: int, now: datetime) -> Optional[int]:
    history = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.desc())
        .all()
    )
    for i in range(len(history) - 1):
        if history[i].price_czk < history[i + 1].price_czk:
            drop_at = history[i].recorded_at.replace(tzinfo=None)
            return (now.replace(tzinfo=None) - drop_at).days
    return None
```

In the listing loop in `compute_signals`, add:

```python
        score_obj.drop_recency_days = _drop_recency_days(db, listing.hash_id, now)
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/analyzer/test_signals.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add analyzer/signals.py tests/analyzer/test_signals.py
git commit -m "feat: add drop_recency_days signal"
```

---

### Task 7: Create market snapshot module

**Files:**
- Create: `analyzer/snapshots.py`
- Create: `tests/analyzer/test_snapshots.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analyzer/test_snapshots.py`:

```python
import pytest
from datetime import datetime, timezone, timedelta
from shared.models import Listing, MarketSnapshot
from analyzer.snapshots import create_market_snapshot

UTC = timezone.utc


def add_listing(db, hash_id, price_per_m2, cat_main=1, cat_type=1, district=5007):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"L{hash_id}",
        price_czk=int(price_per_m2 * 80),
        area_m2=80,
        price_per_m2=price_per_m2,
        category_main_cb=cat_main,
        category_type_cb=cat_type,
        locality_district_id=district,
        is_active=True,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()


def test_create_snapshot_writes_one_row_per_bucket(db):
    add_listing(db, 9001, 60_000.0)
    add_listing(db, 9002, 70_000.0)
    add_listing(db, 9003, 80_000.0)
    db.commit()
    count = create_market_snapshot(db)
    assert count == 1
    snap = db.query(MarketSnapshot).filter_by(
        category_main_cb=1, category_type_cb=1, locality_district_id=5007
    ).one()
    assert snap.listing_count == 3
    assert snap.median_price_m2 == pytest.approx(70_000.0)


def test_snapshot_ignores_inactive_listings(db):
    now = datetime.now(UTC)
    add_listing(db, 9011, 60_000.0)
    inactive = Listing(
        hash_id=9012, name="L9012",
        price_czk=1_000_000, area_m2=80, price_per_m2=12_500.0,
        category_main_cb=1, category_type_cb=1, locality_district_id=5007,
        is_active=False,
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now - timedelta(days=2),
    )
    db.add(inactive)
    db.commit()
    create_market_snapshot(db)
    snap = db.query(MarketSnapshot).filter_by(
        category_main_cb=1, category_type_cb=1, locality_district_id=5007
    ).one()
    assert snap.listing_count == 1


def test_snapshot_creates_separate_rows_per_bucket(db):
    add_listing(db, 9021, 60_000.0, cat_main=1, cat_type=1, district=5007)
    add_listing(db, 9022, 70_000.0, cat_main=1, cat_type=2, district=5007)
    add_listing(db, 9023, 50_000.0, cat_main=1, cat_type=1, district=6202)
    db.commit()
    count = create_market_snapshot(db)
    assert count == 3
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/analyzer/test_snapshots.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Create `analyzer/snapshots.py`**

```python
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median, quantiles
from typing import Optional

from sqlalchemy.orm import Session

from shared.models import Listing, MarketSnapshot

UTC = timezone.utc


def create_market_snapshot(db: Session) -> int:
    now = datetime.now(UTC)

    rows = (
        db.query(
            Listing.category_main_cb,
            Listing.category_type_cb,
            Listing.locality_district_id,
            Listing.price_per_m2,
        )
        .filter(Listing.is_active == True, Listing.price_per_m2 != None)
        .all()
    )

    buckets: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        key = (row.category_main_cb, row.category_type_cb, row.locality_district_id)
        buckets[key].append(row.price_per_m2)

    count = 0
    for (cat_main, cat_type, district_id), prices in buckets.items():
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        med = median(prices_sorted)
        avg = sum(prices_sorted) / n
        if n >= 4:
            qs = quantiles(prices_sorted, n=4)
            p25, p75 = qs[0], qs[2]
        else:
            p25 = p75 = med

        db.add(MarketSnapshot(
            snapshot_at=now,
            category_main_cb=cat_main,
            category_type_cb=cat_type,
            locality_district_id=district_id,
            listing_count=n,
            median_price_m2=med,
            avg_price_m2=avg,
            p25_price_m2=p25,
            p75_price_m2=p75,
        ))
        count += 1

    db.commit()
    return count
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/analyzer/test_snapshots.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add analyzer/snapshots.py tests/analyzer/test_snapshots.py
git commit -m "feat: add market snapshot creation"
```

---

### Task 8: Add `market_delta_pct` and land signals to `compute_signals`

**Files:**
- Modify: `analyzer/signals.py`
- Modify: `tests/analyzer/test_signals.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/analyzer/test_signals.py`:

```python
from shared.models import MarketSnapshot


def add_snapshot(db, median_m2, cat_main=1, cat_type=1, district=5007, days_ago=1):
    db.add(MarketSnapshot(
        snapshot_at=datetime.now(UTC) - timedelta(days=days_ago),
        category_main_cb=cat_main,
        category_type_cb=cat_type,
        locality_district_id=district,
        listing_count=10,
        median_price_m2=median_m2,
        avg_price_m2=median_m2,
        p25_price_m2=median_m2 * 0.8,
        p75_price_m2=median_m2 * 1.2,
    ))
    db.flush()


def test_market_delta_pct_negative_when_cheaper_than_historical(db):
    add_config(db)
    add_snapshot(db, median_m2=80_000.0)
    add_listing(db, hash_id=10001, price=4_800_000, area=80)  # 60_000/m2 vs 80_000 median
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=10001).one()
    assert score.market_delta_pct is not None
    assert score.market_delta_pct < 0


def test_market_delta_pct_none_when_no_snapshots(db):
    add_config(db)
    add_listing(db, hash_id=10002, price=4_000_000, area=80)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=10002).one()
    assert score.market_delta_pct is None


def add_listing_with_land(db, hash_id, price, area_m2, land_area_m2, district=5007):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"House {hash_id}",
        price_czk=price,
        area_m2=area_m2,
        price_per_m2=price / area_m2,
        land_area_m2=land_area_m2,
        category_main_cb=2,
        category_type_cb=1,
        locality_district_id=district,
        is_active=True,
        first_seen_at=now - timedelta(days=5),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()


def test_land_price_percentile_lower_for_cheaper_land(db):
    add_config(db)
    add_listing_with_land(db, 10011, 5_000_000, 150, 500)   # 10_000/m2 land
    add_listing_with_land(db, 10012, 7_000_000, 150, 500)   # 14_000/m2 land
    add_listing_with_land(db, 10013, 9_000_000, 150, 500)   # 18_000/m2 land
    db.commit()
    compute_signals(db)
    scores = {s.hash_id: s for s in db.query(ListingScore).filter(
        ListingScore.hash_id.in_([10011, 10012, 10013])
    ).all()}
    assert scores[10011].land_price_percentile < scores[10012].land_price_percentile
    assert scores[10012].land_price_percentile < scores[10013].land_price_percentile


def test_land_percentile_none_for_apartments(db):
    add_config(db)
    add_listing(db, hash_id=10021, price=4_000_000)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=10021).one()
    assert score.land_price_percentile is None
    assert score.combined_area_price_pct is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/analyzer/test_signals.py::test_market_delta_pct_negative_when_cheaper_than_historical -v
```

Expected: `FAILED`.

- [ ] **Step 3: Add market delta and land signal computation to `analyzer/signals.py`**

At the top of `analyzer/signals.py`, update the imports to:

```python
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median as py_median
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.models import Listing, ListingPriceHistory, ListingScore, MarketSnapshot
```

In `compute_signals`, after the condition percentile query, add queries for historical median and land percentiles:

```python
    # Historical market medians (9-month window)
    nine_months_ago = now - timedelta(days=270)
    snap_rows = (
        db.query(
            MarketSnapshot.category_main_cb,
            MarketSnapshot.category_type_cb,
            MarketSnapshot.locality_district_id,
            MarketSnapshot.median_price_m2,
        )
        .filter(MarketSnapshot.snapshot_at >= nine_months_ago)
        .all()
    )
    snap_buckets: dict[tuple, list[float]] = defaultdict(list)
    for r in snap_rows:
        if r.median_price_m2 is not None:
            snap_buckets[(r.category_main_cb, r.category_type_cb, r.locality_district_id)].append(r.median_price_m2)
    historical_medians = {k: py_median(v) for k, v in snap_buckets.items()}

    # Land percentiles
    land_pct_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY CAST(price_czk AS REAL) / NULLIF(land_area_m2, 0)
            ) * 100 AS land_price_percentile,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY CAST(price_czk AS REAL) / NULLIF(area_m2 + 0.15 * land_area_m2, 0)
            ) * 100 AS combined_area_price_pct
        FROM listings
        WHERE is_active = TRUE AND land_area_m2 IS NOT NULL AND land_area_m2 > 0
    """)
    land_pcts = {r[0]: (r[1], r[2]) for r in db.execute(land_pct_sql).fetchall()}
```

Also add the import at the top of `signals.py`: `from shared.models import ..., MarketSnapshot`

In the listing loop, add:

```python
        bucket_key = (listing.category_main_cb, listing.category_type_cb, listing.locality_district_id)
        hist_median = historical_medians.get(bucket_key)
        if hist_median and listing.price_per_m2:
            score_obj.market_delta_pct = (listing.price_per_m2 - hist_median) / hist_median * 100
        else:
            score_obj.market_delta_pct = None

        land_pct_val, combined_pct_val = land_pcts.get(listing.hash_id, (None, None))
        score_obj.land_price_percentile = land_pct_val
        score_obj.combined_area_price_pct = combined_pct_val
```

- [ ] **Step 4: Run all analyzer tests**

```bash
poetry run pytest tests/analyzer/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add analyzer/signals.py tests/analyzer/test_signals.py
git commit -m "feat: add market_delta_pct and land signal computation"
```

---

### Task 9: Wire snapshots into analyzer main and add alert evaluate endpoint

**Files:**
- Modify: `analyzer/main.py`

- [ ] **Step 1: Import and call `create_market_snapshot` in `run_analysis`**

In `analyzer/main.py`, add import:

```python
from analyzer.snapshots import create_market_snapshot
```

In `run_analysis`, after `compute_signals(db)` and before `compute_scores(...)`:

```python
        create_market_snapshot(db)
```

- [ ] **Step 2: Add `POST /alerts/evaluate/{search_config_id}` endpoint**

Add to `analyzer/main.py`:

```python
import httpx
from shared.models import SearchConfig, ListingScore, Listing, ListingSearchConfig
from analyzer.scoring import compute_scores
from dashboard.scoring import compute_live_score  # we will create this in Task 10


@app.post("/alerts/evaluate/{search_config_id}")
def evaluate_alerts(search_config_id: int):
    db = SessionLocal()
    try:
        config = db.query(SearchConfig).filter_by(id=search_config_id).first()
        if not config or not config.alert_thresholds:
            return {"status": "no_thresholds", "fired": 0}

        thresholds = config.alert_thresholds
        weights = config.scoring_weights or {}

        candidates = (
            db.query(Listing, ListingScore)
            .join(ListingSearchConfig,
                  ListingSearchConfig.hash_id == Listing.hash_id)
            .outerjoin(ListingScore, ListingScore.hash_id == Listing.hash_id)
            .filter(
                ListingSearchConfig.search_config_id == search_config_id,
                Listing.is_active == True,
            )
            .all()
        )

        min_score = thresholds.get("min_score")
        max_ppm2_pct = thresholds.get("max_price_m2_percentile")
        min_condition = thresholds.get("min_condition")
        max_drop_recency = thresholds.get("max_drop_recency_days")

        CONDITION_ORDER = {"wreck": 0, "poor": 1, "standard": 2, "good": 3, "excellent": 4}
        SCORE_TO_BUCKET = {0.0: "wreck", 1.0: "poor", 2.0: "poor", 3.0: "standard",
                           4.0: "good", 5.0: "excellent"}

        fired = []
        for listing, score in candidates:
            if score is None:
                continue
            live = compute_live_score(score, weights)
            if min_score is not None and (live is None or live < min_score):
                continue
            if max_ppm2_pct is not None and (score.price_per_m2_percentile is None
                                              or score.price_per_m2_percentile > max_ppm2_pct):
                continue
            if min_condition is not None and score.condition_score is not None:
                bucket = SCORE_TO_BUCKET.get(score.condition_score, "standard")
                if CONDITION_ORDER.get(bucket, 0) < CONDITION_ORDER.get(min_condition, 0):
                    continue
            if max_drop_recency is not None and (score.drop_recency_days is None
                                                  or score.drop_recency_days > max_drop_recency):
                continue
            fired.append(listing.hash_id)

        return {"status": "ok", "fired": len(fired), "hash_ids": fired}
    finally:
        db.close()
```

- [ ] **Step 3: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add analyzer/main.py
git commit -m "feat: wire market snapshots into analyzer run; add alert evaluate endpoint"
```

---

## Phase 3 — Dashboard

### Task 10: Create `dashboard/scoring.py` with live score computation

**Files:**
- Create: `dashboard/scoring.py`
- Create: `tests/dashboard/test_scoring.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dashboard/test_scoring.py`:

```python
import pytest
from shared.models import ListingScore
from dashboard.scoring import compute_live_score, DEFAULT_WEIGHTS


def make_score(**kwargs):
    s = ListingScore.__new__(ListingScore)
    defaults = dict(
        price_percentile=50.0,
        price_per_m2_percentile=50.0,
        condition_price_pct=None,
        energy_score=None,
        building_type_score=None,
        floor_elevator_penalty=None,
        drop_recency_days=None,
        market_delta_pct=None,
        combined_area_price_pct=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def test_neutral_score_is_50_when_all_signals_at_midpoint():
    score = make_score(price_percentile=50.0, price_per_m2_percentile=50.0)
    result = compute_live_score(score, DEFAULT_WEIGHTS)
    assert result == pytest.approx(50.0, abs=1.0)


def test_cheap_listing_scores_higher_than_expensive():
    cheap = make_score(price_percentile=10.0, price_per_m2_percentile=10.0)
    expensive = make_score(price_percentile=90.0, price_per_m2_percentile=90.0)
    assert compute_live_score(cheap, DEFAULT_WEIGHTS) > compute_live_score(expensive, DEFAULT_WEIGHTS)


def test_none_score_returns_none():
    result = compute_live_score(None, DEFAULT_WEIGHTS)
    assert result is None


def test_zero_weights_returns_none():
    score = make_score()
    result = compute_live_score(score, {})
    assert result is None


def test_recent_drop_improves_score():
    no_drop = make_score(price_percentile=30.0, price_per_m2_percentile=30.0, drop_recency_days=None)
    recent_drop = make_score(price_percentile=30.0, price_per_m2_percentile=30.0, drop_recency_days=2)
    assert compute_live_score(recent_drop, DEFAULT_WEIGHTS) > compute_live_score(no_drop, DEFAULT_WEIGHTS)


def test_negative_market_delta_improves_score():
    at_market = make_score(price_percentile=50.0, price_per_m2_percentile=50.0, market_delta_pct=0.0)
    below_market = make_score(price_percentile=50.0, price_per_m2_percentile=50.0, market_delta_pct=-20.0)
    assert compute_live_score(below_market, DEFAULT_WEIGHTS) > compute_live_score(at_market, DEFAULT_WEIGHTS)


def test_custom_weights_override_defaults():
    score = make_score(price_percentile=5.0, price_per_m2_percentile=90.0)
    price_heavy = {"price_pct": 1.0, "price_m2_pct": 0.0}
    m2_heavy = {"price_pct": 0.0, "price_m2_pct": 1.0}
    assert compute_live_score(score, price_heavy) > compute_live_score(score, m2_heavy)
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest tests/dashboard/test_scoring.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `dashboard/scoring.py`**

```python
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.models import ListingScore

DEFAULT_WEIGHTS: dict[str, float] = {
    "price_pct": 0.25,
    "price_m2_pct": 0.30,
    "condition_price_pct": 0.10,
    "energy_score": 0.05,
    "building_type_score": 0.05,
    "floor_elevator_penalty": 0.05,
    "drop_recency": 0.05,
    "market_delta": 0.10,
    "land_pct": 0.05,
}


def _normalise(key: str, value: float) -> float:
    match key:
        case "price_pct" | "price_m2_pct" | "condition_price_pct" | "land_pct":
            return 100.0 - value
        case "energy_score" | "building_type_score":
            return value / 5.0 * 100.0
        case "floor_elevator_penalty":
            return (value + 20.0) / 20.0 * 100.0
        case "drop_recency":
            return max(0.0, 100.0 - value / 90.0 * 100.0)
        case "market_delta":
            clamped = max(-30.0, min(30.0, value))
            return (30.0 - clamped) / 60.0 * 100.0
        case _:
            return 50.0


def compute_live_score(
    score: Optional["ListingScore"],
    weights: dict[str, float],
) -> Optional[float]:
    if score is None:
        return None
    total_weight = sum(weights.values())
    if total_weight == 0:
        return None

    signal_map = {
        "price_pct": score.price_percentile,
        "price_m2_pct": score.price_per_m2_percentile,
        "condition_price_pct": score.condition_price_pct,
        "energy_score": score.energy_score,
        "building_type_score": score.building_type_score,
        "floor_elevator_penalty": score.floor_elevator_penalty,
        "drop_recency": score.drop_recency_days,
        "market_delta": score.market_delta_pct,
        "land_pct": score.combined_area_price_pct,
    }

    total = sum(
        weights.get(k, 0.0) * (_normalise(k, v) if v is not None else 50.0)
        for k, v in signal_map.items()
    )
    return round(total / total_weight, 1)
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/dashboard/test_scoring.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard/scoring.py tests/dashboard/test_scoring.py
git commit -m "feat: add live score computation with configurable weights"
```

---

### Task 11: Update listings router to use live score and add weights PATCH endpoint

**Files:**
- Modify: `dashboard/routers/listings.py`
- Modify: `dashboard/routers/configs.py`

- [ ] **Step 1: Update `listings.py` to compute live scores and embed signal data attributes**

In `dashboard/routers/listings.py`, add import:

```python
from dashboard.scoring import compute_live_score, DEFAULT_WEIGHTS
```

In `listings_feed`, after `listings = raw if sc_id else [...]`, add:

```python
    weights = {}
    if sc_id:
        config_obj = db.query(SearchConfig).filter_by(id=sc_id).first()
        if config_obj and config_obj.scoring_weights:
            weights = config_obj.scoring_weights
    if not weights:
        weights = DEFAULT_WEIGHTS

    listing_rows = []
    for item in listings:
        lst, score, distance = item
        live_score = compute_live_score(score, weights)
        listing_rows.append((lst, score, distance, live_score))
```

Pass `listing_rows` as `listings` and `weights` to the template context:

```python
    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "listings": listing_rows,
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "configs": configs,
            "filter_qs": filter_qs,
            "has_distance_col": bool(sc_id),
            "weights": weights,
            "default_weights": DEFAULT_WEIGHTS,
            "filters": {
                "search_config_id": sc_id,
                "category_main_cb": cat_cb,
                "locality_district_id": dist_id,
                "min_price": min_p,
                "max_price": max_p,
                "min_score": min_s,
                "hot_only": hot_only,
                "status": status,
                "order_by": col_key,
                "order_dir": order_dir,
            },
        },
    )
```

Update the template loop reference — the tuple is now 4 elements: `{% for listing, score, distance, live_score in listings %}`.

- [ ] **Step 2: Add `PATCH /config/{config_id}/weights` endpoint to `configs.py`**

Add to `dashboard/routers/configs.py`:

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse


@router.post("/config/{config_id}/weights")
async def update_weights(config_id: int, request: Request, db: Session = Depends(get_db)):
    config = db.query(SearchConfig).filter_by(id=config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    body = await request.json()
    config.scoring_weights = body
    db.commit()
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/dashboard/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/routers/listings.py dashboard/routers/configs.py
git commit -m "feat: compute live score in listings feed; add weights save endpoint"
```

---

### Task 12: Update `listings.html` — new columns and column visibility

**Files:**
- Modify: `dashboard/templates/listings.html`

- [ ] **Step 1: Update the loop tuple unpacking and add new `<th>` headers**

Replace the `{% for listing, score, distance in listings %}` line with:

```jinja
{% for listing, score, distance, live_score in listings %}
```

Replace the existing `<thead>` block (preserving all existing columns) with the updated version that adds new `data-col` attributes to each `<th>` for JS toggling, and inserts the new columns:

```html
  <thead>
    <tr>
      <th>Name</th>
      <th>City</th>
      <th data-col="condition">Condition</th>
      <th data-col="energy">Energy</th>
      <th data-col="building_type">Building</th>
      <th data-col="floor">Floor</th>
      <th data-col="parking">Park.</th>
      <th data-col="outdoor">Balc.</th>
      <th data-col="land_area">Land m²</th>
      {{ sort_th("Price", "price") }}
      {{ sort_th("Price/m²", "price_m2") }}
      {{ sort_th("Price pct", "price_pct") }}
      {{ sort_th("PPM² pct", "ppm2_pct") }}
      {{ sort_th("Days", "days") }}
      {{ sort_th("Score", "score") }}
      {% if has_distance_col %}{{ sort_th("Distance", "distance") }}{% endif %}
      <th></th>
    </tr>
  </thead>
```

Replace the tbody row to include the new columns and the live_score:

```html
    <tr {% if not listing.is_active %}class="text-muted"{% endif %}>
      <td>
        {% if not listing.is_active %}
          <span class="badge bg-secondary me-1">inactive</span>
        {% elif score and score.is_hot %}
          <span class="badge bg-danger me-1">HOT</span>
        {% endif %}
        {{ listing.name }}
      </td>
      <td>{{ listing.locality or '—' }}</td>
      <td data-col="condition">{{ listing.condition or '—' }}</td>
      <td data-col="energy">{{ listing.energy_class or '—' }}</td>
      <td data-col="building_type">{{ listing.building_type or '—' }}</td>
      <td data-col="floor">{{ listing.floor or '—' }}</td>
      <td data-col="parking">{% if listing.has_parking %}✓{% elif listing.has_parking == false %}—{% else %}?{% endif %}</td>
      <td data-col="outdoor">{% if listing.has_outdoor_space %}✓{% elif listing.has_outdoor_space == false %}—{% else %}?{% endif %}</td>
      <td data-col="land_area">{{ listing.land_area_m2 or '—' }}</td>
      <td>{{ "{:,}".format(listing.price_czk or 0).replace(",", " ") }}</td>
      <td>{{ "{:,.0f}".format(listing.price_per_m2 or 0) }}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ "{:.0f}".format(score.price_per_m2_percentile or 0) }}th{% endif %}</td>
      <td>{% if score %}{{ score.days_on_market }}{% endif %}</td>
      <td>{% if live_score is not none %}<strong>{{ live_score }}</strong>{% else %}<span class="badge bg-secondary">pending</span>{% endif %}</td>
      {% if has_distance_col %}
      <td>
        {% if distance %}
          {{ "{:.1f}".format(distance.distance_m / 1000) }} km
          / {{ (distance.duration_s // 60) }} min
        {% else %}—{% endif %}
      </td>
      {% endif %}
      <td>
        <a href="/listing/{{ listing.hash_id }}" class="btn btn-xs btn-outline-primary btn-sm">Detail</a>
        <a href="{{ sreality_url(listing) }}"
           target="_blank" class="btn btn-xs btn-outline-secondary btn-sm">sreality</a>
      </td>
    </tr>
```

- [ ] **Step 2: Add the column visibility dropdown button and JS above the table**

Add after the filter form `</form>` and before `<table ...>`:

```html
<div class="d-flex justify-content-end mb-2">
  <div class="dropdown">
    <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"
            id="colToggleBtn" data-bs-toggle="dropdown" data-bs-auto-close="outside">
      Columns
    </button>
    <ul class="dropdown-menu dropdown-menu-end p-2" style="min-width:160px">
      {% set col_labels = [
        ("condition","Condition"),("energy","Energy class"),
        ("building_type","Building type"),("floor","Floor"),
        ("parking","Parking"),("outdoor","Balcony/terrace"),("land_area","Land area")
      ] %}
      {% for col_key, col_label in col_labels %}
      <li>
        <div class="form-check">
          <input class="form-check-input col-toggle" type="checkbox"
                 id="toggle_{{ col_key }}" data-col="{{ col_key }}" checked>
          <label class="form-check-label" for="toggle_{{ col_key }}">{{ col_label }}</label>
        </div>
      </li>
      {% endfor %}
    </ul>
  </div>
</div>

<script>
(function() {
  const COLS = ["condition","energy","building_type","floor","parking","outdoor","land_area"];

  function applyVisibility() {
    COLS.forEach(function(col) {
      const visible = localStorage.getItem("col_" + col) !== "false";
      document.querySelectorAll("[data-col='" + col + "']").forEach(function(el) {
        el.style.display = visible ? "" : "none";
      });
      const cb = document.getElementById("toggle_" + col);
      if (cb) cb.checked = visible;
    });
  }

  document.addEventListener("DOMContentLoaded", function() {
    applyVisibility();
    document.querySelectorAll(".col-toggle").forEach(function(cb) {
      cb.addEventListener("change", function() {
        localStorage.setItem("col_" + cb.dataset.col, cb.checked ? "true" : "false");
        applyVisibility();
      });
    });
  });
})();
</script>
```

- [ ] **Step 3: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/templates/listings.html
git commit -m "feat: add new attribute columns and column visibility toggle to listings table"
```

---

### Task 13: Add weights panel to `listings.html`

**Files:**
- Modify: `dashboard/templates/listings.html`

- [ ] **Step 1: Add the weights panel between the column toggle and the table**

Add after the column-toggle `</div>` and before `<table ...>`:

```html
{% if filters.search_config_id %}
<div class="card mb-3">
  <div class="card-header d-flex justify-content-between align-items-center py-2">
    <span class="fw-semibold small">Score weights</span>
    <button class="btn btn-sm btn-link p-0" type="button"
            data-bs-toggle="collapse" data-bs-target="#weightsPanel">
      Toggle
    </button>
  </div>
  <div class="collapse" id="weightsPanel">
    <div class="card-body">
      <div class="row g-2" id="weightsForm">
        {% set weight_labels = [
          ("price_pct","Price pct"),("price_m2_pct","Price/m² pct"),
          ("condition_price_pct","Condition pct"),("energy_score","Energy"),
          ("building_type_score","Building"),("floor_elevator_penalty","Floor/Elev"),
          ("drop_recency","Drop recency"),("market_delta","Market delta"),
          ("land_pct","Land pct")
        ] %}
        {% for key, label in weight_labels %}
        <div class="col-6 col-md-4 col-lg-3">
          <label class="form-label small mb-0">{{ label }}</label>
          <div class="d-flex align-items-center gap-1">
            <input type="range" class="form-range weight-slider" min="0" max="100" step="1"
                   id="w_{{ key }}" data-key="{{ key }}"
                   value="{{ (weights.get(key, default_weights.get(key, 0)) * 100) | int }}">
            <span class="small text-muted" id="wv_{{ key }}">
              {{ (weights.get(key, default_weights.get(key, 0)) * 100) | int }}%
            </span>
          </div>
        </div>
        {% endfor %}
      </div>
      <div class="mt-2 d-flex gap-2 align-items-center">
        <button class="btn btn-sm btn-primary" id="saveWeights">Save</button>
        <span class="small text-muted" id="weightsSum"></span>
      </div>
    </div>
  </div>
</div>

<script>
(function() {
  function updateSum() {
    var total = 0;
    document.querySelectorAll(".weight-slider").forEach(function(s) {
      total += parseInt(s.value, 10);
      document.getElementById("wv_" + s.dataset.key).textContent = s.value + "%";
    });
    document.getElementById("weightsSum").textContent = "Sum: " + total + "%";
  }

  document.addEventListener("DOMContentLoaded", function() {
    updateSum();
    document.querySelectorAll(".weight-slider").forEach(function(s) {
      s.addEventListener("input", updateSum);
    });

    document.getElementById("saveWeights").addEventListener("click", function() {
      var weights = {};
      document.querySelectorAll(".weight-slider").forEach(function(s) {
        weights[s.dataset.key] = parseInt(s.value, 10) / 100.0;
      });
      fetch("/config/{{ filters.search_config_id }}/weights", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(weights),
      }).then(function(r) {
        if (r.ok) { window.location.reload(); }
      });
    });
  });
})();
</script>
{% endif %}
```

- [ ] **Step 2: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add dashboard/templates/listings.html
git commit -m "feat: add configurable score weights panel to listings page"
```

---

### Task 14: Add market trend charts

**Files:**
- Modify: `dashboard/routers/market.py`
- Modify: `dashboard/templates/market.html`

- [ ] **Step 1: Add JSON endpoint for snapshot time series**

Add to `dashboard/routers/market.py`:

```python
from datetime import datetime, timedelta, timezone
from fastapi.responses import JSONResponse
from shared.models import MarketSnapshot

UTC = timezone.utc


@router.get("/market/snapshots")
def market_snapshots(db: Session = Depends(get_db)):
    cutoff = datetime.now(UTC) - timedelta(days=365)
    rows = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.snapshot_at >= cutoff)
        .order_by(MarketSnapshot.snapshot_at.asc())
        .all()
    )
    result: dict[str, list] = {}
    for r in rows:
        key = f"{r.category_main_cb}_{r.category_type_cb}_{r.locality_district_id}"
        if key not in result:
            result[key] = []
        result[key].append({
            "t": r.snapshot_at.isoformat(),
            "median": r.median_price_m2,
            "p25": r.p25_price_m2,
            "p75": r.p75_price_m2,
        })
    return JSONResponse(result)
```

- [ ] **Step 2: Update `market.html` to add trend charts**

Replace the full content of `dashboard/templates/market.html`:

```html
{% extends "base.html" %}
{% block title %}Market Overview{% endblock %}
{% block content %}
<h2>Market Overview</h2>

<table class="table table-sm table-hover mb-4">
  <thead>
    <tr>
      <th>District ID</th>
      <th>Category</th>
      <th>Type</th>
      <th>Active listings</th>
      <th>Avg price/m²</th>
      <th>Min price/m²</th>
      <th>Max price/m²</th>
    </tr>
  </thead>
  <tbody>
    {% for row in summary %}
    <tr>
      <td>{{ row.district_id }}</td>
      <td>{{ "Byty" if row.category_main_cb == 1 else "Domy" }}</td>
      <td>{{ "Prodej" if row.category_type_cb == 1 else "Pronájem" }}</td>
      <td>{{ row.listing_count }}</td>
      <td>{{ "{:,.0f}".format(row.avg_price_per_m2) }}</td>
      <td>{{ "{:,.0f}".format(row.min_price_per_m2) }}</td>
      <td>{{ "{:,.0f}".format(row.max_price_per_m2) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h4 class="mt-4">Price/m² trends (12 months)</h4>
<div id="chartsContainer" class="row g-3"></div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
fetch("/market/snapshots").then(r => r.json()).then(function(data) {
  const container = document.getElementById("chartsContainer");
  Object.entries(data).forEach(function([key, points]) {
    if (points.length < 2) return;
    const col = document.createElement("div");
    col.className = "col-12 col-md-6 col-lg-4";
    const canvas = document.createElement("canvas");
    col.appendChild(canvas);
    container.appendChild(col);

    const labels = points.map(p => p.t.substring(0, 10));
    new Chart(canvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Median price/m²",
            data: points.map(p => p.median),
            borderColor: "#0d6efd",
            backgroundColor: "transparent",
            tension: 0.3,
          },
          {
            label: "P25",
            data: points.map(p => p.p25),
            borderColor: "#adb5bd",
            borderDash: [4,4],
            backgroundColor: "transparent",
            tension: 0.3,
          },
          {
            label: "P75",
            data: points.map(p => p.p75),
            borderColor: "#adb5bd",
            borderDash: [4,4],
            backgroundColor: "transparent",
            tension: 0.3,
          },
        ]
      },
      options: {
        plugins: { title: { display: true, text: key } },
        scales: { y: { beginAtZero: false } },
      }
    });
  });
});
</script>
{% endblock %}
```

- [ ] **Step 3: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard/routers/market.py dashboard/templates/market.html
git commit -m "feat: add market trend charts with Chart.js using snapshot time series"
```

---

## Done

All 14 tasks implement the full spec:

| Spec section | Implemented in |
|---|---|
| New Listing fields extracted from API | Tasks 1, 2 |
| New signal columns on listing_scores | Tasks 1, 3, 4, 5, 6, 8 |
| market_snapshots table | Tasks 3, 7 |
| Scoring weights per SearchConfig | Tasks 3, 11 |
| Alert thresholds per SearchConfig | Tasks 3, 9 |
| Live score computation | Task 10 |
| Listings table: new columns | Task 12 |
| Column visibility (localStorage) | Task 12 |
| Weights panel UI | Task 13 |
| Market trend charts | Task 14 |
