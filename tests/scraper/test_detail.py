import pytest
from unittest.mock import MagicMock
from scraper.detail import fetch_detail, parse_detail, extract_item_value


SAMPLE_DETAIL_RESPONSE = {
    "hash_id": 1234567890,
    "name": "Prodej bytu 3+kk, 80 m²",
    "price_czk": 5_900_000,
    "is_new": False,
    "locality": {
        "address": "Praha 2 - Vinohrady, Blanická",
        "district_id": 5007,
        "region_id": 10,
    },
    "items": [
        {"name": "Plocha", "value": "80 m²"},
        {"name": "Podlaží", "value": "3. podlaží z 6"},
        {"name": "Typ budovy", "value": "Cihlová"},
        {"name": "Stav objektu", "value": "Velmi dobrý"},
        {"name": "Vlastnictví", "value": "Osobní"},
    ],
}


def test_extract_item_value_found():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Plocha") == "80 m²"
    assert extract_item_value(items, "Typ budovy") == "Cihlová"


def test_extract_item_value_missing():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Neexistuje") is None


def test_parse_detail_maps_fields():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE)
    assert result["hash_id"] == 1234567890
    assert result["name"] == "Prodej bytu 3+kk, 80 m²"
    assert result["price_czk"] == 5_900_000
    assert result["area_m2"] == 80
    assert result["locality"] == "Praha 2 - Vinohrady, Blanická"
    assert result["locality_district_id"] == 5007
    assert result["locality_region_id"] == 10
    assert result["floor"] == "3. podlaží z 6"
    assert result["building_type"] == "Cihlová"
    assert result["condition"] == "Velmi dobrý"
    assert result["ownership"] == "Osobní"
    assert result["is_new_flag"] is False
    assert result["raw_json"] == SAMPLE_DETAIL_RESPONSE


def test_parse_detail_area_extraction():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = [{"name": "Plocha", "value": "120 m²"}]
    result = parse_detail(response)
    assert result["area_m2"] == 120


def test_parse_detail_missing_area_returns_none():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response)
    assert result["area_m2"] is None


def test_fetch_detail_calls_correct_url():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
    mock_client.get.return_value = mock_resp

    result = fetch_detail(mock_client, 1234567890)
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert "1234567890" in call_args[0][0]
    assert result["hash_id"] == 1234567890


def test_parse_detail_price_per_m2_computed():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE)
    assert result["price_per_m2"] == pytest.approx(5_900_000 / 80)


def test_parse_detail_price_per_m2_none_if_no_area():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response)
    assert result["price_per_m2"] is None
