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
