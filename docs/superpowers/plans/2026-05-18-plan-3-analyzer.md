# Analyzer + Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute bargain scores for all active listings, flag hot offers, and send email alerts (immediate hot-offer notifications + a daily digest).

**Architecture:** `analyzer/signals.py` computes per-listing signals (percentile ranks, days on market, price drop) using SQL window functions. `analyzer/scoring.py` combines signals into a 0–100 score and sets the `is_hot` flag. `analyzer/alerts.py` sends SMTP email. `analyzer/main.py` exposes `POST /run` via FastAPI for on-demand triggering and runs the scheduler for timed jobs. All functions accept an explicit `Session` for testability.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, APScheduler 3.x, FastAPI, uvicorn, smtplib (stdlib)

**Prerequisite:** Plans 1 and 2 must be complete.

---

## File Map

| File | Responsibility |
|------|---------------|
| `analyzer/signals.py` | `compute_signals(db)` — writes price_percentile, price_per_m2_percentile, days_on_market, had_price_drop, price_drop_pct into `listing_scores` |
| `analyzer/scoring.py` | `compute_scores(db)` — reads signals, writes combined_score + is_hot |
| `analyzer/alerts.py` | `send_hot_alerts(db)`, `send_daily_digest(db)` — SMTP email |
| `analyzer/main.py` | FastAPI app with `POST /run`; APScheduler for scheduled + daily digest |
| `tests/analyzer/test_signals.py` | Signal computation with SQLite fixtures |
| `tests/analyzer/test_scoring.py` | Score formula unit tests (pure Python) |
| `tests/analyzer/test_alerts.py` | Email formatting + SMTP mock |

---

### Task 1: analyzer/signals.py + tests

**Files:**
- Create: `analyzer/signals.py`
- Create: `tests/analyzer/test_signals.py`

Signal computation uses SQL `percent_rank()` window functions. SQLite supports window functions since 3.25 — the test suite can use the existing SQLite fixture.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analyzer/test_signals.py
import pytest
from datetime import datetime, timezone, timedelta
from shared.models import SearchConfig, Listing, ListingPriceHistory, ListingScore
from analyzer.signals import compute_signals

UTC = timezone.utc


def add_config(db):
    config = SearchConfig(
        name="Test",
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
        created_at=datetime.now(UTC),
    )
    db.add(config)
    db.flush()
    return config


def add_listing(db, hash_id, price, area=80, days_ago=5):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=price,
        area_m2=area,
        price_per_m2=price / area if area else None,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
        is_active=True,
        first_seen_at=now - timedelta(days=days_ago),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    return listing


def test_compute_signals_creates_score_rows(db):
    add_config(db)
    add_listing(db, hash_id=5001, price=3_000_000)
    add_listing(db, hash_id=5002, price=4_000_000)
    add_listing(db, hash_id=5003, price=5_000_000)
    db.commit()
    compute_signals(db)
    scores = db.query(ListingScore).filter(ListingScore.hash_id.in_([5001, 5002, 5003])).all()
    assert len(scores) == 3


def test_cheapest_listing_has_lowest_price_percentile(db):
    add_config(db)
    add_listing(db, hash_id=5011, price=2_000_000)
    add_listing(db, hash_id=5012, price=4_000_000)
    add_listing(db, hash_id=5013, price=6_000_000)
    db.commit()
    compute_signals(db)
    scores = {s.hash_id: s for s in db.query(ListingScore).filter(
        ListingScore.hash_id.in_([5011, 5012, 5013])
    ).all()}
    assert scores[5011].price_percentile < scores[5012].price_percentile
    assert scores[5012].price_percentile < scores[5013].price_percentile


def test_days_on_market_computed(db):
    add_config(db)
    add_listing(db, hash_id=5021, price=4_000_000, days_ago=10)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=5021).one()
    assert score.days_on_market >= 10


