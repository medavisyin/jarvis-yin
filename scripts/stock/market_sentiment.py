"""
市场情绪指标 — VIX恐慌指数 + CNN Fear & Greed Index.

用途:
  - 作为模型特征 (市场整体恐慌/贪婪程度)
  - UI 展示参考信号
  - 极端值时发出警告
  - World monitor Finance radar (Fear & Greed + VIX + gold/oil/SPX/BTC)

数据源:
  - VIX / quotes: Yahoo Finance chart API
  - Fear & Greed: alternative.me / CNN
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote

import requests

from config import STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(STOCK_REPORTS_ROOT, "market_sentiment")
SIGNAL_TTL_SEC = 30 * 60
RADAR_QUOTE_SPECS = (
    {"id": "gold", "symbol": "GC=F", "label": "Gold"},
    {"id": "oil", "symbol": "CL=F", "label": "WTI"},
    {"id": "spx", "symbol": "^GSPC", "label": "S&P 500"},
    {"id": "btc", "symbol": "BTC-USD", "label": "Bitcoin"},
)
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _proxy_candidates() -> list[dict]:
    """Try STOCK_PROXY / BRIEFING_PROXY first, then direct (socks may be down)."""
    proxy = os.environ.get("STOCK_PROXY") or os.environ.get("BRIEFING_PROXY") or ""
    opts: list[dict] = []
    if proxy:
        opts.append({"http": proxy, "https": proxy})
    opts.append({})
    return opts


def _request_proxies() -> dict:
    return _proxy_candidates()[0]


def fetch_fear_greed() -> dict:
    """
    Fetch CNN-style Fear & Greed index.
    Uses alternative.me API (widely available, no auth needed).
    Returns: { value: 0-100, label: str, timestamp: str }
    """
    result = {"value": None, "label": "", "timestamp": "", "source": ""}

    # Source 1: alternative.me Fear & Greed (crypto-derived, but tracks market sentiment)
    for proxies in _proxy_candidates():
        try:
            resp = requests.get(
                "https://api.alternative.me/fng/?limit=1&format=json",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10, proxies=proxies or None,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [{}])[0]
            result["value"] = int(data.get("value", 0))
            result["label"] = data.get("value_classification", "")
            result["timestamp"] = data.get("timestamp", "")
            result["source"] = "alternative.me"
            log.info("Fear & Greed: %d (%s)", result["value"], result["label"])
            break
        except Exception as e:
            log.warning("alternative.me Fear & Greed 获取失败: %s", e)

    # Source 2: Try CNN Fear & Greed via web scrape
    if result["value"] is None:
        for proxies in _proxy_candidates():
            try:
                resp = requests.get(
                    "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "application/json",
                    },
                    timeout=10, proxies=proxies or None,
                )
                resp.raise_for_status()
                data = resp.json()
                score = data.get("fear_and_greed", {}).get("score")
                rating = data.get("fear_and_greed", {}).get("rating")
                if score is not None:
                    result["value"] = round(float(score))
                    result["label"] = rating or ""
                    result["timestamp"] = datetime.now().isoformat()
                    result["source"] = "CNN"
                    log.info("CNN Fear & Greed: %d (%s)", result["value"], result["label"])
                    break
            except Exception as e:
                log.warning("CNN Fear & Greed 获取失败: %s", e)

    if result["value"] is not None:
        _save_cache("fear_greed", result)
    return result


def fetch_vix() -> dict:
    """
    Fetch latest VIX (CBOE Volatility Index) from Yahoo Finance.
    Returns: { value: float, change_pct: float, timestamp: str }
    """
    result = {"value": None, "change_pct": None, "timestamp": "", "source": ""}
    parsed = _fetch_yahoo_symbol("^VIX")
    if parsed:
        result.update(parsed)
        log.info("VIX: %.2f (%.2f%%)", result["value"], result.get("change_pct") or 0)
    else:
        log.warning("所有 VIX 数据源均失败")

    if result["value"] is not None:
        _save_cache("vix", result)
    return result


def parse_yahoo_quote(data: dict) -> dict | None:
    results = data.get("chart", {}).get("result") or [{}]
    meta = results[0].get("meta", {}) if results else {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("previousClose")
    if price is None:
        return None
    result = {
        "value": round(float(price), 2),
        "source": "Yahoo Finance",
        "timestamp": datetime.now().isoformat(),
    }
    if prev and float(prev) > 0:
        result["change_pct"] = round((float(price) - float(prev)) / float(prev) * 100, 2)
    return result


def _parse_yahoo_vix(data: dict) -> dict | None:
    return parse_yahoo_quote(data)


def _fetch_yahoo_symbol(symbol: str) -> dict | None:
    encoded = quote(symbol, safe="")
    for proxies in _proxy_candidates():
        for host in ("query2", "query1"):
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=5d"
            try:
                resp = requests.get(
                    url,
                    headers=_YAHOO_HEADERS,
                    timeout=8,
                    proxies=proxies or None,
                )
                resp.raise_for_status()
                parsed = parse_yahoo_quote(resp.json())
                if parsed:
                    return parsed
            except Exception as e:
                log.debug("Yahoo %s %s failed: %s", host, symbol, e)
    return None


def fetch_radar_quotes() -> list[dict]:
    """Latest Gold / WTI / S&P 500 / Bitcoin snapshots from Yahoo chart API."""
    rows: list[dict] = []

    def one(spec: dict) -> dict:
        parsed = _fetch_yahoo_symbol(spec["symbol"]) or {}
        return {
            "id": spec["id"],
            "symbol": spec["symbol"],
            "label": spec["label"],
            "value": parsed.get("value"),
            "change_pct": parsed.get("change_pct"),
            "source": parsed.get("source") or "",
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(one, spec): spec for spec in RADAR_QUOTE_SPECS}
        by_id = {}
        for fut in as_completed(futs):
            spec = futs[fut]
            try:
                by_id[spec["id"]] = fut.result()
            except Exception as e:
                log.debug("radar quote %s failed: %s", spec["id"], e)
                by_id[spec["id"]] = {
                    "id": spec["id"],
                    "symbol": spec["symbol"],
                    "label": spec["label"],
                    "value": None,
                    "change_pct": None,
                    "source": "",
                }
    rows = [by_id[spec["id"]] for spec in RADAR_QUOTE_SPECS if spec["id"] in by_id]
    _save_cache("radar_quotes", {"quotes": rows, "fetched_at": datetime.now().isoformat()})
    return rows


def fetch_all_sentiment() -> dict:
    """Fetch all market sentiment indicators at once."""
    fg = fetch_fear_greed()
    vix = fetch_vix()

    combined = {
        "fear_greed": fg,
        "vix": vix,
        "fetched_at": datetime.now().isoformat(),
        "market_mood": _classify_mood(fg.get("value"), vix.get("value")),
    }
    _save_cache("combined", combined)
    return combined


def _classify_mood(fg_value, vix_value) -> dict:
    """Classify overall market mood from fear/greed + VIX."""
    signals = []
    risk_level = "normal"

    if fg_value is not None:
        if fg_value <= 20:
            signals.append("极度恐惧 (Extreme Fear)")
            risk_level = "high_fear"
        elif fg_value <= 40:
            signals.append("恐惧 (Fear)")
            risk_level = "fear"
        elif fg_value >= 80:
            signals.append("极度贪婪 (Extreme Greed)")
            risk_level = "high_greed"
        elif fg_value >= 60:
            signals.append("贪婪 (Greed)")
            risk_level = "greed"
        else:
            signals.append("中性 (Neutral)")

    if vix_value is not None:
        if vix_value >= 30:
            signals.append(f"VIX {vix_value:.1f} — 高波动/恐慌")
            if risk_level in ("normal", "greed", "high_greed"):
                risk_level = "high_fear"
        elif vix_value >= 20:
            signals.append(f"VIX {vix_value:.1f} — 偏高")
        else:
            signals.append(f"VIX {vix_value:.1f} — 正常")

    return {
        "risk_level": risk_level,
        "signals": signals,
        "recommendation": _mood_recommendation(risk_level),
    }


def _mood_recommendation(risk_level: str) -> str:
    return {
        "high_fear": "市场极度恐慌，建议谨慎操作，可能是逢低建仓的机会",
        "fear": "市场偏恐慌，建议降低仓位或观望",
        "normal": "市场情绪正常，按计划操作",
        "greed": "市场偏贪婪，注意风险，考虑止盈",
        "high_greed": "市场极度贪婪，高风险区域，建议减仓",
    }.get(risk_level, "")


def load_cached_sentiment() -> dict | None:
    return _load_cache("combined")


def load_cached_quotes() -> dict | None:
    return _load_cache("radar_quotes")


def assemble_radar_signals(combined: dict | None, quotes: list | None) -> dict:
    combined = combined or {}
    fg = combined.get("fear_greed") or {}
    vix = combined.get("vix") or {}
    mood = combined.get("market_mood") or {}
    return {
        "fear_greed": {
            "value": fg.get("value"),
            "label": fg.get("label") or "",
            "source": fg.get("source") or "",
        },
        "vix": {
            "value": vix.get("value"),
            "change_pct": vix.get("change_pct"),
            "source": vix.get("source") or "",
        },
        "quotes": list(quotes or []),
        "mood": {
            "risk_level": mood.get("risk_level") or "",
            "signals": list(mood.get("signals") or []),
            "recommendation": mood.get("recommendation") or "",
        },
        "fetched_at": combined.get("fetched_at") or "",
    }


def _signals_stale(fetched_at: str) -> bool:
    if not fetched_at:
        return True
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    return (datetime.now() - ts).total_seconds() > SIGNAL_TTL_SEC


def _filled_field(old: dict, new: dict, key: str) -> dict:
    incoming = new.get(key) or {}
    if incoming.get("value") is not None:
        return incoming
    return old.get(key) or incoming


def load_radar_signals(*, allow_fetch: bool = False) -> dict:
    """Cache-first snapshot for the World monitor Finance radar. Live GET may fetch."""
    combined = load_cached_sentiment() or {}
    quotes_wrap = load_cached_quotes() or {}
    quotes = list(quotes_wrap.get("quotes") or [])
    fetched_at = quotes_wrap.get("fetched_at") or combined.get("fetched_at") or ""
    have_fg = combined.get("fear_greed", {}).get("value") is not None
    have_quotes = any(q.get("value") is not None for q in quotes)
    stale = _signals_stale(fetched_at)
    if allow_fetch and (stale or not have_fg or not have_quotes):
        if stale or not have_fg:
            try:
                fresh = fetch_all_sentiment()
                fg = _filled_field(combined, fresh, "fear_greed")
                vix = _filled_field(combined, fresh, "vix")
                combined = {
                    "fear_greed": fg,
                    "vix": vix,
                    "fetched_at": fresh.get("fetched_at") or combined.get("fetched_at") or "",
                    "market_mood": _classify_mood(fg.get("value"), vix.get("value")),
                }
                _save_cache("combined", combined)
            except Exception as e:
                log.warning("radar sentiment fetch failed: %s", e)
        if stale or not have_quotes:
            try:
                fresh_quotes = fetch_radar_quotes()
                if any(q.get("value") is not None for q in fresh_quotes):
                    quotes = fresh_quotes
            except Exception as e:
                log.warning("radar quotes fetch failed: %s", e)
    return assemble_radar_signals(combined, quotes)


def _load_cache(name: str) -> dict | None:
    path = os.path.join(_CACHE_DIR, f"{name}.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            pass
    return None


def _save_cache(name: str, data: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    result = fetch_all_sentiment()
    quotes = fetch_radar_quotes()
    print(json.dumps(assemble_radar_signals(result, quotes), ensure_ascii=False, indent=2))
