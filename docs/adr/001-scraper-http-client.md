# ADR 001: Replace Playwright with httpx for scraper HTTP client

**Date:** 2026-05-29  
**Status:** Accepted

## Context

The scraper originally used plain `httpx` to call the Sreality v2 API (`/api/cs/v2/estates`). In May 2026 that endpoint returned 403 due to JS-based bot protection, so it was replaced with a Playwright-backed `BrowserClient` that launched headless Chromium, visited `sreality.cz` to let bot-protection JS run, then used `page.request.get()` for API calls.

In May 2026 Sreality removed the v2 API entirely (404) and replaced it with a v1 API (`/api/v1/estates/search`) gated behind Seznam SSO authentication. The new auth flow is three plain HTTP calls — no JavaScript execution required:

```
GET  https://login.szn.cz/?service=sreality...   (acquire session cookies)
POST https://login.szn.cz/api/v1/login            (authenticate)
GET  https://login.szn.cz/api/v1/autologin        (transfer session to sreality.cz)
```

## Decision

Remove Playwright entirely from the scraper. Replace `BrowserClient` with a plain `httpx.Client` that authenticates via the three-call login flow and carries the resulting cookie jar for all subsequent API requests.

## Consequences

**Positive:**
- Eliminates the ~200–300 MB headless Chromium process per scrape run — significant on a memory-constrained Synology NAS.
- Removes the `playwright` dependency from `scraper/requirements.txt`; it remains only in the dev group of `pyproject.toml` for any future testing needs.
- Faster scrape startup: no browser launch, no page load, no JS execution.
- Simpler code: `browser.py` becomes a thin authenticated-session factory returning an `httpx.Client`.

**Negative / risks:**
- If Sreality adds a CAPTCHA or other challenge to the login flow in future, plain httpx will not be able to solve it without browser automation.
- The login credentials (`SREALITY_USERNAME`, `SREALITY_PASSWORD`) must be present in `.env` and available to the scraper container at runtime.

## Alternatives considered

**Keep Playwright, use only `context.request`:** Would avoid the browser page but still carry the Playwright dependency and its Chromium binary (~300 MB). Rejected — no benefit over plain httpx for a purely HTTP auth flow.

**Playwright stealth + consent bypass:** Attempt to mask headless Chromium to pass the CMP bot detection, then scrape HTML. Rejected — brittle, higher ongoing maintenance risk, and the authenticated API approach is more reliable.

**Switch to bezrealitky.cz:** Different listing inventory (no agency listings), requires rebuilding search config model and parsers. Rejected — more disruptive than migrating to the new Sreality API.
