"""Parse official US macro release pages (Census, ISM PMI, ADP NER)."""
from __future__ import annotations

import html as htmlmod
import re
from datetime import date
from urllib.parse import urljoin

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_ISM_BASE = (
    "https://www.ismworld.org/supply-management-news-and-reports/"
    "reports/ism-pmi-reports"
)
_ADP_BASE = "https://mediacenter.adp.com"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _text(blob: str) -> str:
    blob = htmlmod.unescape(blob or "")
    blob = _TAG_RE.sub(" ", blob)
    return _WS_RE.sub(" ", blob).strip()


def looks_like_captcha(html: str) -> bool:
    low = (html or "").lower()
    return (
        "captcha_form" in low
        or "captcha_resp" in low
        or "challenge-platform" in low
        or "just a moment" in low
        or "attention required" in low
        or "cloudflare" in low
    )


def looks_like_xml(body: str) -> bool:
    head = (body or "").lstrip()[:200].lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head


def parse_census_html(html: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"<article\b[^>]*>(.*?)</article>",
        html or "",
        re.I | re.S,
    ):
        block = m.group(1)
        hm = re.search(
            r"<h[23][^>]*>\s*(?:<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>)?([^<]{3,120})",
            block,
            re.I,
        )
        if not hm:
            continue
        href = (hm.group(1) or "").strip()
        title = _text(hm.group(2) or "")
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        bits = [_text(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", block, re.I | re.S)]
        bits = [b for b in bits if b][:4]
        url = href if href.startswith("http") else urljoin(
            "https://www.census.gov/", href.lstrip("/")
        )
        items.append(_census_item(title, url, bits))
        if len(items) >= 12:
            break
    if items:
        return items
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", html or "", re.I | re.S):
        title = _text(m.group(1))
        if not title or title.lower() in seen:
            continue
        if not re.search(
            r"Starts|Sales|Inventories|Orders|Trade|Construction|"
            r"Applications|Durable|Wholesale|Retail|Housing|Factory",
            title,
            re.I,
        ):
            continue
        seen.add(title.lower())
        items.append(_census_item(title, "https://www.census.gov/economic-indicators/", []))
        if len(items) >= 12:
            break
    return items


def _census_item(title: str, url: str, bits: list[str]) -> dict:
    released = next((b for b in bits if "Released" in b), "")
    return {
        "title": title,
        "url": url or "https://www.census.gov/economic-indicators/",
        "date": _census_released_iso(released),
        "summary": " · ".join(bits),
        "category": "us-political",
        "points": [],
        "source": "Census Bureau",
    }


def _census_released_iso(text: str) -> str:
    m = re.search(
        r"Released\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,\s+(\d{4})",
        text or "",
        re.I,
    )
    if not m:
        return ""
    month = {name: i + 1 for i, name in enumerate(_MONTHS)}.get(m.group(1).lower())
    if not month:
        return ""
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def parse_ism_report_html(html: str, url: str) -> dict | None:
    if not html or looks_like_captcha(html):
        return None
    plain = _text(html)
    if "no longer available" in plain.lower():
        return None
    if "captcha" in plain.lower() and len(plain) < 400:
        return None
    headings = [_text(h) for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)]
    headings = [h for h in headings if h]
    title = next((h for h in headings if re.search(r"PMI|percent|%", h, re.I)), "")
    if not title and headings:
        title = headings[0]
    if not title or "no longer available" in title.lower():
        return None
    if not re.search(r"PMI|Manufacturing|Services", title, re.I):
        return None
    para = ""
    for p in re.findall(r"<p[^>]*>(.*?)</p>", html, re.I | re.S):
        t = _text(p)
        if "Tempe" in t or "Economic activity" in t:
            para = t
            break
    if not para:
        para = plain[:400]
    if "Economic activity" not in para and "PMI" not in title:
        return None
    return {
        "title": title[:200],
        "url": url,
        "date": "",
        "summary": para[:400],
        "category": "us-political",
        "points": [],
        "source": "ISM PMI Reports",
    }


def ism_report_urls(today: date | None = None) -> list[str]:
    today = today or date.today()
    months: list[str] = []
    m = today.month
    for _ in range(3):
        months.append(_MONTHS[m - 1])
        m -= 1
        if m == 0:
            m = 12
    urls = []
    for kind in ("pmi", "services"):
        for month in months:
            urls.append(f"{_ISM_BASE}/{kind}/{month}/")
    return urls


def playwright_ism_urls(need_pw: list[str], per_kind: int = 2) -> list[str]:
    """Keep manufacturing and services when Playwright budget is tight."""
    picked: list[str] = []
    for kind in ("/pmi/", "/services/"):
        picked.extend([u for u in need_pw if kind in u][:per_kind])
    return picked


def parse_adp_list_html(html: str, base: str = _ADP_BASE) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for href, raw in re.findall(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html or "",
        re.I | re.S,
    ):
        title = _text(raw)
        if "national employment report" not in title.lower():
            continue
        key = title.lower()[:80]
        if not title or key in seen:
            continue
        seen.add(key)
        url = href if href.startswith("http") else urljoin(base.rstrip("/") + "/", href.lstrip("/"))
        items.append({
            "title": title,
            "url": url,
            "date": "",
            "summary": title,
            "category": "us-political",
            "points": [],
            "source": "ADP Employment",
        })
        if len(items) >= 12:
            break
    return items
