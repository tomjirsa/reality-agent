import smtplib
import logging
from datetime import datetime, timezone, timedelta
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
                subject=f"Hot offer: {listing.name}",
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