def test_price_drop_detected(db):
    add_config(db)
    listing = add_listing(db, hash_id=5031, price=3_800_000, days_ago=15)
    history = ListingPriceHistory(
        hash_id=5031,
        price_czk=4_000_000,
        price_per_m2=4_000_000 / 80,
        recorded_at=datetime.now(UTC) - timedelta(days=15),
    )
    db.add(history)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=5031).one()
    assert score.had_price_drop is True
    assert score.price_drop_pct == pytest.approx(5.0, abs=0.1)


def test_no_price_drop_when_no_history(db):
    add_config(db)
    add_listing(db, hash_id=5041, price=4_000_000, days_ago=5)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=5041).one()
    assert score.had_price_drop is False
    assert score.price_drop_pct is None


def test_inactive_listings_excluded(db):
    add_config(db)
    add_listing(db, hash_id=5051, price=4_000_000, days_ago=5)
    now = datetime.now(UTC)
    inactive = Listing(
        hash_id=5052,
        name="Inactive",
        price_czk=2_000_000,
        area_m2=80,
        price_per_m2=25_000.0,
        category_main_cb=1,
        category_type_cb=1,
        locality_district_id=5007,
        is_active=False,
        first_seen_at=now - timedelta(days=20),
        last_seen_at=now - timedelta(days=5),
        removed_at=now - timedelta(days=5),
    )
    db.add(inactive)
    db.commit()
    compute_signals(db)
    score = db.query(ListingScore).filter_by(hash_id=5052).first()
    assert score is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analyzer/test_signals.py -v
```
Expected: `ImportError: No module named 'analyzer.signals'`

- [ ] **Step 3: Write `analyzer/signals.py`**

```python
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.models import Listing, ListingPriceHistory, ListingScore

UTC = timezone.utc


def _first_price(db: Session, hash_id: int) -> Optional[int]:
    row = (
        db.query(ListingPriceHistory)
        .filter_by(hash_id=hash_id)
        .order_by(ListingPriceHistory.recorded_at.asc())
        .first()
    )
    return row.price_czk if row else None


def compute_signals(db: Session) -> None:
    now = datetime.now(UTC)

    # Fetch percentile ranks via window function
    # Groups by (category_main_cb, category_type_cb, locality_district_id)
    percentile_sql = text("""
        SELECT
            hash_id,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY price_czk
            ) * 100 AS price_percentile,
            PERCENT_RANK() OVER (
                PARTITION BY category_main_cb, category_type_cb, locality_district_id
                ORDER BY price_per_m2
            ) * 100 AS price_per_m2_percentile
        FROM listings
        WHERE is_active = TRUE
    """)
    rows = db.execute(percentile_sql).fetchall()
    percentiles = {r[0]: (r[1], r[2]) for r in rows}

    active_listings = (
        db.query(Listing).filter_by(is_active=True).all()
    )

    for listing in active_listings:
        first_price = _first_price(db, listing.hash_id)
        had_price_drop = first_price is not None and first_price > listing.price_czk
        price_drop_pct: Optional[float] = None
        if had_price_drop and first_price:
            price_drop_pct = (first_price - listing.price_czk) / first_price * 100

        first_seen = listing.first_seen_at.replace(tzinfo=None)
        days_on_market = (now.replace(tzinfo=None) - first_seen).days

        price_pct, ppm2_pct = percentiles.get(listing.hash_id, (None, None))

        existing = db.query(ListingScore).filter_by(hash_id=listing.hash_id).first()
        if existing is None:
            score = ListingScore(
                hash_id=listing.hash_id,
                price_percentile=price_pct,
                price_per_m2_percentile=ppm2_pct,
                days_on_market=days_on_market,
                had_price_drop=had_price_drop,
                price_drop_pct=price_drop_pct,
                is_hot=False,
                computed_at=now,
            )
            db.add(score)
        else:
            existing.price_percentile = price_pct
            existing.price_per_m2_percentile = ppm2_pct
            existing.days_on_market = days_on_market
            existing.had_price_drop = had_price_drop
            existing.price_drop_pct = price_drop_pct
            existing.computed_at = now

    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analyzer/test_signals.py -v
