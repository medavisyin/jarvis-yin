"""Parsers for US official macro sources (Census / ISM / ADP)."""

from __future__ import annotations

import os
import sys
from datetime import date

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_NEWS = os.path.join(_SCRIPTS, "fetchers", "news")
if _NEWS not in sys.path:
    sys.path.insert(0, _NEWS)

from us_macro_parse import (  # noqa: E402
    ism_report_urls,
    looks_like_captcha,
    parse_adp_list_html,
    parse_census_html,
    parse_ism_report_html,
    playwright_ism_urls,
)

_CENSUS_HTML = """
<article class="newest-release">
  <h3><a href="https://www.census.gov/construction/nrc/index.html">Housing Starts</a></h3>
  <p>Released August 18th, 2026</p>
  <p>Current July 2026</p>
  <p>1,239,000 units</p>
  <p>Difference -12.4%</p>
</article>
<article class="newest-release">
  <h3><a href="https://www.census.gov/retail/index.html">Advance Retail and Food Services Sales</a></h3>
  <p>Released August 14th, 2026</p>
  <p>Current July 2026</p>
  <p>$763.6B</p>
  <p>Difference -0.6%</p>
</article>
"""

_ISM_HTML = """
<html><body>
<h1>Manufacturing PMI&reg; at 55.6%</h1>
<h1>July 2026 ISM&reg; Manufacturing PMI&reg; Report</h1>
<p>(Tempe, Arizona) — Economic activity in the manufacturing sector expanded in July
for the seventh consecutive month. The Manufacturing PMI registered 55.6 percent.</p>
</body></html>
"""

_ISM_EMPTY = """
<html><body>
<h1>The content you are looking for is no longer available.</h1>
</body></html>
"""

_ADP_HTML = """
<html><body>
<a href="/2026-08-05-ADP-National-Employment-Report-Private-Sector-Employment-Increased-by-44,000-Jobs-in-July-Annual-Pay-was-Up-4-4">ADP National Employment Report: Private Sector Employment Increased by 44,000 Jobs in July; Annual Pay was Up 4.4%</a>
<a href="/2026-08-25-ADP-National-Employment-Report-Preliminary-Estimate-for-August-8-2026">ADP National Employment Report Preliminary Estimate for August 8, 2026</a>
<a href="/2026-08-27-ADP-to-Present-at-Upcoming-Investor-Conference">ADP to Present at Upcoming Investor Conference</a>
</body></html>
"""


def test_parse_census_newest_releases():
    items = parse_census_html(_CENSUS_HTML)
    titles = [it["title"] for it in items]
    assert "Housing Starts" in titles
    assert any("Retail" in t for t in titles)
    housing = next(it for it in items if it["title"] == "Housing Starts")
    assert "census.gov" in housing["url"]
    assert "12.4" in housing["summary"] or "1,239,000" in housing["summary"]
    assert housing["category"] == "us-political"
    assert housing["source"].startswith("Census")
    assert housing["date"] == "2026-08-18"
    assert not housing["date"].startswith("Released")
    assert "Released" in housing["summary"]


def test_parse_ism_report_html():
    url = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/july/"
    item = parse_ism_report_html(_ISM_HTML, url)
    assert item is not None
    assert "55.6" in item["title"]
    assert "manufacturing" in item["title"].lower() or "Manufacturing" in item["summary"]
    assert item["url"] == url
    assert item["category"] == "us-political"
    assert parse_ism_report_html(_ISM_EMPTY, url) is None
    assert parse_ism_report_html('<form name="captcha_form"></form>', url) is None


def test_ism_report_urls_cover_pmi_and_services():
    urls = ism_report_urls(today=date(2026, 8, 29))
    blob = " ".join(urls)
    assert "/pmi/" in blob
    assert "/services/" in blob
    assert "july" in blob
    assert "august" in blob


def test_playwright_ism_urls_keep_both_series():
    queued = ism_report_urls(today=date(2026, 8, 29))
    picked = playwright_ism_urls(queued)
    blob = " ".join(picked)
    assert "/pmi/july/" in blob
    assert "/services/july/" in blob
    assert picked.count([u for u in picked if "/pmi/" in u][0]) == 1
    assert len([u for u in picked if "/pmi/" in u]) == 2
    assert len([u for u in picked if "/services/" in u]) == 2


def test_looks_like_captcha_includes_cloudflare():
    assert looks_like_captcha('<form name="captcha_form"></form>')
    assert looks_like_captcha("<title>Attention Required! | Cloudflare</title>")
    assert looks_like_captcha('<div class="cf-challenge-platform"></div>')
    assert not looks_like_captcha("<h1>Housing Starts</h1>")


def test_parse_adp_keeps_employment_report_only():
    items = parse_adp_list_html(_ADP_HTML)
    titles = [it["title"] for it in items]
    assert any("44,000" in t for t in titles)
    assert any("Preliminary Estimate" in t for t in titles)
    assert not any("Investor Conference" in t for t in titles)
    assert all("mediacenter.adp.com" in it["url"] for it in items)
    assert all(it["category"] == "us-political" for it in items)


def test_census_and_ism_fetchers_have_playwright_fallback():
    news = os.path.join(_NEWS)
    for name in ("fetch-census.py", "fetch-ism.py"):
        src = open(os.path.join(news, name), encoding="utf-8").read()
        assert "async_playwright" in src, name
        assert "get_proxy_for_playwright" in src, name
    ism_src = open(os.path.join(news, "fetch-ism.py"), encoding="utf-8").read()
    assert "playwright_ism_urls" in ism_src
    assert "except Exception" in ism_src
    census_src = open(os.path.join(news, "fetch-census.py"), encoding="utf-8").read()
    assert "break" in census_src
