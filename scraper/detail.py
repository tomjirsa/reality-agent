import time
import random
import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)
RETRY_DELAYS = [5, 15, 30]

BASE_URL = "https://www.sreality.cz/api/v1/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _named_value(obj: Optional[dict]) -> Optional[str]:
    """Return obj['name'] when the object represents a real selection (value > 0), else None."""
    if not obj or obj.get("value", 0) == 0:
        return None
    return obj.get("name")


def _build_locality_string(locality: dict) -> Optional[str]:
    street = locality.get("street") or ""
    citypart = locality.get("citypart") or ""
    city = locality.get("city") or ""
    parts = list(dict.fromkeys(filter(None, [street, citypart, city])))
    return ", ".join(parts) if parts else None


def parse_detail(data: dict, hash_id: int) -> dict[str, Any]:
    locality = data.get("locality") or {}
    price_czk = data.get("price_czk")
    area_m2 = data.get("usable_area")
    price_per_m2 = price_czk / area_m2 if (price_czk and area_m2) else None

    elevator = data.get("elevator")
    elev_value = elevator.get("value", 0) if elevator else 0
    has_elevator = None if elev_value == 0 else (elev_value == 1)

    return {
        "hash_id": hash_id,
        "name": data.get("advert_name", ""),
        "price_czk": price_czk,
        "area_m2": area_m2,
        "price_per_m2": price_per_m2,
        "locality": _build_locality_string(locality),
        "locality_district_id": locality.get("district_id"),
        "locality_region_id": locality.get("region_id"),
        "floor": data.get("floor_number"),
        "building_type": _named_value(data.get("building_type")),
        "condition": _named_value(data.get("building_condition")),
        "ownership": _named_value(data.get("ownership")),
        "is_new_flag": bool(data.get("is_new_flag", False)),
        "energy_class": _named_value(data.get("energy_efficiency_rating_cb")),
        "has_elevator": has_elevator,
        "has_outdoor_space": bool(
            data.get("balcony") or data.get("loggia") or data.get("terrace")
        ),
        "has_parking": bool(data.get("garage") or data.get("parking_lots")),
        "has_cellar": data.get("cellar") or False,
        "year_built": data.get("object_age"),
        "land_area_m2": data.get("building_area"),
        "raw_json": data,
    }


def fetch_detail(client: httpx.Client, hash_id: int) -> dict[str, Any]:
    url = f"{BASE_URL}/{hash_id}"
    time.sleep(random.uniform(0.01, 0.2))
    for attempt, retry_wait in enumerate([0] + RETRY_DELAYS):
        if retry_wait:
            logger.warning("Rate limited, waiting %ds before retry (attempt %d)", retry_wait, attempt)
            time.sleep(retry_wait)
        resp = client.get(url, headers=HEADERS, timeout=30)
        if resp.status_code in (429, 503):
            continue
        if resp.status_code in (404, 410):
            logger.info("Listing %s is gone (%d), skipping", hash_id, resp.status_code)
            return None
        resp.raise_for_status()
        return parse_detail(resp.json()["result"], hash_id=hash_id)
    resp.raise_for_status()
    return parse_detail(resp.json()["result"], hash_id=hash_id)
