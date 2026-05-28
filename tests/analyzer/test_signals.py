import pytest
from datetime import datetime, timezone, timedelta
from shared.models import SearchConfig, Listing, ListingPriceHistory, ListingScore, MarketSnapshot
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
