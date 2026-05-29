import pytest
from unittest.mock import MagicMock
from scraper.search import search_page, search_all, build_search_params
from shared.models import SearchConfig
from datetime import datetime, timezone


def make_config(**kwargs):
    defaults = dict(
        id=1,
        name="Test",
        category_main_cb=1,
        category_type_cb=1,
        category_sub_cb=None,
        locality_region_id=None,
        locality_district_id=5007,
        czk_price_min=None,
        czk_price_max=None,
        usable_area_min=None,
        usable_area_max=None,
        ownership=None,
        no_auction=True,
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    config = MagicMock(spec=SearchConfig)
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


def make_estate(hash_id=1001, price=5_000_000, locality="Praha 2"):
    return {
        "hash_id": hash_id,
        "price_czk": price,
        "locality": {"city": locality, "citypart": locality, "district_id": 5007},
    }


def make_search_response(estates, total):
    return {"pagination": {"total": total}, "results": estates}


def test_build_search_params_basic():
    config = make_config()
    params = build_search_params(config, from_offset=0)
    assert params["category_main_cb"] == 1
    assert params["category_type_cb"] == 1
    assert params["locality_district_id"] == 5007
    assert params["no_auction"] == 1
    assert params["limit"] == 20
    assert params["offset"] == 0


def test_build_search_params_with_price_range():
    config = make_config(czk_price_min=3_000_000, czk_price_max=6_000_000)
    params = build_search_params(config, from_offset=20)
    assert params["czk_price_summary_min"] == 3_000_000
    assert params["czk_price_summary_max"] == 6_000_000
    assert params["offset"] == 20


def test_build_search_params_omits_none_values():
    config = make_config(locality_region_id=None, locality_district_id=None)
    params = build_search_params(config, from_offset=0)
    assert "locality_region_id" not in params
    assert "locality_district_id" not in params


def test_search_page_returns_estates():
    config = make_config()
    fake_response = make_search_response([make_estate(1001), make_estate(1002)], total=2)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_client.get.return_value = mock_resp

    estates, total = search_page(mock_client, config, from_offset=0)
    assert len(estates) == 2
    assert estates[0]["hash_id"] == 1001
    assert total == 2


def test_search_page_empty_results():
    config = make_config()
    fake_response = make_search_response([], total=0)
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_response
    mock_client.get.return_value = mock_resp

    estates, total = search_page(mock_client, config, from_offset=0)
    assert estates == []
    assert total == 0


def test_search_all_paginates():
    config = make_config()
    page1 = make_search_response([make_estate(i) for i in range(20)], total=25)
    page2 = make_search_response([make_estate(i) for i in range(20, 25)], total=25)

    mock_client = MagicMock()
    responses = []
    for data in [page1, page2]:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = data
        responses.append(mock_resp)
    mock_client.get.side_effect = responses

    all_estates = search_all(mock_client, config)
    assert len(all_estates) == 25
    assert mock_client.get.call_count == 2