```
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add analyzer/signals.py tests/analyzer/test_signals.py
git commit -m "feat: analyzer signal computation — percentile ranks, days on market, price drop"
```

---

### Task 2: analyzer/scoring.py + tests

**Files:**
- Create: `analyzer/scoring.py`
- Create: `tests/analyzer/test_scoring.py`

The scoring formula is pure Python math. Tests do not need a DB.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analyzer/test_scoring.py
import pytest
from analyzer.scoring import (
    days_and_drop_signal,
    combined_score,
    is_hot_offer,
    WEIGHT_PRICE,
    WEIGHT_PPM2,
    WEIGHT_DAYS,
)


def test_days_signal_zero_days():
    assert days_and_drop_signal(days_on_market=0, price_drop_pct=None) == pytest.approx(0.0)


def test_days_signal_180_days_no_drop():
    assert days_and_drop_signal(days_on_market=180, price_drop_pct=None) == pytest.approx(70.0)


def test_days_signal_180_days_capped():
    assert days_and_drop_signal(days_on_market=999, price_drop_pct=None) == pytest.approx(70.0)


def test_days_signal_with_20pct_drop():
    result = days_and_drop_signal(days_on_market=0, price_drop_pct=20.0)
    assert result == pytest.approx(30.0)


def test_days_signal_combined():
    result = days_and_drop_signal(days_on_market=90, price_drop_pct=10.0)
    days_score = 90 / 180 * 70
    drop_bonus = 10 / 20 * 30
    assert result == pytest.approx(days_score + drop_bonus)


def test_days_signal_drop_capped_at_20pct():
    result_20 = days_and_drop_signal(days_on_market=0, price_drop_pct=20.0)
    result_50 = days_and_drop_signal(days_on_market=0, price_drop_pct=50.0)
    assert result_20 == result_50


def test_combined_score_weights_sum_to_1():
    assert WEIGHT_PRICE + WEIGHT_PPM2 + WEIGHT_DAYS == pytest.approx(1.0)


def test_combined_score_perfect_bargain():
    score = combined_score(
        price_percentile=0.0,
        price_per_m2_percentile=0.0,
        days_on_market=180,
        price_drop_pct=20.0,
    )
    assert score == pytest.approx(100.0)


def test_combined_score_worst_case():
    score = combined_score(
        price_percentile=100.0,
        price_per_m2_percentile=100.0,
        days_on_market=0,
        price_drop_pct=None,
    )
    assert score == pytest.approx(0.0)


def test_combined_score_midpoint():
    score = combined_score(
        price_percentile=50.0,
        price_per_m2_percentile=50.0,
        days_on_market=90,
        price_drop_pct=None,
    )
    days_s = days_and_drop_signal(90, None)
    expected = WEIGHT_PRICE * 50 + WEIGHT_PPM2 * 50 + WEIGHT_DAYS * days_s
    assert score == pytest.approx(expected)


def test_is_hot_true_when_new_and_cheap():
    assert is_hot_offer(days_on_market=3, price_per_m2_percentile=20.0, hot_max_days=7) is True


def test_is_hot_false_when_old():
    assert is_hot_offer(days_on_market=10, price_per_m2_percentile=20.0, hot_max_days=7) is False


def test_is_hot_false_when_not_cheap():
    assert is_hot_offer(days_on_market=3, price_per_m2_percentile=30.0, hot_max_days=7) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analyzer/test_scoring.py -v
```
Expected: `ImportError: No module named 'analyzer.scoring'`

- [ ] **Step 3: Write `analyzer/scoring.py`**

```python
from sqlalchemy.orm import Session
from shared.models import ListingScore

WEIGHT_PRICE: float = 0.35
WEIGHT_PPM2: float = 0.40
WEIGHT_DAYS: float = 0.25


def days_and_drop_signal(days_on_market: int, price_drop_pct: float | None) -> float:
    days_score = min(days_on_market, 180) / 180 * 70
    drop_bonus = min(price_drop_pct or 0.0, 20.0) / 20.0 * 30
    return days_score + drop_bonus


