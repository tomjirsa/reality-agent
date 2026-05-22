import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared.models import Listing, ListingDistance, ListingSearchConfig, SearchConfig
from enricher.client import route

logger = logging.getLogger(__name__)
UTC = timezone.utc
ENRICH_DELAY = 0.2


def _extract_gps(raw_json: dict | None) -> tuple[float, float] | None:
    if not raw_json:
        return None
    map_obj = raw_json.get("map", {})
    if not isinstance(map_obj, dict):
        return None
    lat = map_obj.get("lat")
    lon = map_obj.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def enrich_all_configs(db: Session, api_key: str) -> None:
    configs = (
        db.query(SearchConfig)
        .filter(
            SearchConfig.active == True,
            SearchConfig.destination_lat.isnot(None),
            SearchConfig.destination_lon.isnot(None),
            SearchConfig.travel_mode.isnot(None),
        )
        .all()
    )
    for config in configs:
        _enrich_config(db, config, api_key)


def _enrich_config(db: Session, config: SearchConfig, api_key: str) -> None:
    enriched_ids = {
        row.hash_id
        for row in db.query(ListingDistance.hash_id).filter_by(search_config_id=config.id).all()
    }
    pending_ids = [
        row.hash_id
        for row in db.query(ListingSearchConfig.hash_id).filter_by(search_config_id=config.id).all()
        if row.hash_id not in enriched_ids
    ]
    if not pending_ids:
        return

    listings = {
        lst.hash_id: lst
        for lst in db.query(Listing).filter(Listing.hash_id.in_(pending_ids)).all()
    }
    logger.info("Enriching %d listings for config '%s'", len(pending_ids), config.name)

    for hash_id in pending_ids:
        listing = listings.get(hash_id)
        if listing is None:
            continue
        coords = _extract_gps(listing.raw_json)
        if coords is None:
            logger.warning("No GPS in raw_json for hash_id=%s", hash_id)
            continue
        lat, lon = coords
        time.sleep(ENRICH_DELAY)
        result = route(
            origin_lat=lat,
            origin_lon=lon,
            dest_lat=config.destination_lat,
            dest_lon=config.destination_lon,
            mode=config.travel_mode,
            api_key=api_key,
            hash_id=hash_id,
        )
        if result is None:
            continue
        db.add(ListingDistance(
            hash_id=hash_id,
            search_config_id=config.id,
            travel_mode=config.travel_mode,
            distance_m=result["distance_m"],
            duration_s=result["duration_s"],
            computed_at=datetime.now(UTC),
        ))
        db.commit()
        logger.info(
            "Enriched hash_id=%s: %dm %ds", hash_id, result["distance_m"], result["duration_s"]
        )
