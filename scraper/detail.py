import time
import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)

DETAIL_DELAY = 0.3
RETRY_DELAYS = [5, 15, 30]

BASE_URL = "https://www.sreality.cz/api/v1/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


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
    has_elevator = None if elevator is None else (elevator.get("value") == 1)

    building_type_obj = data.get("building_type")
    condition_obj = data.get("building_condition")
    ownership_obj = data.get("ownership")
    energy_obj = data.get("energy_efficiency_rating_cb")

    return {
        "hash_id": hash_id,
        "name": data.get("name", ""),
        "price_czk": price_czk,
        "area_m2": area_m2,
        "price_per_m2": price_per_m2,
        "locality": _build_locality_string(locality),
        "locality_district_id": locality.get("district_id"),
        "locality_region_id": locality.get("region_id"),
        "floor": data.get("floor_number"),
        "building_type": building_type_obj.get("name") if building_type_obj else None,
        "condition": condition_obj.get("name") if condition_obj else None,
        "ownership": ownership_obj.get("name") if ownership_obj else None,
        "is_new_flag": bool(data.get("is_new_flag", False)),
        "energy_class": energy_obj.get("name") if energy_obj else None,
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
    time.sleep(DETAIL_DELAY)
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
