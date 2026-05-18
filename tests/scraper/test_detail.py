import pytest
from unittest.mock import MagicMock
from scraper.detail import fetch_detail, parse_detail, extract_item_value


# Matches the current sreality.cz API response structure:
# - hash_id not present (passed separately)
# - locality is {"value": "address string"}
# - price_czk is {"value_raw": N, ...}
# - locality_district_id is top-level
# - area field is "Užitná ploch" (truncated by API)
# - building type field is "Stavba"
SAMPLE_DETAIL_RESPONSE = {
    "name": "Prodej bytu 3+kk, 80 m²",
    "price_czk": {"value_raw": 5_900_000, "name": "Celková cena", "value": "5 900 000", "unit": ""},
    "is_new": False,
    "locality": {"name": "Adresa", "value": "Praha 2 - Vinohrady, Blanická", "accuracy": "address"},
    "locality_district_id": 5007,
    "items": [
        {"name": "Užitná ploch", "value": "80"},
        {"name": "Podlaží", "value": "3. podlaží z 6"},
        {"name": "Stavba", "value": "Cihlová"},
        {"name": "Stav objektu", "value": "Velmi dobrý"},
        {"name": "Vlastnictví", "value": "Osobní"},
    ],
}

HASH_ID = 1234567890


def test_extract_item_value_found():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Užitná ploch") == "80"
    assert extract_item_value(items, "Stavba") == "Cihlová"


def test_extract_item_value_missing():
    items = SAMPLE_DETAIL_RESPONSE["items"]
    assert extract_item_value(items, "Neexistuje") is None


def test_parse_detail_maps_fields():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["hash_id"] == HASH_ID
    assert result["name"] == "Prodej bytu 3+kk, 80 m²"
    assert result["price_czk"] == 5_900_000
    assert result["area_m2"] == 80
    assert result["locality"] == "Praha 2 - Vinohrady, Blanická"
    assert result["locality_district_id"] == 5007
    assert result["locality_region_id"] is None
    assert result["floor"] == "3. podlaží z 6"
    assert result["building_type"] == "Cihlová"
    assert result["condition"] == "Velmi dobrý"
    assert result["ownership"] == "Osobní"
    assert result["is_new_flag"] is False
    assert result["raw_json"] == SAMPLE_DETAIL_RESPONSE


def test_parse_detail_name_as_dict():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["name"] = {"name": "Název", "value": "Prodej rodinného domu 128 m²"}
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["name"] == "Prodej rodinného domu 128 m²"


def test_parse_detail_area_extraction():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = [{"name": "Užitná ploch", "value": "120"}]
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["area_m2"] == 120


def test_parse_detail_area_legacy_field_name():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = [{"name": "Plocha", "value": "75 m²"}]
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["area_m2"] == 75


def test_parse_detail_missing_area_returns_none():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["area_m2"] is None


def test_fetch_detail_calls_correct_url():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = SAMPLE_DETAIL_RESPONSE
    mock_client.get.return_value = mock_resp

    result = fetch_detail(mock_client, HASH_ID)
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    assert str(HASH_ID) in call_args[0][0]
    assert result["hash_id"] == HASH_ID


def test_parse_detail_price_per_m2_computed():
    result = parse_detail(SAMPLE_DETAIL_RESPONSE, hash_id=HASH_ID)
    assert result["price_per_m2"] == pytest.approx(5_900_000 / 80)


def test_parse_detail_price_per_m2_none_if_no_area():
    response = dict(SAMPLE_DETAIL_RESPONSE)
    response["items"] = []
    result = parse_detail(response, hash_id=HASH_ID)
    assert result["price_per_m2"] is None
