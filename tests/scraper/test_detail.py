import pytest
from unittest.mock import MagicMock
from scraper.detail import fetch_detail, parse_detail

HASH_ID = 1234567890

SAMPLE_LOCALITY = {
    "street": "Blanická",
    "citypart": "Vinohrady",
    "city": "Praha",
    "district_id": 5007,
    "region_id": 10,
}

SAMPLE_DETAIL = {
    "advert_name": "Prodej bytu 3+kk, 80 m²",
    "price_czk": 5_900_000,
    "is_new_flag": False,
    "locality": SAMPLE_LOCALITY,
    "usable_area": 80,
    "floor_number": 3,
    "building_type": {"name": "Cihlová"},
    "building_condition": {"name": "Velmi dobrý"},
    "ownership": {"name": "Osobní"},
    "elevator": None,
    "energy_efficiency_rating_cb": None,
    "balcony": False,
    "loggia": False,
    "terrace": False,
    "garage": False,
    "parking_lots": False,
    "cellar": False,
    "object_age": None,
    "building_area": None,
}

FULL_DETAIL = {
    **SAMPLE_DETAIL,
    "floor_number": 5,
    "energy_efficiency_rating_cb": {"name": "B"},
    "elevator": {"value": 1, "name": "Ano"},
    "balcony": True,
    "garage": True,
    "cellar": True,
    "object_age": 1998,
}

HOUSE_DETAIL = {
    **SAMPLE_DETAIL,
    "locality": {
        "street": "",
        "citypart": "Líšeň",
        "city": "Brno",
        "district_id": 6202,
        "region_id": 7,
    },
    "building_area": 650,
}


def test_parse_detail_maps_core_fields():
    result = parse_detail(SAMPLE_DETAIL, hash_id=HASH_ID)
    assert result["hash_id"] == HASH_ID
    assert result["name"] == "Prodej bytu 3+kk, 80 m²"
    assert result["price_czk"] == 5_900_000
    assert result["area_m2"] == 80
    assert result["floor"] == 3
    assert result["building_type"] == "Cihlová"
    assert result["condition"] == "Velmi dobrý"
    assert result["ownership"] == "Osobní"
    assert result["is_new_flag"] is False
    assert result["raw_json"] == SAMPLE_DETAIL


def test_parse_detail_locality_string_deduplicates():
    result = parse_detail(SAMPLE_DETAIL, hash_id=HASH_ID)
    # Blanická, Vinohrady, Praha — all distinct
    assert result["locality"] == "Blanická, Vinohrady, Praha"


def test_parse_detail_locality_string_deduplicates_citypart_equals_city():
    data = {**SAMPLE_DETAIL, "locality": {
        "street": "Písečná", "citypart": "Chomutov", "city": "Chomutov",
        "district_id": 20, "region_id": 4,
    }}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["locality"] == "Písečná, Chomutov"


def test_parse_detail_locality_ids():
    result = parse_detail(SAMPLE_DETAIL, hash_id=HASH_ID)
    assert result["locality_district_id"] == 5007
    assert result["locality_region_id"] == 10


def test_parse_detail_price_per_m2_computed():
    result = parse_detail(SAMPLE_DETAIL, hash_id=HASH_ID)
    assert result["price_per_m2"] == pytest.approx(5_900_000 / 80)


def test_parse_detail_price_per_m2_none_if_no_area():
    data = {**SAMPLE_DETAIL, "usable_area": None}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["price_per_m2"] is None


def test_parse_detail_null_fields_when_absent():
    result = parse_detail(SAMPLE_DETAIL, hash_id=HASH_ID)
    assert result["energy_class"] is None
    assert result["has_elevator"] is None
    assert result["has_outdoor_space"] is False
    assert result["has_parking"] is False
    assert result["has_cellar"] is False
    assert result["year_built"] is None
    assert result["land_area_m2"] is None


def test_parse_detail_extracts_energy_class():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["energy_class"] == "B"


def test_parse_detail_extracts_elevator_true():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["has_elevator"] is True


def test_parse_detail_elevator_false_when_value_not_1():
    data = {**SAMPLE_DETAIL, "elevator": {"value": 0, "name": "Ne"}}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["has_elevator"] is False


def test_parse_detail_outdoor_space_from_balcony():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["has_outdoor_space"] is True


def test_parse_detail_outdoor_space_from_loggia():
    data = {**SAMPLE_DETAIL, "loggia": True}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["has_outdoor_space"] is True


def test_parse_detail_outdoor_space_from_terrace():
    data = {**SAMPLE_DETAIL, "terrace": True}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["has_outdoor_space"] is True


def test_parse_detail_extracts_parking():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["has_parking"] is True


def test_parse_detail_parking_from_parking_lots():
    data = {**SAMPLE_DETAIL, "parking_lots": True}
    result = parse_detail(data, hash_id=HASH_ID)
    assert result["has_parking"] is True


def test_parse_detail_extracts_cellar():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["has_cellar"] is True


def test_parse_detail_extracts_year_built():
    result = parse_detail(FULL_DETAIL, hash_id=HASH_ID)
    assert result["year_built"] == 1998


def test_parse_detail_extracts_land_area():
    result = parse_detail(HOUSE_DETAIL, hash_id=HASH_ID)
    assert result["land_area_m2"] == 650


def test_fetch_detail_unwraps_result_key():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": SAMPLE_DETAIL}
    mock_client.get.return_value = mock_resp

    result = fetch_detail(mock_client, HASH_ID)
    assert result["hash_id"] == HASH_ID
    assert result["price_czk"] == 5_900_000


def test_fetch_detail_calls_v1_url():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": SAMPLE_DETAIL}
    mock_client.get.return_value = mock_resp

    fetch_detail(mock_client, HASH_ID)
    url = mock_client.get.call_args[0][0]
    assert "/api/v1/estates/" in url
    assert str(HASH_ID) in url
