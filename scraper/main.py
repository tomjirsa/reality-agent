import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import SessionLocal
from shared.models import Listing, ListingPriceHistory, SearchConfig, ScrapeRun, ListingSearchConfig
from scraper.browser import browser_client
from scraper.search import search_all
from scraper.detail import fetch_detail

logger = logging.getLogger(__name__)
UTC = timezone.utc
_scrape_lock = threading.Lock()


def create_scrape_run(db: Session, config: SearchConfig) -> ScrapeRun:
    run = ScrapeRun(
        search_config_id=config.id,
        started_at=datetime.now(UTC),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_scrape_run(
    db: Session,
    run: ScrapeRun,
    listings_found: int,
    listings_new: int,
    listings_updated: int,
    listings_removed: int,
    error: str | None = None,
) -> None:
    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    run.listings_updated = listings_updated
    run.listings_removed = listings_removed
    run.status = "error" if error else "success"
    run.error_message = error
    db.commit()


def _record_config_link(db: Session, hash_id: int, search_config_id: int) -> None:
    exists = db.query(ListingSearchConfig).filter_by(
        hash_id=hash_id, search_config_id=search_config_id
    ).first()
    if not exists:
        db.add(ListingSearchConfig(hash_id=hash_id, search_config_id=search_config_id))


def upsert_listings(
    db: Session, config: SearchConfig, details: list[dict]
) -> dict[str, int]:
    stats = {"new": 0, "updated": 0}
    now = datetime.now(UTC)
    for d in details:
        existing = db.query(Listing).filter_by(hash_id=d["hash_id"]).first()
        if existing is None:
            listing = Listing(
                hash_id=d["hash_id"],
                name=d["name"],
                price_czk=d["price_czk"],
                area_m2=d["area_m2"],
                price_per_m2=d["price_per_m2"],
                locality=d["locality"],
                locality_district_id=d["locality_district_id"],
                locality_region_id=d["locality_region_id"],
                floor=d["floor"],
                building_type=d["building_type"],
                condition=d["condition"],
                ownership=d["ownership"],
                category_main_cb=config.category_main_cb,
                category_type_cb=config.category_type_cb,
                is_active=True,
                is_new_flag=d["is_new_flag"],
                first_seen_at=now,
                last_seen_at=now,
                raw_json=d["raw_json"],
                energy_class=d.get("energy_class"),
                has_elevator=d.get("has_elevator"),
                has_outdoor_space=d.get("has_outdoor_space"),
                has_parking=d.get("has_parking"),
                has_cellar=d.get("has_cellar"),
                year_built=d.get("year_built"),
                land_area_m2=d.get("land_area_m2"),
            )
            db.add(listing)
            stats["new"] += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            existing.raw_json = d["raw_json"]
            existing.energy_class = d.get("energy_class")
            existing.has_elevator = d.get("has_elevator")
            existing.has_outdoor_space = d.get("has_outdoor_space")
            existing.has_parking = d.get("has_parking")
            existing.has_cellar = d.get("has_cellar")
            existing.year_built = d.get("year_built")
            existing.land_area_m2 = d.get("land_area_m2")
            if existing.price_czk != d["price_czk"]:
                if existing.price_czk is not None:
                    history = ListingPriceHistory(
                        hash_id=existing.hash_id,
                        price_czk=existing.price_czk,
                        price_per_m2=existing.price_per_m2,
                        recorded_at=now,
                    )
                    db.add(history)
                existing.price_czk = d["price_czk"]
                existing.price_per_m2 = d["price_per_m2"]
                stats["updated"] += 1
        _record_config_link(db, d["hash_id"], config.id)
    db.commit()
    return stats


def detect_removals(
    db: Session, config: SearchConfig, current_hash_ids: set[int]
) -> int:
    # Find listings this config previously found that are no longer in results
    all_links = (
        db.query(ListingSearchConfig)
        .filter(ListingSearchConfig.search_config_id == config.id)
        .all()
    )
    gone_hash_ids = {link.hash_id for link in all_links if link.hash_id not in current_hash_ids}
    if not gone_hash_ids:
        return 0

    # Remove config links for listings no longer found by this config
    db.query(ListingSearchConfig).filter(
        ListingSearchConfig.search_config_id == config.id,
        ListingSearchConfig.hash_id.in_(gone_hash_ids),
    ).delete(synchronize_session=False)

    # Only mark globally inactive when no other config still claims the listing
    now = datetime.now(UTC)
    count = 0
    for hash_id in gone_hash_ids:
        still_linked = db.query(ListingSearchConfig).filter_by(hash_id=hash_id).count()
        if still_linked == 0:
            listing = db.query(Listing).filter_by(hash_id=hash_id, is_active=True).first()
            if listing:
                listing.is_active = False
                listing.removed_at = now
                if listing.first_seen_at:
                    listing.days_to_sell = (
                        now.replace(tzinfo=None) - listing.first_seen_at.replace(tzinfo=None)
                    ).days
                count += 1

    db.commit()
    return count


def run_scrape(db: Session, config: SearchConfig) -> None:
    run = create_scrape_run(db, config)
    logger.info("Starting scrape for config: %s", config.name)
    try:
        with browser_client() as client:
            raw_estates = search_all(client, config)
            run.progress_total = len(raw_estates)
            db.commit()
            current_hash_ids = {e["hash_id"] for e in raw_estates}

            existing_prices = {
                row.hash_id: row.price_czk
                for row in db.query(Listing.hash_id, Listing.price_czk)
                .filter(Listing.hash_id.in_(current_hash_ids))
                .all()
            }
            stats = {"new": 0, "updated": 0}
            for estate in raw_estates:
                hid = estate["hash_id"]
                price = estate.get("price_czk")
                if hid not in existing_prices or existing_prices[hid] != price:
                    detail = fetch_detail(client, hid)
                    if detail is None:
                        continue
                    s = upsert_listings(db, config, [detail])
                    stats["new"] += s["new"]
                    stats["updated"] += s["updated"]
                else:
                    db.query(Listing).filter_by(hash_id=hid).update(
                        {"last_seen_at": datetime.now(UTC)}
                    )
                    _record_config_link(db, hid, config.id)
                run.progress_done = (run.progress_done or 0) + 1
                db.commit()

            removed = detect_removals(db, config, current_hash_ids) if current_hash_ids else 0

        finish_scrape_run(
            db, run,
            listings_found=len(current_hash_ids),
            listings_new=stats["new"],
            listings_updated=stats["updated"],
            listings_removed=removed,
        )
        logger.info(
            "Scrape complete for %s: found=%d new=%d updated=%d removed=%d",
            config.name, len(current_hash_ids), stats["new"], stats["updated"], removed,
        )
    except Exception as exc:
        finish_scrape_run(
            db, run,
            listings_found=0, listings_new=0, listings_updated=0, listings_removed=0,
            error=str(exc),
        )
        logger.exception("Scrape failed for config %s", config.name)


def cleanup_stale_runs(db: Session) -> None:
    stale = db.query(ScrapeRun).filter_by(status="running").all()
    now = datetime.now(UTC)
    for run in stale:
        run.status = "aborted"
        run.finished_at = now
    if stale:
        db.commit()
        logger.info("Marked %d stale scrape run(s) as aborted", len(stale))


def run_pipeline(config_id: int | None = None) -> None:
    if not _scrape_lock.acquire(blocking=False):
        logger.info("Scrape already running, skipping")
        return
    db = SessionLocal()
    try:
        if config_id is not None:
            configs = db.query(SearchConfig).filter_by(active=True, id=config_id).all()
        else:
            configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
        # Enrichment and analysis always run after any scrape, whether full or per-config.
        if settings.mapy_api_key:
            from enricher.main import enrich_all_configs
            enrich_all_configs(db, settings.mapy_api_key)
        try:
            httpx.post(f"{settings.analyzer_url}/run", timeout=30)
        except Exception:
            logger.exception("Failed to trigger analyzer after pipeline")
    except Exception:
        logger.exception("Pipeline failed")
    finally:
        db.close()
        _scrape_lock.release()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        cleanup_stale_runs(db)
    finally:
        db.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=settings.scrape_interval_hours,
        next_run_time=datetime.now(),
        id="scrape",
    )
    scheduler.start()
    logger.info("Scraper starting, interval=%dh", settings.scrape_interval_hours)
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/run")
def trigger_run(background_tasks: BackgroundTasks, config_id: int | None = None):
    background_tasks.add_task(run_pipeline, config_id=config_id)
    return {"status": "triggered"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("scraper.main:app", host="0.0.0.0", port=8082, log_level="info")
