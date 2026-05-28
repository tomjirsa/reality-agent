import pytest
from shared.models import ListingScore
from dashboard.scoring import compute_live_score, DEFAULT_WEIGHTS


def make_score(**kwargs):
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

    class MockListingScore:
        def __init__(self, **attrs):
            for k, v in attrs.items():
                setattr(self, k, v)

    return MockListingScore(**defaults)


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
