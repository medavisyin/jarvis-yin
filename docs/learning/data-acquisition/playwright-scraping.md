# Know-How: Playwright for Web Scraping

An introduction to **Playwright** and why **Jarvis** uses it to fetch content from the modern web.

## What is Playwright?

**Playwright** is a **browser automation** library from Microsoft.

- Drives **real browsers**: Chromium, Firefox, WebKit.
- Executes **JavaScript**, waits for network and DOM updates, scrolls pages, clicks, types—like a user.
- Used for **end-to-end testing** and **web scraping / data extraction**.

Official documentation:

- [Playwright for Python](https://playwright.dev/python/)

## Why Playwright instead of requests + BeautifulSoup?

**`requests`** fetches raw HTML. **BeautifulSoup** parses that HTML statically.

Many sites today:

- Render content **only after JavaScript runs**
- Use **infinite scroll** or **lazy loading**
- Are **single-page apps (SPAs)** where the first HTML shell is nearly empty
- Show different content after **cookie banners** or client-side redirects

**Playwright** opens a **real browser**, so it sees what a human sees after JS runs. That makes it **more reliable** for news sites, listings, and dynamic portals—at the cost of heavier resource use than plain HTTP.

```text
requests + BS4:   HTTP response → parse static HTML
Playwright:       launch browser → load page → interact → read DOM
```

## How Jarvis uses Playwright

- **All ~15 `fetch-*.py` scripts** use Playwright for scraping briefing sources.
- **`scripts/pipeline/preflight-check.py`** uses Playwright for **URL reachability** / page-load style checks.
- Runs **headless** (no visible window) for automation.
- Uses the **async API** (`async_playwright`) for concurrency-friendly scraping.

## Key patterns used in Jarvis

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()

    await page.goto(
        "https://arxiv.org/list/cs.AI/recent",
        wait_until="domcontentloaded",
    )

    elements = await page.query_selector_all("dt")
    for el in elements:
        text = await el.inner_text()
        href = await el.get_attribute("href")

    await page.evaluate("window.scrollBy(0, 2000)")
    await page.wait_for_timeout(1500)

    await page.goto(article_url, wait_until="domcontentloaded")
    abstract = await page.query_selector(".abstract")

    await browser.close()
```

Patterns illustrated:

- **`goto` + `wait_until`** — control how “loaded” the page must be before you scrape.
- **`query_selector_all` / `query_selector`** — CSS selectors over the live DOM.
- **`inner_text` / `get_attribute`** — read visible text and links.
- **`evaluate` + `wait_for_timeout`** — scroll to trigger lazy content, then pause briefly for rendering.

## Proxy support

For corporate networks, set **`BRIEFING_PROXY`**. Jarvis passes it into browser launch, conceptually:

```python
browser = await p.chromium.launch(
    headless=True,
    proxy={"server": PROXY},
)
```

Use the exact env var name and wiring from your Jarvis scripts in your environment.

## Installation

```bash
pip install playwright
playwright install chromium
```

`playwright install` downloads browser binaries required for automation.

## Common gotchas

- **Selectors break:** Sites change CSS classes; prefer stable attributes when possible and expect maintenance.
- **Rate limits / ToS:** Scraping may violate terms; use official APIs when available.
- **Flaky waits:** Prefer **explicit waits** (`wait_for_selector`, `wait_for_load_state`) over long fixed sleeps when you can.
- **Headless detection:** Some sites behave differently for automated browsers; retries or stealth tooling may be needed (use responsibly and legally).
- **Resource usage:** Browsers use **CPU and RAM**; parallelize carefully.

## Further reading

- [Playwright Python guide](https://playwright.dev/python/docs/intro)
- [Locators & auto-waiting](https://playwright.dev/python/docs/locators)
- [Network & navigation](https://playwright.dev/python/docs/network)
