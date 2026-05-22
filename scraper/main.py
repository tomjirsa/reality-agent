import logging
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from shared.config import settings
from shared.db import SessionLocal
from shared.models import Listing, ListingPriceHistory, SearchConfig, ScrapeRun, ListingSearchConfig
from scraper.search import search_all
from scraper.detail import fetch_detail

logger = logging.getLogger(__name__)
UTC = timezone.utc


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
            )
            db.add(listing)
            stats["new"] += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            existing.raw_json = d["raw_json"]
            if existing.price_czk != d["price_czk"]:
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
    query = (
        db.query(Listing)
        .filter(
            Listing.is_active == True,
            Listing.category_main_cb == config.category_main_cb,
            Listing.category_type_cb == config.category_type_cb,
            ~Listing.hash_id.in_(current_hash_ids),
        )
    )
    if config.locality_district_id:
        ids = [int(x) for x in config.locality_district_id.split("|") if x.strip()]
        query = query.filter(Listing.locality_district_id.in_(ids))
    elif config.locality_region_id is not None:
        query = query.filter(Listing.locality_region_id == config.locality_region_id)

    removed = query.all()
    now = datetime.now(UTC)
    for listing in removed:
        listing.is_active = False
        listing.removed_at = now
        if listing.first_seen_at:
            listing.days_to_sell = (now.replace(tzinfo=None) - listing.first_seen_at.replace(tzinfo=None)).days
    db.commit()
    return len(removed)


def run_scrape(db: Session, config: SearchConfig) -> None:
    run = create_scrape_run(db, config)
    logger.info("Starting scrape for config: %s", config.name)
    try:
        with httpx.Client() as client:
            raw_estates = search_all(client, config)
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
                    s = upsert_listings(db, config, [detail])
                    stats["new"] += s["new"]
                    stats["updated"] += s["updated"]
                else:
                    db.query(Listing).filter_by(hash_id=hid).update(
                        {"last_seen_at": datetime.now(UTC)}
                    )
                    db.commit()

            removed = detect_removals(db, config, current_hash_ids)

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


def run_pipeline() -> None:
    db = SessionLocal()
    try:
        configs = db.query(SearchConfig).filter_by(active=True).all()
        for config in configs:
            run_scrape(db, config)
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=settings.scrape_interval_hours,
        next_run_time=datetime.now(),
    )
    logger.info("Scraper starting, interval=%dh", settings.scrape_interval_hours)
    scheduler.start()