def combined_score(
    price_percentile: float,
    price_per_m2_percentile: float,
    days_on_market: int,
    price_drop_pct: float | None,
) -> float:
    d = days_and_drop_signal(days_on_market, price_drop_pct)
    return (
        WEIGHT_PRICE * (100 - price_percentile)
        + WEIGHT_PPM2 * (100 - price_per_m2_percentile)
        + WEIGHT_DAYS * d
    )


def is_hot_offer(
    days_on_market: int,
    price_per_m2_percentile: float,
    hot_max_days: int,
) -> bool:
    return days_on_market < hot_max_days and price_per_m2_percentile < 25.0


def compute_scores(db: Session, bargain_threshold: float, hot_max_days: int) -> int:
    scores = db.query(ListingScore).all()
    updated = 0
    for score in scores:
        if score.price_percentile is None or score.price_per_m2_percentile is None:
            continue
        score.combined_score = combined_score(
            price_percentile=score.price_percentile,
            price_per_m2_percentile=score.price_per_m2_percentile,
            days_on_market=score.days_on_market or 0,
            price_drop_pct=score.price_drop_pct,
        )
        score.is_hot = is_hot_offer(
            days_on_market=score.days_on_market or 0,
            price_per_m2_percentile=score.price_per_m2_percentile,
            hot_max_days=hot_max_days,
        )
        updated += 1
    db.commit()
    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analyzer/test_scoring.py -v
```
Expected: 13 PASSED

- [ ] **Step 5: Commit**

```bash
git add analyzer/scoring.py tests/analyzer/test_scoring.py
git commit -m "feat: analyzer scoring — combined score + hot offer flag"
```

---

### Task 3: analyzer/alerts.py + tests

**Files:**
- Create: `analyzer/alerts.py`
- Create: `tests/analyzer/test_alerts.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analyzer/test_alerts.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from shared.models import SearchConfig, Listing, ListingScore
from analyzer.alerts import (
    build_hot_alert_body,
    build_daily_digest_body,
    send_hot_alerts,
)

UTC = timezone.utc


def add_scored_listing(db, hash_id, price, ppm2_pct, days, is_hot=True, combined=85.0, alerted_at=None):
    now = datetime.now(UTC)
    listing = Listing(
        hash_id=hash_id,
        name=f"Listing {hash_id}",
        price_czk=price,
        area_m2=80,
        price_per_m2=price / 80,
        locality="Praha 2 - Vinohrady",
        locality_district_id=5007,
        category_main_cb=1,
        category_type_cb=1,
        is_active=True,
        first_seen_at=now - timedelta(days=days),
        last_seen_at=now,
    )
    db.add(listing)
    db.flush()
    score = ListingScore(
        hash_id=hash_id,
        price_percentile=10.0,
        price_per_m2_percentile=ppm2_pct,
        days_on_market=days,
        had_price_drop=False,
        is_hot=is_hot,
        combined_score=combined,
        alerted_at=alerted_at,
        computed_at=now,
    )
    db.add(score)
    db.commit()
    return listing, score


def test_build_hot_alert_body_contains_key_info():
    listing = MagicMock()
    listing.hash_id = 12345
    listing.name = "Byt 3+kk, 80 m²"
    listing.price_czk = 4_500_000
    listing.price_per_m2 = 56_250.0
    listing.locality = "Praha 2"

    score = MagicMock()
    score.price_percentile = 8.5
    score.price_per_m2_percentile = 12.3
    score.days_on_market = 4
    score.combined_score = 87.2

    body = build_hot_alert_body(listing, score)
    assert "Byt 3+kk" in body
    assert "4 500 000" in body or "4500000" in body
    assert "Praha 2" in body
    assert "87" in body
    assert "sreality.cz" in body


def test_build_daily_digest_body_contains_top_bargains():
    entries = [
        {"name": f"Listing {i}", "combined_score": 90 - i, "price_czk": 4_000_000 + i * 100_000}
        for i in range(10)
    ]
    body = build_daily_digest_body(
        top_bargains=entries,
        new_count=5,
        price_drop_count=3,
    )
    assert "Listing 0" in body
    assert "new" in body.lower() or "5" in body
    assert "3" in body


