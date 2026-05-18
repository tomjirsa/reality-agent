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
