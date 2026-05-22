import pytest
from unittest.mock import patch, MagicMock
from enricher.client import geocode, route


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=status_code)
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_geocode_returns_lat_lon():
    mock_resp = _mock_response({
        "items": [{"position": {"lat": 50.0815, "lon": 14.4241}}]
    })
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("Václavské náměstí, Praha", "test-key")
    assert result == (50.0815, 14.4241)


def test_geocode_returns_none_on_empty_items():
    mock_resp = _mock_response({"items": []})
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("nonexistent place xyz", "test-key")
    assert result is None


def test_geocode_returns_none_on_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
        result = geocode("Praha", "test-key")
    assert result is None


def test_geocode_returns_none_on_4xx():
    mock_resp = _mock_response({}, status_code=401)
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("Praha", "bad-key")
    assert result is None


def test_route_returns_distance_and_duration():
    mock_resp = _mock_response({
        "routeSummary": {"distance": 1500, "duration": 300}
    })
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=123)
    assert result == {"distance_m": 1500, "duration_s": 300}
    params = mock_get.call_args[1]["params"]
    assert params["routeType"] == "car_fast_traffic"


def test_route_maps_travel_modes():
    mock_resp = _mock_response({"routeSummary": {"distance": 800, "duration": 600}})
    for mode, expected_type in [
        ("walk", "foot_fast"),
        ("bike", "bike_road"),
        ("transit", "public_transport"),
    ]:
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            route(50.087, 14.421, 50.075, 14.435, mode, "test-key")
        params = mock_get.call_args[1]["params"]
        assert params["routeType"] == expected_type, f"mode={mode}"


def test_route_returns_none_on_timeout():
    import httpx
    with patch("httpx.get", side_effect=httpx.TimeoutException("timeout")):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_returns_none_on_4xx():
    mock_resp = _mock_response({}, status_code=404)
    with patch("httpx.get", return_value=mock_resp):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_returns_none_on_5xx():
    mock_resp = _mock_response({}, status_code=500)
    with patch("httpx.get", return_value=mock_resp):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=99)
    assert result is None


def test_route_uses_lon_lat_order_in_params():
    mock_resp = _mock_response({"routeSummary": {"distance": 1000, "duration": 200}})
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        route(50.087, 14.421, 50.075, 14.435, "car", "test-key")
    params = mock_get.call_args[1]["params"]
    # mapy.cz expects "lon,lat" order
    assert params["start"] == "14.421,50.087"
    assert params["end"] == "14.435,50.075"


def test_geocode_returns_none_on_malformed_response():
    mock_resp = _mock_response({"items": [{"no_position_key": {}}]})
    with patch("httpx.get", return_value=mock_resp):
        result = geocode("Praha", "test-key")
    assert result is None


def test_route_returns_none_on_malformed_response():
    mock_resp = _mock_response({"no_route_summary": {}})
    with patch("httpx.get", return_value=mock_resp):
        result = route(50.087, 14.421, 50.075, 14.435, "car", "test-key", hash_id=1)
    assert result is None
