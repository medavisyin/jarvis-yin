"""
Smart proxy strategy for source fetchers.

Determines per-domain whether to use a direct connection or proxy.
Results are persisted to a JSON file so successful strategies are
reused immediately on subsequent runs.

Strategy per domain:
  1. If a remembered strategy exists and is fresh (< 7 days), use it.
  2. Otherwise, probe: try direct first; if it fails or is Cloudflare-
     blocked, try proxy.  Remember the winner.

Usage in Playwright-based fetchers:

    from proxy_strategy import get_proxy_for_playwright

    async with async_playwright() as p:
        proxy_arg = await get_proxy_for_playwright(p, SOURCE_URL)
        browser = await p.chromium.launch(headless=True, **proxy_arg)
        ...

Usage in httpx-based fetchers:

    from proxy_strategy import get_proxy_for_httpx

    proxy_kwarg = get_proxy_for_httpx(url)
    r = httpx.get(url, timeout=15, **proxy_kwarg)

Usage in requests-based fetchers:

    from proxy_strategy import get_proxies_for_requests

    proxies = get_proxies_for_requests(url)
    r = requests.get(url, proxies=proxies, ...)
"""
from __future__ import annotations

import json
import os
import time
import logging
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

PROXY_URL = os.environ.get("BRIEFING_PROXY", "")
_DEFAULT_REPORTS = os.path.join(os.path.expanduser("~"), "reports", "ai")
_MEMORY_PATH = os.path.join(
    os.environ.get("JARVIS_REPORTS_ROOT", _DEFAULT_REPORTS),
    ".proxy-strategy.json",
)
_RETEST_SECONDS = 7 * 24 * 3600  # re-probe after 7 days
_PROBE_TIMEOUT_MS = 35_000       # probe timeout (some sites need 30s+)


def _domain(url: str) -> str:
    return urlparse(url).hostname or url


def _load_memory() -> dict:
    if os.path.exists(_MEMORY_PATH):
        try:
            with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_memory(mem: dict) -> None:
    os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
    with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)


def _is_fresh(entry: dict) -> bool:
    return (time.time() - entry.get("last_tested", 0)) < _RETEST_SECONDS


def get_remembered(url: str) -> str | None:
    """Return 'direct' or 'proxy' if a fresh remembered strategy exists."""
    domain = _domain(url)
    mem = _load_memory()
    entry = mem.get(domain)
    if entry and _is_fresh(entry):
        return entry["method"]
    return None


def remember(url: str, method: str) -> None:
    """Persist the winning strategy for a domain."""
    domain = _domain(url)
    mem = _load_memory()
    mem[domain] = {
        "method": method,
        "last_tested": time.time(),
        "proxy_url": PROXY_URL if method == "proxy" else None,
    }
    _save_memory(mem)
    _log.info("Proxy strategy for %s: %s", domain, method)


# ── Playwright helpers ────────────────────────────────────────────────

def _pw_proxy_arg(method: str) -> dict:
    if method == "proxy" and PROXY_URL:
        return {"proxy": {"server": PROXY_URL}}
    return {}


async def _pw_probe(playwright, url: str) -> str:
    """Try direct, then proxy.  Return the winning method."""
    methods = ["direct"]
    if PROXY_URL:
        methods.append("proxy")
    for method in methods:
        proxy_arg = _pw_proxy_arg(method)
        browser = None
        try:
            browser = await playwright.chromium.launch(headless=True, **proxy_arg)
            page = await browser.new_page()
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=_PROBE_TIMEOUT_MS)
            title = (await page.title()).lower()
            await browser.close()
            browser = None

            blocked = "just a moment" in title or "forbidden" in title
            bad_status = resp and resp.status in (403, 503)
            if blocked or bad_status:
                _log.info("Probe %s via %s: blocked (title=%s, status=%s)",
                          _domain(url), method, title[:30], resp.status if resp else "?")
                continue
            _log.info("Probe %s via %s: OK", _domain(url), method)
            return method
        except Exception as exc:
            _log.info("Probe %s via %s: failed (%s)", _domain(url), method, str(exc)[:80])
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
    _log.warning("Probe %s: all methods failed, defaulting to direct", _domain(url))
    return "direct"


