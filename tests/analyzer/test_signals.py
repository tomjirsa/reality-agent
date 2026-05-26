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
