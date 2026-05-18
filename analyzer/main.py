import logging
from contextlib import asynccontextmanager

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
