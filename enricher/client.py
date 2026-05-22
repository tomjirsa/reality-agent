import logging
import httpx

logger = logging.getLogger(__name__)

MAPY_BASE = "https://api.mapy.cz/v1"

TRAVEL_MODE_MAP: dict[str, str] = {
    "car": "car_fast_traffic",
    "walk": "foot_fast",
    "bike": "bike_road",
    "transit": "public_transport",
}


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lon) for address, or None on any failure."""
    try:
        resp = httpx.get(
            f"{MAPY_BASE}/geocode",
            params={"apikey": api_key, "query": address, "lang": "cs", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            logger.warning("Geocode returned no results for: %s", address)
            return None
        pos = items[0]["position"]
        return float(pos["lat"]), float(pos["lon"])
    except httpx.TimeoutException:
        logger.warning("Geocode timeout for address: %s", address)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("Geocode HTTP %s for address: %s", exc.response.status_code, address)
        return None
    except KeyError:
        logger.warning("Geocode unexpected response shape for address: %s", address)
        return None


def route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str,
    api_key: str,
    hash_id: int | None = None,
) -> dict | None:
    """Return {"distance_m": int, "duration_s": int} or None on any failure."""
    route_type = TRAVEL_MODE_MAP.get(mode, TRAVEL_MODE_MAP["car"])
    try:
        resp = httpx.get(
            f"{MAPY_BASE}/routing/route",
            params={
                "apikey": api_key,
                "lang": "cs",
                "routeType": route_type,
                "start": f"{origin_lon},{origin_lat}",
                "end": f"{dest_lon},{dest_lat}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        summary = resp.json()["routeSummary"]
        return {"distance_m": summary["distance"], "duration_s": summary["duration"]}
    except httpx.TimeoutException:
        logger.warning("Route timeout for hash_id=%s", hash_id)
        return None
    except httpx.HTTPStatusError as exc:
        sc = exc.response.status_code
        if sc >= 500:
            logger.warning("Route HTTP 5xx (%s) for hash_id=%s", sc, hash_id)
        else:
            logger.warning("Route HTTP 4xx (%s) for hash_id=%s", sc, hash_id)
        return None
    except KeyError:
        logger.warning("Route unexpected response shape for hash_id=%s", hash_id)
        return None
