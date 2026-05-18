import re
import httpx
from typing import Any, Optional

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
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else None


def parse_detail(data: dict) -> dict[str, Any]:
    items = data.get("items", [])
    locality = data.get("locality", {})
    if isinstance(locality, str):
        locality_address = locality
        district_id = None
        region_id = None
    else:
        locality_address = locality.get("address")
        district_id = locality.get("district_id")
        region_id = locality.get("region_id")

    area_raw = extract_item_value(items, "Plocha")
    area_m2 = _parse_area(area_raw)
    price_czk = data.get("price_czk")
    price_per_m2 = price_czk / area_m2 if (price_czk and area_m2) else None

    return {
        "hash_id": data["hash_id"],
        "name": data.get("name", ""),
        "price_czk": price_czk,
        "area_m2": area_m2,
        "price_per_m2": price_per_m2,
        "locality": locality_address,
        "locality_district_id": district_id,
        "locality_region_id": region_id,
        "floor": extract_item_value(items, "Podlaží"),
        "building_type": extract_item_value(items, "Typ budovy"),
        "condition": extract_item_value(items, "Stav objektu"),
        "ownership": extract_item_value(items, "Vlastnictví"),
        "is_new_flag": bool(data.get("is_new", False)),
        "raw_json": data,
    }


def fetch_detail(client: httpx.Client, hash_id: int) -> dict[str, Any]:
    url = f"{BASE_URL}/{hash_id}"
    resp = client.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_detail(resp.json())
