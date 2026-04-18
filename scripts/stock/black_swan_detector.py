"""
黑天鹅事件检测器 — 从每日世界新闻中识别可能影响特定行业的重大风险事件.

数据源: Daily Fetch 产生的 world-news-data.json
输出: 行业风险评估 + 受影响股票预警

检测维度:
  - 战争/军事冲突
  - 制裁/贸易战
  - 自然灾害
  - 金融危机/银行倒闭
  - 疫情/公共卫生
  - 监管政策突变
  - 科技禁令/出口管制
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from config import STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

_REPORTS_AI_ROOT = os.environ.get("JARVIS_REPORTS_ROOT", "C:/reports/ai")
_CACHE_DIR = os.path.join(STOCK_REPORTS_ROOT, "market_sentiment")

RISK_PATTERNS = {
    "war": {
        "keywords": [
            r"\bwar\b", r"\bmilitary\b", r"\binvasion\b", r"\bairstrikes?\b",
            r"\bbombing\b", r"\barmed conflict\b", r"\btroops?\b", r"\bmissile",
            r"战争", r"军事冲突", r"入侵", r"空袭", r"导弹",
        ],
        "label": "战争/军事冲突",
        "industries": ["军工", "航空", "能源", "石油", "黄金", "航运", "保险"],
    },
    "sanctions": {
        "keywords": [
            r"\bsanctions?\b", r"\btrade war\b", r"\btariff", r"\bembargo\b",
            r"\bexport ban\b", r"\bblacklist", r"\bentity list\b",
            r"制裁", r"贸易战", r"关税", r"禁运", r"出口管制", r"实体清单",
        ],
        "label": "制裁/贸易战",
        "industries": ["半导体", "芯片", "AI", "科技", "电子", "通信", "汽车", "农业"],
    },
    "pandemic": {
        "keywords": [
            r"\bpandemic\b", r"\bepidemic\b", r"\boutbreak\b", r"\bvirus\b",
            r"\bquarantine\b", r"\blockdown\b", r"\bWHO.*emergency",
            r"疫情", r"大流行", r"封锁", r"隔离", r"病毒",
        ],
        "label": "疫情/公共卫生",
        "industries": ["医药", "生物", "旅游", "航空", "餐饮", "酒店", "零售"],
    },
    "financial_crisis": {
        "keywords": [
            r"\bbank.*(?:fail|collaps|crisis)\b", r"\bfinancial crisis\b",
            r"\brecession\b", r"\bdefault\b", r"\bdebt crisis\b",
            r"\bcredit crunch\b", r"\bmarket crash\b",
            r"金融危机", r"银行倒闭", r"债务违约", r"信贷紧缩", r"经济衰退",
        ],
        "label": "金融危机",
        "industries": ["银行", "保险", "证券", "金融", "房地产", "信托"],
    },
    "natural_disaster": {
        "keywords": [
            r"\bearthquake\b", r"\btsunami\b", r"\bhurricane\b", r"\btyphoon\b",
            r"\bflood(?:ing)?\b", r"\bwildfire\b", r"\bvolcano\b",
            r"地震", r"海啸", r"台风", r"洪水", r"火山", r"干旱",
        ],
        "label": "自然灾害",
        "industries": ["保险", "建筑", "农业", "能源", "航运", "旅游"],
    },
    "regulation": {
        "keywords": [
            r"\bantitrust\b", r"\bregulat(?:ion|ory) crackdown\b",
            r"\bban(?:ned|s)?\b.*(?:tech|app|platform)",
            r"\bnew regulation\b", r"\bpolicy shift\b",
            r"反垄断", r"监管", r"政策突变", r"禁令", r"整顿",
        ],
        "label": "监管政策突变",
        "industries": ["互联网", "游戏", "教育", "金融", "房地产", "医药"],
    },
    "tech_ban": {
        "keywords": [
            r"\bchip ban\b", r"\bsemiconductor.*restrict", r"\btech.*decouple",
            r"\bAI.*(?:ban|restrict|regulate)\b", r"\bexport control.*chip",
            r"芯片禁令", r"技术封锁", r"半导体制裁", r"AI监管",
        ],
        "label": "科技禁令/出口管制",
        "industries": ["半导体", "芯片", "AI", "5G", "通信", "消费电子", "软件"],
    },
}


def scan_world_news(date_str: Optional[str] = None) -> dict:
    """
    Scan world news for black swan indicators.

    Args:
        date_str: YYYY-MM-DD format. Defaults to today, falls back to yesterday.

    Returns: {
        "date": "2026-04-16",
        "alerts": [ { type, label, severity, matched_headlines, industries } ],
        "risk_summary": { overall_level, affected_industries },
    }
    """
    news_data = _load_world_news(date_str)
    if not news_data:
        return {"date": date_str or "", "alerts": [], "risk_summary": _empty_risk()}

    all_text = _extract_text(news_data)
    alerts = []

    for risk_type, config in RISK_PATTERNS.items():
        matched = []
        for headline, body in all_text:
            combined = f"{headline} {body}"
            for pat in config["keywords"]:
                if re.search(pat, combined, re.IGNORECASE):
                    matched.append(headline)
                    break

        if matched:
            severity = "high" if len(matched) >= 3 else "medium" if len(matched) >= 2 else "low"
            alerts.append({
                "type": risk_type,
                "label": config["label"],
                "severity": severity,
                "match_count": len(matched),
                "matched_headlines": matched[:5],
                "affected_industries": config["industries"],
            })

    alerts.sort(key=lambda a: {"high": 3, "medium": 2, "low": 1}[a["severity"]], reverse=True)

    result = {
        "date": date_str or datetime.now().strftime("%Y-%m-%d"),
        "alerts": alerts,
        "risk_summary": _build_risk_summary(alerts),
        "scanned_at": datetime.now().isoformat(),
    }

    _save_result(result)
    return result


def check_stock_risk(symbol: str, sector: str) -> dict | None:
    """
    Check if a specific stock's sector is at risk from today's black swan alerts.
    Returns risk info or None if no risk detected.
    """
    cached = load_cached_alerts()
    if not cached or not cached.get("alerts"):
        return None

    sector_lower = sector.lower() if sector else ""
    matching_alerts = []

    for alert in cached["alerts"]:
        for ind in alert["affected_industries"]:
            if ind.lower() in sector_lower or sector_lower in ind.lower():
                matching_alerts.append(alert)
                break

    if not matching_alerts:
        return None

    max_severity = max(a["severity"] for a in matching_alerts)
    return {
        "symbol": symbol,
        "sector": sector,
        "alerts": matching_alerts,
        "max_severity": max_severity,
        "warning": f"检测到 {len(matching_alerts)} 个可能影响 {sector} 行业的风险事件",
    }


def _load_world_news(date_str: Optional[str] = None) -> dict | None:
    dates_to_try = []
    if date_str:
        dates_to_try.append(date_str)
    else:
        today = datetime.now()
        dates_to_try.append(today.strftime("%Y-%m-%d"))
        dates_to_try.append((today - timedelta(days=1)).strftime("%Y-%m-%d"))

    for d in dates_to_try:
        path = os.path.join(_REPORTS_AI_ROOT, d, "world-news", "world-news-data.json")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                log.info("加载世界新闻: %s (%d items)", d, data.get("total_items", 0))
                return data
            except Exception as e:
                log.warning("读取 %s 失败: %s", path, e)
    return None


def _extract_text(news_data: dict) -> list[tuple[str, str]]:
    """Extract (headline, body) pairs from world-news-data.json."""
    items = []
    for cat in news_data.get("categories", []):
        for item in cat.get("items", []):
            title = item.get("title", "")
            summary = item.get("summary", "")
            points = " ".join(item.get("points", []))
            items.append((title, f"{summary} {points}"))
    return items


def _build_risk_summary(alerts: list[dict]) -> dict:
    if not alerts:
        return _empty_risk()

    all_industries = set()
    for a in alerts:
        all_industries.update(a["affected_industries"])

    high_count = sum(1 for a in alerts if a["severity"] == "high")
    medium_count = sum(1 for a in alerts if a["severity"] == "medium")

    if high_count >= 2:
        level = "critical"
    elif high_count >= 1:
        level = "high"
    elif medium_count >= 2:
        level = "elevated"
    elif alerts:
        level = "low"
    else:
        level = "normal"

    return {
        "overall_level": level,
        "alert_count": len(alerts),
        "affected_industries": sorted(all_industries),
        "recommendation": {
            "critical": "多个高危事件同时发生，建议大幅降低仓位，重点关注避险资产",
            "high": "检测到重大风险事件，建议谨慎操作，审视相关行业持仓",
            "elevated": "存在中等风险信号，建议关注相关行业动态",
            "low": "检测到轻微风险信号，持续观察",
            "normal": "未检测到显著风险事件",
        }[level],
    }


def _empty_risk() -> dict:
    return {
        "overall_level": "normal",
        "alert_count": 0,
        "affected_industries": [],
        "recommendation": "未检测到显著风险事件",
    }


def load_cached_alerts() -> dict | None:
    path = os.path.join(_CACHE_DIR, "black_swan_alerts.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_result(result: dict):
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = os.path.join(_CACHE_DIR, "black_swan_alerts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    result = scan_world_news()
    print(json.dumps(result, ensure_ascii=False, indent=2))
