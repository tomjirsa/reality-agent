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
