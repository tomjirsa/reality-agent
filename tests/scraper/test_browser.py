import pytest
from unittest.mock import MagicMock, patch
import httpx

from scraper.browser import _login, browser_client


def _make_mock_client(login_status=200):
    client = MagicMock(spec=httpx.Client)
    client.get.return_value = MagicMock(status_code=200)
    client.post.return_value = MagicMock(status_code=login_status)
    return client


def test_login_makes_three_requests_in_order():
    client = _make_mock_client()
    with patch("scraper.browser.settings") as s:
        s.sreality_username = "u"
        s.sreality_password = "p"
        _login(client)

    assert client.get.call_count == 2
    assert client.post.call_count == 1

    get_urls = [call[0][0] for call in client.get.call_args_list]
    post_url = client.post.call_args[0][0]

    assert "login.szn.cz" in get_urls[0]
    assert "service=sreality" in get_urls[0]
    assert "login.szn.cz/api/v1/login" in post_url
    assert "autologin" in get_urls[1]


def test_login_raises_on_non_200():
    client = _make_mock_client(login_status=401)
    with patch("scraper.browser.settings") as s:
        s.sreality_username = "u"
        s.sreality_password = "wrong"
        with pytest.raises(Exception):
            _login(client)


def test_login_sends_credentials_in_body():
    client = _make_mock_client()
    with patch("scraper.browser.settings") as s:
        s.sreality_username = "user@example.com"
        s.sreality_password = "secret"
        _login(client)

    post_kwargs = client.post.call_args[1]
    body = post_kwargs.get("json", {})
    assert body.get("username") == "user@example.com"
    assert body.get("password") == "secret"
    assert body.get("service") == "sreality"


def test_browser_client_yields_httpx_client():
    with patch("scraper.browser._login"):
        with browser_client() as client:
            assert isinstance(client, httpx.Client)
