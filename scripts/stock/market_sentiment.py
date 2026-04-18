"""
市场情绪指标 — VIX恐慌指数 + CNN Fear & Greed Index.

用途:
  - 作为模型特征 (市场整体恐慌/贪婪程度)
  - UI 展示参考信号
  - 极端值时发出警告

数据源:
  - VIX: Yahoo Finance CSV (CBOE Volatility Index)
  - Fear & Greed: CNN Business API / alternative-me crypto fear index as proxy
"""
import json
import logging
import os
import re
from datetime import datetime

import requests

from config import STOCK_DATA_DIR, STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(STOCK_REPORTS_ROOT, "market_sentiment")
_PROXIES = {}
_proxy = os.environ.get("STOCK_PROXY")
if _proxy:
    _PROXIES = {"http": _proxy, "https": _proxy}


def fetch_fear_greed() -> dict:
    """
    Fetch CNN-style Fear & Greed index.
    Uses alternative.me API (widely available, no auth needed).
    Returns: { value: 0-100, label: str, timestamp: str }
    """
    result = {"value": None, "label": "", "timestamp": "", "source": ""}

    # Source 1: alternative.me Fear & Greed (crypto-derived, but tracks market sentiment)
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=1&format=json",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10, proxies=_PROXIES,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [{}])[0]
        result["value"] = int(data.get("value", 0))
        result["label"] = data.get("value_classification", "")
        result["timestamp"] = data.get("timestamp", "")
        result["source"] = "alternative.me"
        log.info("Fear & Greed: %d (%s)", result["value"], result["label"])
    except Exception as e:
        log.warning("alternative.me Fear & Greed 获取失败: %s", e)

    # Source 2: Try CNN Fear & Greed via web scrape
    if result["value"] is None:
        try:
            resp = requests.get(
                "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                },
                timeout=10, proxies=_PROXIES,
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
        except Exception as e:
            log.warning("CNN Fear & Greed 获取失败: %s", e)

    _save_cache("fear_greed", result)
    return result


def fetch_vix() -> dict:
    """
    Fetch latest VIX (CBOE Volatility Index) from Yahoo Finance.
    Returns: { value: float, change_pct: float, timestamp: str }
    """
    result = {"value": None, "change_pct": None, "timestamp": "", "source": ""}

    for vix_url, vix_parser in [
        ("https://query2.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d", _parse_yahoo_vix),
        ("https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d", _parse_yahoo_vix),
    ]:
        try:
            resp = requests.get(
                vix_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10, proxies=_PROXIES,
            )
            resp.raise_for_status()
            parsed = vix_parser(resp.json())
            if parsed:
                result.update(parsed)
                log.info("VIX: %.2f (%.2f%%)", result["value"], result.get("change_pct") or 0)
                break
        except Exception as e:
            log.debug("VIX source %s failed: %s", vix_url[:50], e)

    if result["value"] is None:
        log.warning("所有 VIX 数据源均失败")

    _save_cache("vix", result)
    return result


def _parse_yahoo_vix(data: dict) -> dict | None:
    meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
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
    path = os.path.join(_CACHE_DIR, "combined.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
