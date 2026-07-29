"""Market-impact filter and ranking for finance news briefings.

Policy (locked):
- Drop-signal hit → discard
- Keep-signal hit → keep with score
- Neither → discard (default-deny for finance sources)
"""

from __future__ import annotations

import copy
import re
from typing import Any

MIN_SCORE = 1
SOFT_WARN_COUNT = 40

# Higher weight = higher impact when sorting
_KEEP_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"circuit\s*breaker|熔断|跌停|涨停", re.I), 100),
    (re.compile(r"\bFed\b|FOMC|Powell|利率决议|降息|加息|rate\s*cut|rate\s*hike", re.I), 90),
    (re.compile(r"PBOC|央行|降准|RRR|MLF|LPR", re.I), 90),
    (re.compile(r"BOJ|ECB|央行行长|central\s*bank", re.I), 85),
    (re.compile(r"tariff|关税|制裁|sanction|trade\s*war|特朗普|Trump", re.I), 85),
    (re.compile(r"财政|刺激|stimulus|bailout|救助|违约|default", re.I), 75),
    (re.compile(r"IPO|财报|earnings|指引|guidance|并购|M&A|收购购", re.I), 70),
    (re.compile(r"原油|oil\b|黄金|gold\b|美元|USD|汇率|forex|yield", re.I), 65),
    (re.compile(r"股市|股指|指数|S&P|Nasdaq|Dow\b|沪深|A股|恒生|Nikkei|KOSPI|Hang\s*Seng", re.I), 60),
    (re.compile(r"监管|SEC|证监会|反垄断|antitrust|罚款|处罚", re.I), 60),
    (re.compile(r"通胀|CPI|PPI|非农|payroll|GDP|失业", re.I), 55),
    (re.compile(r"市场|股市波动|markets?|stocks?|equit(y|ies)|bond|期货|futures", re.I), 40),
    (re.compile(r"财联社|证券时报|Bloomberg|CNBC|Reuters\s*Markets", re.I), 30),
]

_DROP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"celebrity|明星|恋情|婚礼|wedding|娱乐|综艺|体育|足球|篮球|NBA|电影|电视剧", re.I),
    re.compile(r"天气|weather|气温|美食|旅游|游戏皮肤", re.I),
]

_CHINA_HINTS = re.compile(
    r"中国|中方|PBOC|央行|人民币|A股|沪深|港股|财联社|证券时报|人民日报|新浪|微博|北京|上海|"
    r"China|Chinese|Beijing|Shanghai|Hong\s*Kong|CNY|yuan",
    re.I,
)
_US_HINTS = re.compile(
    r"\bUS\b|\bU\.S\.|America|Fed\b|FOMC|Powell|Wall\s*Street|S&P|Nasdaq|Dow\b|"
    r"白宫|特朗普|Trump|SEC\b|纽约|New\s*York|CNBC|Yahoo",
    re.I,
)
_APAC_HINTS = re.compile(
    r"日本|韩国|韩股|日股|Nikkei|KOSPI|Tokyo|Seoul|BOJ|亚股|亚太|Australia|ASX|"
    r"India|Sensex|Taiwan|台股|新加坡|Singapore",
    re.I,
)

_CHINA_SOURCES = re.compile(r"中国|财联社|新浪|人民|头条|微博|证券时报|东方财富", re.I)
_US_SOURCES = re.compile(r"CNBC|Yahoo|Bloomberg|WSJ|MarketWatch", re.I)


def _text_of(item: dict[str, Any], *, include_source: bool = False) -> str:
    parts = [
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        str(item.get("description") or ""),
        " ".join(str(p) for p in (item.get("points") or []) if p),
    ]
    if include_source:
        parts.append(str(item.get("source") or ""))
    return " ".join(parts)


def hits_drop_signal(item: dict[str, Any]) -> bool:
    # Title/summary only — source display names must not trigger keep/drop
    text = _text_of(item, include_source=False)
    return any(p.search(text) for p in _DROP_PATTERNS)


def score_market_impact(item: dict[str, Any]) -> int:
    """Return impact score; 0 means discard under default-deny policy."""
    if hits_drop_signal(item):
        return 0
    text = _text_of(item, include_source=False)
    best = 0
    for pattern, weight in _KEEP_PATTERNS:
        if pattern.search(text):
            best = max(best, weight)
    return best


def assign_region(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "")
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    body = f"{title} {summary}"

    # Title/body region cues beat generic source defaults
    if _APAC_HINTS.search(body):
        return "apac"
    if _US_HINTS.search(body):
        return "us"
    if _CHINA_HINTS.search(body) or _CHINA_SOURCES.search(source):
        return "china"
    if _US_SOURCES.search(source):
        return "us"
    return "global"


def is_same_day(item: dict[str, Any], report_date: str) -> bool:
    date_val = str(item.get("date") or item.get("published") or "")
    if not date_val.strip():
        return False
    return report_date in date_val


def filter_and_rank_items(
    items: list[dict[str, Any]],
    report_date: str,
) -> list[dict[str, Any]]:
    """Filter by market-impact policy and rank by score (desc)."""
    kept: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        score = score_market_impact(raw)
        if score < MIN_SCORE:
            continue
        item = copy.deepcopy(raw)
        same_day = is_same_day(item, report_date)
        if not same_day:
            item["date_uncertain"] = True
            score = max(MIN_SCORE, score - 10)
        item["impact_score"] = score
        item["region"] = assign_region(item)
        kept.append(item)

    kept.sort(key=lambda x: (-int(x.get("impact_score") or 0), str(x.get("title") or "")))

    # Light region diversity: ensure first window covers available regions
    if len(kept) >= 3:
        kept = _diversify_front(kept, window=12)

    if len(kept) > SOFT_WARN_COUNT:
        print(
            f"[finance_news_filter] warning: {len(kept)} items kept "
            f"(>{SOFT_WARN_COUNT}); audio may be long"
        )
    return kept


def _diversify_front(items: list[dict[str, Any]], window: int = 12) -> list[dict[str, Any]]:
    """Pull one item per missing high-priority region into the front window.

    Inserts without re-sorting the whole front (preserves diversity slots).
    """
    front = list(items[:window])
    rest = list(items[window:])
    present = {it.get("region") for it in front}
    wanted = ("us", "apac", "china")
    for region in wanted:
        if region in present:
            continue
        idx = next((i for i, it in enumerate(rest) if it.get("region") == region), None)
        if idx is None:
            continue
        # Append to front window so region is represented; do not re-sort away
        front.append(rest.pop(idx))
        present.add(region)
    return front + rest
