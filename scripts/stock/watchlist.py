"""
Watchlist management for stock tracking.

Manages a personal list of stocks to monitor daily.
Supports add/remove, batch data refresh, and status overview.
"""
import json
import os
import logging
from datetime import datetime

from config import WATCHLIST_FILE, STOCK_DATA_DIR

log = logging.getLogger(__name__)

_DEFAULT_WATCHLIST = {
    "stocks": [],
    "sectors": [],
    "updated_at": None,
}


def _load_raw() -> dict:
    if os.path.isfile(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                log.warning("watchlist.json 格式异常, 使用默认值")
                return dict(_DEFAULT_WATCHLIST)
            data.setdefault("stocks", [])
            data.setdefault("sectors", [])
            data.setdefault("updated_at", None)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            log.error("watchlist.json 解析失败 (%s), 使用默认值", e)
            return dict(_DEFAULT_WATCHLIST)
    return dict(_DEFAULT_WATCHLIST)


def _save(data: dict):
    data["updated_at"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_stocks() -> list[dict]:
    """返回 watchlist 中所有股票."""
    return _load_raw().get("stocks", [])


def add_stock(symbol: str, name: str = "", sector: str = "", notes: str = "") -> dict:
    """
    添加股票到 watchlist.  If name/sector are empty, auto-resolve from market data.

    Args:
        symbol: 股票代码, e.g. "600519"
        name: 股票名称, e.g. "贵州茅台"
        sector: 所属行业
        notes: 备注

    Returns:
        新添加的股票记录
    """
    data = _load_raw()
    existing = {s["symbol"] for s in data["stocks"]}
    if symbol in existing:
        log.info("股票 %s 已在 watchlist 中", symbol)
        return next(s for s in data["stocks"] if s["symbol"] == symbol)

    if not name or not sector:
        resolved_name, resolved_sector = _resolve_stock_info(symbol)
        if not name:
            name = resolved_name
        if not sector:
            sector = resolved_sector

    entry = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "added": datetime.now().strftime("%Y-%m-%d"),
        "notes": notes,
    }
    data["stocks"].append(entry)
    _save(data)
    log.info("已添加 %s (%s) 到 watchlist", symbol, name)
    return entry


def _resolve_stock_info(symbol: str) -> tuple[str, str]:
    """Try to resolve stock name and sector from local cache or akshare."""
    name, sector = "", ""

    realtime_path = os.path.join(STOCK_DATA_DIR, symbol, "realtime.json")
    if os.path.isfile(realtime_path):
        try:
            with open(realtime_path, encoding="utf-8") as f:
                rt = json.load(f)
            name = rt.get("名称", "")
        except Exception:
            pass

    profile_path = os.path.join(STOCK_DATA_DIR, symbol, "profile.json")
    if os.path.isfile(profile_path):
        try:
            with open(profile_path, encoding="utf-8") as f:
                profile = json.load(f)
            if not name:
                name = profile.get("股票简称", "")
            sector = profile.get("行业", "")
        except Exception:
            pass

    if not name:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == symbol]
            if not row.empty:
                name = str(row.iloc[0].get("名称", ""))
        except Exception as e:
            log.debug("akshare 查询 %s 名称失败: %s", symbol, e)

    if not sector and name:
        try:
            from fetch_market_data import fetch_company_profile
            profile = fetch_company_profile(symbol)
            sector = profile.get("行业", "")
        except Exception:
            pass

    return name, sector


def remove_stock(symbol: str) -> bool:
    """从 watchlist 移除股票. 返回是否成功."""
    data = _load_raw()
    before = len(data["stocks"])
    data["stocks"] = [s for s in data["stocks"] if s["symbol"] != symbol]
    if len(data["stocks"]) < before:
        _save(data)
        log.info("已从 watchlist 移除 %s", symbol)
        return True
    return False


def get_stock(symbol: str) -> dict | None:
    """获取 watchlist 中某只股票的信息."""
    for s in list_stocks():
        if s["symbol"] == symbol:
            return s
    return None


def update_stock_notes(symbol: str, notes: str) -> bool:
    """更新股票备注."""
    data = _load_raw()
    for s in data["stocks"]:
        if s["symbol"] == symbol:
            s["notes"] = notes
            _save(data)
            return True
    return False