def test_send_hot_alerts_sends_for_unalerted_hot_listings(db):
    add_scored_listing(db, hash_id=7001, price=3_000_000, ppm2_pct=15.0, days=3, is_hot=True, combined=88.0)
    with patch("analyzer.alerts.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        count = send_hot_alerts(
            db,
            smtp_host="smtp.test",
            smtp_port=587,
            smtp_user="user@test.com",
            smtp_password="pass",
            alert_email="alert@test.com",
            bargain_threshold=70.0,
        )
    assert count == 1
    mock_smtp.sendmail.assert_called_once()


def test_send_hot_alerts_skips_already_alerted(db):
    add_scored_listing(
        db, hash_id=7002, price=3_000_000, ppm2_pct=15.0, days=3,
        is_hot=True, combined=88.0,
        alerted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    with patch("analyzer.alerts.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        count = send_hot_alerts(
            db,
            smtp_host="smtp.test", smtp_port=587,
            smtp_user="u", smtp_password="p", alert_email="a@b.com",
            bargain_threshold=70.0,
        )
    assert count == 0


def test_send_hot_alerts_skips_below_threshold(db):
    add_scored_listing(db, hash_id=7003, price=3_000_000, ppm2_pct=15.0, days=3, is_hot=True, combined=50.0)
    with patch("analyzer.alerts.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        count = send_hot_alerts(
            db,
            smtp_host="smtp.test", smtp_port=587,
            smtp_user="u", smtp_password="p", alert_email="a@b.com",
            bargain_threshold=70.0,
        )
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analyzer/test_alerts.py -v
```
Expected: `ImportError: No module named 'analyzer.alerts'`

- [ ] **Step 3: Write `analyzer/alerts.py`**

```python
import smtplib
import logging
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from sqlalchemy.orm import Session

from shared.models import Listing, ListingScore

logger = logging.getLogger(__name__)
UTC = timezone.utc


def build_hot_alert_body(listing: Any, score: Any) -> str:
    price_fmt = f"{listing.price_czk:,}".replace(",", " ")
    link = f"https://www.sreality.cz/detail/prodej/byt/{listing.hash_id}"
    return (
        f"Hot offer: {listing.name}\n\n"
        f"Price: {price_fmt} CZK\n"
        f"Price/m²: {listing.price_per_m2:,.0f} CZK/m²\n"
        f"Location: {listing.locality}\n"
        f"Price percentile: {score.price_percentile:.1f}th\n"
        f"Price/m² percentile: {score.price_per_m2_percentile:.1f}th\n"
        f"Days on market: {score.days_on_market}\n"
        f"Bargain score: {score.combined_score:.1f}/100\n\n"
        f"Link: {link}\n"
    )


def build_daily_digest_body(
    top_bargains: list[dict],
    new_count: int,
    price_drop_count: int,
) -> str:
    lines = [
        "Reality Agent — Daily Digest",
        "=" * 40,
        f"New listings in last 24h: {new_count}",
        f"Listings with price drops: {price_drop_count}",
        "",
        "Top 10 bargains by score:",
        "-" * 40,
    ]
    for i, b in enumerate(top_bargains[:10], 1):
        price_fmt = f"{b['price_czk']:,}".replace(",", " ")
        lines.append(f"{i}. {b['name']} — {price_fmt} CZK — score {b['combined_score']:.1f}")
    return "\n".join(lines)


def _send_email(
    subject: str,
    body: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    alert_email: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = alert_email
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, alert_email, msg.as_string())


def send_hot_alerts(
    db: Session,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    alert_email: str,
    bargain_threshold: float,
) -> int:
    candidates = (
        db.query(Listing, ListingScore)
        .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
        .filter(
            ListingScore.is_hot == True,
            ListingScore.combined_score >= bargain_threshold,
            ListingScore.alerted_at == None,
        )
        .all()
    )
    sent = 0
    for listing, score in candidates:
        try:
            body = build_hot_alert_body(listing, score)
            _send_email(
                subject=f"🔥 Hot offer: {listing.name}",
                body=body,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_user=smtp_user,
                smtp_password=smtp_password,
                alert_email=alert_email,
            )
            score.alerted_at = datetime.now(UTC)
            db.commit()
            sent += 1
        except Exception:
            logger.exception("Failed to send hot alert for hash_id=%s", listing.hash_id)
    return sent


def send_daily_digest(
    db: Session,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    alert_email: str,
    bargain_threshold: float,
) -> None:
    from datetime import timedelta
    now = datetime.now(UTC)
    yesterday = now - timedelta(hours=24)

    new_count = (
        db.query(Listing)
        .filter(Listing.first_seen_at >= yesterday, Listing.is_active == True)
        .count()
    )
    price_drop_count = (
        db.query(ListingScore)
        .filter(ListingScore.had_price_drop == True)
        .count()
    )
    top_bargains = (
        db.query(Listing, ListingScore)
        .join(ListingScore, Listing.hash_id == ListingScore.hash_id)
        .filter(
            Listing.is_active == True,
            ListingScore.combined_score >= bargain_threshold,
        )
        .order_by(ListingScore.combined_score.desc())
        .limit(10)
        .all()
    )
    entries = [
        {
            "name": l.name,
            "price_czk": l.price_czk or 0,
            "combined_score": s.combined_score or 0.0,
        }
        for l, s in top_bargains
    ]
    body = build_daily_digest_body(entries, new_count, price_drop_count)
    try:
        _send_email(
            subject="Reality Agent — Daily Digest",
            body=body,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            alert_email=alert_email,
        )
    except Exception:
        logger.exception("Failed to send daily digest")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analyzer/test_alerts.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add analyzer/alerts.py tests/analyzer/test_alerts.py
git commit -m "feat: analyzer email alerts — hot offer + daily digest"
```

---

### Task 4: analyzer/main.py

**Files:**
- Create: `analyzer/main.py`

No separate test for main.py — it's an entrypoint that wires together tested components. Verify manually by inspecting startup logs.

- [ ] **Step 1: Write `analyzer/main.py`**

```python
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from shared.config import settings
from shared.db import SessionLocal
from analyzer.signals import compute_signals
from analyzer.scoring import compute_scores
from analyzer.alerts import send_hot_alerts, send_daily_digest

logger = logging.getLogger(__name__)


def run_analysis() -> None:
    logger.info("Running analysis")
    db = SessionLocal()
    try:
        compute_signals(db)
        compute_scores(db, settings.bargain_score_threshold, settings.hot_offer_max_days)
        if settings.smtp_user:
            send_hot_alerts(
                db,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                alert_email=settings.alert_email,
                bargain_threshold=settings.bargain_score_threshold,
            )
        logger.info("Analysis complete")
    except Exception:
        logger.exception("Analysis failed")
    finally:
        db.close()


def run_daily_digest() -> None:
    if not settings.smtp_user:
        return
    db = SessionLocal()
    try:
        send_daily_digest(
            db,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
            alert_email=settings.alert_email,
            bargain_threshold=settings.bargain_score_threshold,
        )
    finally:
        db.close()


scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        run_analysis,
        "interval",
        hours=settings.scrape_interval_hours,
        id="analysis",
    )
    scheduler.add_job(
        run_daily_digest,
        "cron",
        hour=7,
        minute=0,
        id="daily_digest",
    )
    scheduler.start()
    logger.info("Analyzer scheduler started")
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/run")
def trigger_analysis():
    run_analysis()
    return {"status": "ok"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("analyzer.main:app", host="0.0.0.0", port=8081, log_level="info")
```

- [ ] **Step 2: Run all analyzer tests**

```bash
pytest tests/analyzer/ -v
```
Expected: 26 PASSED

- [ ] **Step 3: Commit**

```bash
git add analyzer/main.py
git commit -m "feat: analyzer entrypoint — FastAPI /run endpoint + APScheduler"
```
