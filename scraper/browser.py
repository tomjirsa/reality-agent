import logging
import httpx
from contextlib import contextmanager
from shared.config import settings

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://login.szn.cz/api/v1/login"
_INIT_URL = "https://login.szn.cz/?service=sreality&return_url=https://www.sreality.cz/"
_AUTOLOGIN_URL = (
    "https://login.szn.cz/api/v1/autologin"
    "?service=sreality&return_url=https://www.sreality.cz/"
)


def _login(client: httpx.Client) -> None:
    client.get(_INIT_URL)

    resp = client.post(
        _LOGIN_URL,
        json={
            "username": settings.sreality_username,
            "password": settings.sreality_password,
            "service": "sreality",
            "rememberMe": True,
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://login.szn.cz/",
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Sreality login failed: HTTP {resp.status_code}")

    client.get(_AUTOLOGIN_URL, headers={"Referer": "https://www.sreality.cz/"})
    logger.info("Sreality session established")


@contextmanager
def browser_client():
    with httpx.Client(follow_redirects=True) as client:
        _login(client)
        yield client
