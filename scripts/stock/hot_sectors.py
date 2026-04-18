"""
Hot sector / concept data fetcher for A-share market.

Uses akshare + Sina Finance to identify trending sectors and concepts.
Results are cached daily to avoid redundant API calls.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime

import akshare as ak
import requests

_stock_dir = os.path.dirname(os.path.abspath(__file__))
if _stock_dir not in sys.path:
    sys.path.insert(0, _stock_dir)

from config import STOCK_CACHE_DIR, STOCK_PROXY

log = logging.getLogger(__name__)
_PROXIES = {"http": STOCK_PROXY, "https": STOCK_PROXY} if STOCK_PROXY else None


def _cache_path() -> str:
    return os.path.join(STOCK_CACHE_DIR, f"hot_sectors_{datetime.now():%Y-%m-%d}.json")


def _retry(fn, *args, retries=2, **kwargs):
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("hot_sectors 尝试 %d/%d 失败: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(1 * (attempt + 1))
    raise last_err


def fetch_hot_sectors() -> list[dict]:
    """
    Fetch today's hot sectors/concepts with constituent stocks.

    Returns list of dicts:
      { "name": "AI应用", "change_pct": 3.2, "leader": "科大讯飞",
        "leader_symbol": "002230", "stocks": ["002230","300033",...] }

    Results are cached daily.
    """
    cache = _cache_path()
    if os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                log.info("使用缓存的热门板块数据 (%d 个板块)", len(data))
                return data
        except Exception:
            pass

    sectors = []

    try:
        sectors = _fetch_sectors_akshare()
    except Exception as e:
        log.warning("akshare 板块数据获取失败: %s, 尝试备用方案", e)

    if not sectors:
        try:
            sectors = _fetch_sectors_eastmoney()
        except Exception as e:
            log.error("所有板块数据源均失败: %s", e)

    if sectors:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(sectors, f, ensure_ascii=False, indent=2, default=str)
        log.info("已保存 %d 个热门板块", len(sectors))

    return sectors


def _fetch_sectors_akshare() -> list[dict]:
    """Fetch sector data via akshare concept board API."""
    df = _retry(ak.stock_board_concept_name_em)
    if df is None or df.empty:
        return []

    df = df.sort_values("涨跌幅", ascending=False)
    top = df.head(20)

    sectors = []
    for _, row in top.iterrows():
        name = str(row.get("板块名称", ""))
        change_pct = row.get("涨跌幅", 0)
        if change_pct is None or (isinstance(change_pct, float) and change_pct != change_pct):
            change_pct = 0

        leader_name = str(row.get("领涨股票", ""))
        leader_code = str(row.get("领涨股票-代码", ""))

        stocks = []
        try:
            cons_df = ak.stock_board_concept_cons_em(symbol=name)
            if cons_df is not None and not cons_df.empty:
                stocks = cons_df["代码"].tolist()[:30]
        except Exception:
            pass

        sectors.append({
            "name": name,
            "change_pct": float(change_pct) if change_pct else 0,
            "leader": leader_name,
            "leader_symbol": leader_code,
            "stocks": stocks,
        })
        time.sleep(0.3)

    return sectors


def _fetch_sectors_eastmoney() -> list[dict]:
    """Fallback: fetch hot concepts from Eastmoney HTTP API."""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "20",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90+t:3",
        "fields": "f2,f3,f12,f14,f128,f140,f141",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15, proxies=_PROXIES)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data", {}).get("diff", [])
    if not items:
        return []

    sectors = []
    for item in items:
        sectors.append({
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "leader": item.get("f128", ""),
            "leader_symbol": item.get("f140", ""),
            "stocks": [],
        })
    return sectors


def get_hot_stock_set() -> set[str]:
    """Return a set of stock codes that appear in today's hot sectors."""
    sectors = fetch_hot_sectors()
    hot = set()
    for s in sectors:
        hot.update(s.get("stocks", []))
        if s.get("leader_symbol"):
            hot.add(s["leader_symbol"])
    return hot


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sectors = fetch_hot_sectors()
    for s in sectors[:5]:
        print(f"  {s['name']:12s}  涨跌: {s['change_pct']:+.2f}%  领涨: {s['leader']} ({s['leader_symbol']})")
    print(f"\n热门股票总数: {len(get_hot_stock_set())}")
