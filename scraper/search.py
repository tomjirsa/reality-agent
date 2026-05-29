import logging
import httpx
from typing import Any
from shared.models import SearchConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sreality.cz/api/v1/estates/search"
PER_PAGE = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def build_search_params(config: SearchConfig, from_offset: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "category_main_cb": config.category_main_cb,
        "category_type_cb": config.category_type_cb,
        "limit": PER_PAGE,
        "offset": from_offset,
    }
    if config.category_sub_cb:
        ids = str(config.category_sub_cb).split("|")
        params["category_sub_cb"] = ids if len(ids) > 1 else ids[0]
    if config.locality_region_id is not None:
        params["locality_region_id"] = config.locality_region_id
    if config.locality_district_id:
        ids = str(config.locality_district_id).split("|")
        params["locality_district_id"] = ids if len(ids) > 1 else ids[0]
    if config.czk_price_min is not None:
        params["czk_price_summary_min"] = config.czk_price_min
    if config.czk_price_max is not None:
        params["czk_price_summary_max"] = config.czk_price_max
    if config.usable_area_min is not None:
        params["usable_area_min"] = config.usable_area_min
    if config.usable_area_max is not None:
        params["usable_area_max"] = config.usable_area_max
    if config.estate_area_min is not None:
        params["estate_area_from"] = config.estate_area_min
    if config.estate_area_max is not None:
        params["estate_area_to"] = config.estate_area_max
    if config.ownership is not None:
        params["ownership"] = config.ownership
    if config.no_auction:
        params["no_auction"] = 1
    return params


def search_page(
    client: httpx.Client, config: SearchConfig, from_offset: int
) -> tuple[list[dict], int]:
    params = build_search_params(config, from_offset)
    resp = client.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    estates = data.get("results", [])
    total = data.get("pagination", {}).get("total", 0)
    return estates, total


def search_all(client: httpx.Client, config: SearchConfig) -> list[dict]:
    all_estates = []
    offset = 0
    while True:
        estates, total = search_page(client, config, from_offset=offset)
        all_estates.extend(estates)
        offset += PER_PAGE
        if offset >= total or not estates:
            break
    return all_estates
