import logging
import urllib.parse
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class _BrowserResponse:
    """Thin wrapper making Playwright's APIResponse compatible with httpx Response usage."""

    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(
                f"Client error '{self.status_code}' for url '{self._resp.url}'"
            )

    def json(self):
        return self._resp.json()


class BrowserClient:
    """Drop-in replacement for httpx.Client that routes requests through a Playwright
    browser context, sharing its cookies and bypassing JS-based bot protection."""

    def __init__(self, page):
        self._page = page

    def get(self, url: str, headers: dict = None, timeout: int = 30, params: dict = None, **kwargs) -> _BrowserResponse:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        resp = self._page.request.get(
            url,
            headers=headers or {},
            timeout=timeout * 1000,
        )
        return _BrowserResponse(resp)


@contextmanager
def browser_client():
    """Context manager yielding a BrowserClient with an established Sreality session.

    Launches headless Chromium, visits the Sreality homepage so the JS bot-protection
    challenge runs and sets valid session cookies, then yields a client that reuses
    those cookies for all subsequent API requests.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        logger.info("Establishing Sreality browser session...")
        page.goto("https://www.sreality.cz/", wait_until="networkidle", timeout=60000)
        logger.info("Browser session established")

        try:
            yield BrowserClient(page)
        finally:
            browser.close()