async def get_proxy_for_playwright(playwright, url: str) -> dict:
    """Return the kwargs dict for ``chromium.launch()`` with the optimal proxy setting.

    Example::

        proxy_arg = await get_proxy_for_playwright(p, SOURCE_URL)
        browser = await p.chromium.launch(headless=True, **proxy_arg)
    """
    remembered = get_remembered(url)
    if remembered:
        _log.info("Using remembered strategy for %s: %s", _domain(url), remembered)
        return _pw_proxy_arg(remembered)

    method = await _pw_probe(playwright, url)
    remember(url, method)
    return _pw_proxy_arg(method)


# ── httpx helpers ─────────────────────────────────────────────────────

def _httpx_probe(url: str) -> str:
    """Try direct, then proxy.  Return the winning method."""
    import httpx

    methods = ["direct"]
    if PROXY_URL:
        methods.append("proxy")
    for method in methods:
        try:
            kwargs: dict = {"timeout": 15}
            if method == "proxy":
                kwargs["proxy"] = PROXY_URL
            r = httpx.get(url, **kwargs)
            if r.status_code in (403, 503):
                _log.info("httpx probe %s via %s: status %d", _domain(url), method, r.status_code)
                continue
            _log.info("httpx probe %s via %s: OK (%d)", _domain(url), method, r.status_code)
            return method
        except Exception as exc:
            _log.info("httpx probe %s via %s: failed (%s)", _domain(url), method, str(exc)[:80])
    _log.warning("httpx probe %s: all methods failed, defaulting to direct", _domain(url))
    return "direct"


def get_proxy_for_httpx(url: str) -> dict:
    """Return kwargs dict for ``httpx.get()`` with the optimal proxy.

    Example::

        proxy_kwarg = get_proxy_for_httpx(rss_url)
        r = httpx.get(rss_url, timeout=15, **proxy_kwarg)
    """
    remembered = get_remembered(url)
    if remembered is None:
        remembered = _httpx_probe(url)
        remember(url, remembered)
    else:
        _log.info("Using remembered strategy for %s: %s", _domain(url), remembered)

    if remembered == "proxy" and PROXY_URL:
        return {"proxy": PROXY_URL}
    return {}


# ── requests helpers ──────────────────────────────────────────────────

def _requests_probe(url: str) -> str:
    """Try direct, then proxy.  Return the winning method."""
    import requests

    methods = ["direct"]
    if PROXY_URL:
        methods.append("proxy")
    for method in methods:
        try:
            kwargs: dict = {"timeout": 15, "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }}
            if method == "proxy":
                kwargs["proxies"] = {"http": PROXY_URL, "https": PROXY_URL}
            r = requests.get(url, **kwargs)
            if r.status_code in (403, 503):
                _log.info("requests probe %s via %s: status %d", _domain(url), method, r.status_code)
                continue
            _log.info("requests probe %s via %s: OK (%d)", _domain(url), method, r.status_code)
            return method
        except Exception as exc:
            _log.info("requests probe %s via %s: failed (%s)", _domain(url), method, str(exc)[:80])
    _log.warning("requests probe %s: all methods failed, defaulting to direct", _domain(url))
    return "direct"


def get_proxies_for_requests(url: str) -> dict:
    """Return proxies dict for ``requests.get(proxies=...)``.

    Example::

        proxies = get_proxies_for_requests(api_url)
        r = requests.get(api_url, proxies=proxies, ...)
    """
    remembered = get_remembered(url)
    if remembered is None:
        remembered = _requests_probe(url)
        remember(url, remembered)
    else:
        _log.info("Using remembered strategy for %s: %s", _domain(url), remembered)

    if remembered == "proxy" and PROXY_URL:
        return {"http": PROXY_URL, "https": PROXY_URL}
    return {}
