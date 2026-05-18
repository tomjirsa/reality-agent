import re
import time
import logging
import httpx
from typing import Any, Optional

logger = logging.getLogger(__name__)

DETAIL_DELAY = 0.3   # seconds between requests
RETRY_DELAYS = [5, 15, 30]  # seconds to wait after 503/429

BASE_URL = "https://www.sreality.cz/api/cs/v2/estates"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def extract_item_value(items: list[dict], name: str) -> Optional[str]:
    for item in items:
        if item.get("name") == name:
            return item.get("value")
    return None


def _parse_area(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"(\d+)", str(value))
    return int(match.group(1)) if match else None


def parse_detail(data: dict, hash_id: int) -> dict[str, Any]:
    items = data.get("items", [])

    locality_obj = data.get("locality", {})
    if isinstance(locality_obj, dict):
        locality_address = locality_obj.get("value") or locality_obj.get("address")
    else:
        locality_address = locality_obj

    # Try current and legacy Czech field names for usable area
    area_raw = (
        extract_item_value(items, "Užitná ploch")
        or extract_item_value(items, "Užitná plocha")
        or extract_item_value(items, "Plocha")
        or extract_item_value(items, "Celková plocha")
    )
    area_m2 = _parse_area(area_raw)

    price_czk_data = data.get("price_czk")
    if isinstance(price_czk_data, dict):
        price_czk = price_czk_data.get("value_raw")
    else:
        price_czk = price_czk_data

    price_per_m2 = price_czk / area_m2 if (price_czk and area_m2) else None

    return {
        "hash_id": hash_id,
        "name": data.get("name", ""),
        "price_czk": price_czk,
        "area_m2": area_m2,
        "price_per_m2": price_per_m2,
        "locality": locality_address,
        "locality_district_id": data.get("locality_district_id"),
        "locality_region_id": data.get("locality_region_id"),
        "floor": extract_item_value(items, "Podlaží"),
        "building_type": (
            extract_item_value(items, "Stavba")
            or extract_item_value(items, "Typ budovy")
        ),
        "condition": extract_item_value(items, "Stav objektu"),
        "ownership": extract_item_value(items, "Vlastnictví"),
        "is_new_flag": bool(data.get("is_new", False)),
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
        resp.raise_for_status()
        return parse_detail(resp.json(), hash_id=hash_id)
    resp.raise_for_status()  # final raise if all retries exhausted
    return parse_detail(resp.json(), hash_id=hash_id)  # unreachable but satisfies type checker