def get_watchlist_with_prices() -> list[dict]:
    """
    返回 watchlist 中所有股票, 附带最新缓存价格信息.

    每只股票额外包含: latest_price, change_pct, market_cap (来自本地缓存).
    """
    stocks = list_stocks()
    enriched = []
    for s in stocks:
        entry = dict(s)
        realtime_path = os.path.join(STOCK_DATA_DIR, s["symbol"], "realtime.json")
        if os.path.isfile(realtime_path):
            try:
                with open(realtime_path, encoding="utf-8") as f:
                    rt = json.load(f)
                entry["latest_price"] = rt.get("最新价")
                entry["change_pct"] = rt.get("涨跌幅")
                entry["market_cap"] = rt.get("总市值")
                entry["pe"] = rt.get("市盈率-动态")
                entry["pb"] = rt.get("市净率")
                entry["volume"] = rt.get("成交量")
                entry["fetched_at"] = rt.get("_fetched_at")
            except Exception:
                pass

        profile_path = os.path.join(STOCK_DATA_DIR, s["symbol"], "profile.json")
        if os.path.isfile(profile_path) and not entry.get("sector"):
            try:
                with open(profile_path, encoding="utf-8") as f:
                    profile = json.load(f)
                entry["sector"] = profile.get("行业", "")
                if not entry.get("name"):
                    entry["name"] = profile.get("股票简称", "")
            except Exception:
                pass

        if not entry.get("name"):
            realtime_path2 = os.path.join(STOCK_DATA_DIR, s["symbol"], "realtime.json")
            if os.path.isfile(realtime_path2):
                try:
                    with open(realtime_path2, encoding="utf-8") as f:
                        rt2 = json.load(f)
                    entry["name"] = rt2.get("名称", "")
                except Exception:
                    pass

        enriched.append(entry)
    return enriched


def refresh_all_data() -> list[dict]:
    """
    刷新 watchlist 中所有股票的数据.
    Also backfills missing name/sector from freshly fetched data.

    Returns list of update summaries.
    """
    from fetch_market_data import update_stock_data

    stocks = list_stocks()
    results = []
    for s in stocks:
        log.info("刷新 %s (%s)...", s["symbol"], s.get("name", ""))
        summary = update_stock_data(s["symbol"])
        results.append(summary)

    _backfill_watchlist_info()
    return results


def _backfill_watchlist_info():
    """Fill in empty name/sector fields from local cached data (profile.json, realtime.json)."""
    data = _load_raw()
    changed = False
    for s in data["stocks"]:
        sym = s.get("symbol", "")
        if not sym:
            continue
        if s.get("name") and s.get("sector"):
            continue

        resolved_name, resolved_sector = _resolve_stock_info(sym)
        if not s.get("name") and resolved_name:
            s["name"] = resolved_name
            changed = True
        if not s.get("sector") and resolved_sector:
            s["sector"] = resolved_sector
            changed = True

    if changed:
        _save(data)
        log.info("已回填 watchlist 中缺失的名称/行业信息")


def search_stock(keyword: str) -> list[dict]:
    """
    搜索股票 (按代码或名称).

    使用 akshare 实时行情数据搜索.
    Returns list of matching stocks (max 20).
    """
    import akshare as ak

    try:
        df = ak.stock_zh_a_spot_em()
        mask = df["代码"].str.contains(keyword) | df["名称"].str.contains(keyword)
        matches = df[mask].head(20)
        results = []
        for _, row in matches.iterrows():
            results.append({
                "symbol": row["代码"],
                "name": row["名称"],
                "price": row.get("最新价"),
                "change_pct": row.get("涨跌幅"),
                "pe": row.get("市盈率-动态"),
                "market_cap": row.get("总市值"),
            })
        return results
    except Exception as e:
        log.error("搜索失败: %s", e)
        return []


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("用法: watchlist.py <命令> [参数]")
        print("  list          — 显示 watchlist")
        print("  add <代码> [名称] [行业]  — 添加股票")
        print("  remove <代码> — 移除股票")
        print("  refresh       — 刷新所有数据")
        print("  prices        — 显示带价格的列表")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "list":
        for s in list_stocks():
            print(f"  {s['symbol']}  {s.get('name',''):10s}  {s.get('sector',''):10s}  ({s.get('added','')})")

    elif cmd == "add" and len(sys.argv) >= 3:
        sym = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        sector = sys.argv[4] if len(sys.argv) > 4 else ""
        add_stock(sym, name, sector)

    elif cmd == "remove" and len(sys.argv) >= 3:
        remove_stock(sys.argv[2])

    elif cmd == "refresh":
        results = refresh_all_data()
        for r in results:
            print(json.dumps(r, ensure_ascii=False, indent=2))

    elif cmd == "prices":
        for s in get_watchlist_with_prices():
            price = s.get("latest_price", "N/A")
            chg = s.get("change_pct", "N/A")
            print(f"  {s['symbol']}  {s.get('name',''):10s}  价格: {price}  涨跌: {chg}%")

    else:
        print(f"未知命令: {cmd}")
