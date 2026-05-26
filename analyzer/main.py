import logging
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from shared.config import settings
from shared.db import SessionLocal
from analyzer.signals import compute_signals
from analyzer.scoring import compute_scores
from analyzer.snapshots import create_market_snapshot
from analyzer.alerts import send_hot_alerts, send_daily_digest

logger = logging.getLogger(__name__)


def run_analysis() -> None:
    logger.info("Running analysis")
    db = SessionLocal()
    try:
        compute_signals(db)
        create_market_snapshot(db)
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
    except Exception:
        logger.exception("Daily digest failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
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


@app.post("/alerts/evaluate/{search_config_id}")
def evaluate_alerts(search_config_id: int):
    from dashboard.scoring import compute_live_score  # lazy import
    from shared.models import SearchConfig, Listing, ListingScore, ListingSearchConfig

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("analyzer.main:app", host="0.0.0.0", port=8081, log_level="info")
