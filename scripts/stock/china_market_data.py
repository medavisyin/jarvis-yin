"""
中国A股特色数据获取层 — 资金流向、北向资金、龙虎榜、融资融券、涨跌停池。

所有数据通过 akshare 免费获取，按日缓存避免重复请求。
缓存目录: STOCK_CACHE_DIR 下各子目录。

用途:
  - 作为 ML 特征 (资金行为因子、板块轮动、市场温度)
  - Scanner Layer 1/2 选股评分
  - UI 展示参考信号
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from config import STOCK_DATA_DIR, STOCK_CACHE_DIR, STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

_CACHE_NORTHBOUND = os.path.join(STOCK_CACHE_DIR, ".northbound")
_CACHE_FUND_FLOW = os.path.join(STOCK_CACHE_DIR, ".fund_flow")
_CACHE_SECTOR_FLOW = os.path.join(STOCK_CACHE_DIR, ".sector_flow")
_CACHE_LHB = os.path.join(STOCK_CACHE_DIR, ".lhb")
_CACHE_MARGIN = os.path.join(STOCK_CACHE_DIR, ".margin")
_CACHE_LIMIT = os.path.join(STOCK_CACHE_DIR, ".limit_pool")
_CACHE_MARKET_FLOW = os.path.join(STOCK_CACHE_DIR, ".market_flow")

for _d in [_CACHE_NORTHBOUND, _CACHE_FUND_FLOW, _CACHE_SECTOR_FLOW,
           _CACHE_LHB, _CACHE_MARGIN, _CACHE_LIMIT, _CACHE_MARKET_FLOW]:
    os.makedirs(_d, exist_ok=True)

_RETRY_DELAY = 1.5
_MAX_RETRIES = 2


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _cache_fresh(path: str, max_age_hours: float = 12) -> bool:
    """Check if a cache file exists and is fresh enough."""
    if not os.path.isfile(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < max_age_hours * 3600


def _retry(fn, *args, retries=_MAX_RETRIES, delay=_RETRY_DELAY, **kwargs):
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("尝试 %d/%d 失败: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    raise last_err


# ── 1. 北向资金 (Northbound Capital) ────────────────────────

def fetch_northbound(days: int = 120) -> pd.DataFrame:
    """获取北向资金历史数据 (沪深港通)。

    Returns DataFrame with at least columns: 日期, 净买额(亿元)
    Primary source: stock_hsgt_hist_em (contains NaN for recent dates)
    Filters to rows with valid 当日成交净买额 only.
    """
    cache_path = os.path.join(_CACHE_NORTHBOUND, "history_clean.csv")
    if _cache_fresh(cache_path, max_age_hours=8):
        df = pd.read_csv(cache_path, parse_dates=["日期"])
        if len(df) >= min(days * 0.3, 30):
            log.info("北向资金: 从缓存加载 %d 条", len(df))
            return df.tail(days)

    log.info("北向资金: 从东方财富获取...")
    try:
        df = _retry(ak.stock_hsgt_hist_em, symbol="北向资金")
        if df is not None and not df.empty:
            net_col = "当日成交净买额"
            if net_col in df.columns:
                df[net_col] = pd.to_numeric(df[net_col], errors="coerce")
                df = df.dropna(subset=[net_col])
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            log.info("北向资金: 获取 %d 条有效数据, 已缓存", len(df))
            return df.tail(days)
    except Exception as e:
        log.error("北向资金获取失败: %s", e)

    if os.path.isfile(cache_path):
        return pd.read_csv(cache_path, parse_dates=["日期"]).tail(days)
    return pd.DataFrame()


def northbound_momentum(window_short: int = 5, window_long: int = 20) -> dict:
    """计算北向资金动量信号。

    Returns:
        net_today: 今日净买入(亿元)
        net_5d: 5日累计净买入
        net_20d: 20日累计净买入
        momentum: 短期均值 / 长期均值 (>1 = 加速流入)
        consecutive: 连续净买入天数(负数=连续净卖出)
        trend: "加速流入" / "减速流入" / "流出" / "加速流出"
    """
    df = fetch_northbound(days=max(window_long + 5, 30))
    result = {
        "net_today": 0, "net_5d": 0, "net_20d": 0,
        "momentum": 1.0, "consecutive": 0, "trend": "无数据",
    }
    if df.empty:
        return result

    net_col = "当日成交净买额"
    if net_col not in df.columns:
        for col in df.columns:
            if "净" in col and "买" in col:
                net_col = col
                break

    if net_col not in df.columns:
        return result

    series = pd.to_numeric(df[net_col], errors="coerce").dropna()
    if series.empty:
        log.warning("北向资金: 所有净买额数据为 NaN (可能是假期/数据延迟)")
        return result
    vals = series.tolist()
    if not vals:
        return result

    result["net_today"] = round(vals[-1], 2)
    result["net_5d"] = round(sum(vals[-window_short:]), 2)
    result["net_20d"] = round(sum(vals[-window_long:]), 2)

    avg_short = sum(vals[-window_short:]) / window_short if len(vals) >= window_short else 0
    avg_long = sum(vals[-window_long:]) / window_long if len(vals) >= window_long else 1
    if abs(avg_long) > 0.01:
        result["momentum"] = round(avg_short / avg_long, 3)

    consec = 0
    for v in reversed(vals):
        if v > 0:
            if consec >= 0:
                consec += 1
            else:
                break
        elif v < 0:
            if consec <= 0:
                consec -= 1
            else:
                break
        else:
            break
    result["consecutive"] = consec

    mom = result["momentum"]
    if mom > 1.3:
        result["trend"] = "加速流入"
    elif mom > 0.7:
        result["trend"] = "温和流入" if result["net_5d"] > 0 else "温和流出"
    elif mom > 0:
        result["trend"] = "减速流入"
    else:
        result["trend"] = "加速流出"

    return result


# ── 2. 个股资金流向 (Per-Stock Fund Flow) ───────────────────

def fetch_stock_fund_flow(symbol: str) -> pd.DataFrame:
    """获取个股资金流向 (近100个交易日)。

    Returns DataFrame: 日期, 主力净流入, 超大单净流入, 大单净流入, 中单净流入, 小单净流入, ...
    """
    cache_path = os.path.join(_CACHE_FUND_FLOW, f"{symbol}.csv")
    if _cache_fresh(cache_path, max_age_hours=8):
        log.debug("个股资金流向 %s: 从缓存加载", symbol)
        return pd.read_csv(cache_path)

    market = "sh" if symbol.startswith(("6", "5", "9")) else "sz"
    log.info("个股资金流向 %s: 从东方财富获取...", symbol)
    try:
        df = _retry(ak.stock_individual_fund_flow, stock=symbol, market=market)
        if df is not None and not df.empty:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            log.info("个股资金流向 %s: 获取 %d 条", symbol, len(df))
            return df
    except Exception as e:
        log.warning("个股资金流向 %s 获取失败: %s", symbol, e)

    if os.path.isfile(cache_path):
        return pd.read_csv(cache_path)
    return pd.DataFrame()


def stock_fund_flow_signals(symbol: str) -> dict:
    """为个股计算资金流向信号。"""
    df = fetch_stock_fund_flow(symbol)
    result = {
        "main_net_3d": 0, "main_net_10d": 0, "main_pct_3d": 0,
        "super_large_ratio": 0, "accumulation_signal": False,
        "data_days": 0,
    }
    if df.empty or len(df) < 3:
        return result

    net_col = None
    pct_col = None
    super_col = None
    for col in df.columns:
        if "主力净流入" in col and "净额" in col:
            net_col = col
        elif "主力净流入" in col and "净占比" in col:
            pct_col = col
        elif "超大单" in col and "净额" in col:
            super_col = col

    if net_col is None:
        for col in df.columns:
            if "主力" in col and "净" in col:
                net_col = col
                break
    if net_col is None:
        return result

    vals = pd.to_numeric(df[net_col], errors="coerce").fillna(0).tolist()
    result["data_days"] = len(vals)
    result["main_net_3d"] = round(sum(vals[-3:]), 2)
    result["main_net_10d"] = round(sum(vals[-10:]) if len(vals) >= 10 else sum(vals), 2)

    if pct_col:
        pcts = pd.to_numeric(df[pct_col], errors="coerce").fillna(0).tolist()
        result["main_pct_3d"] = round(sum(pcts[-3:]), 4)

    if super_col and net_col:
        super_vals = pd.to_numeric(df[super_col], errors="coerce").fillna(0)
        net_vals = pd.to_numeric(df[net_col], errors="coerce").fillna(0)
        total_abs = net_vals.abs().sum()
        if total_abs > 0:
            result["super_large_ratio"] = round(super_vals.sum() / total_abs, 3)

    result["accumulation_signal"] = result["main_net_3d"] > 0

    try:
        accum = detect_smart_money_accumulation(symbol, df, net_col, pct_col)
        result.update(accum)
    except Exception as e:
        log.debug("聪明钱检测 %s 失败: %s", symbol, e)

    return result


def detect_smart_money_accumulation(symbol: str, ff_df: pd.DataFrame,
                                     net_col: str, pct_col: str = None) -> dict:
    """检测聪明钱布局期信号 — 资金进但价格不涨。

    核心逻辑:
      - 资金持续流入 (3日/5日主力净流入 > 0)
      - 价格横盘或微跌 (近5日涨幅 < 2%)
      - 两者背离越大 = 吸筹信号越强

    Returns dict with:
      - smart_money_phase: "布局期" / "拉升期" / "出货期" / "无信号"
      - accumulation_score: 0-100
      - accumulation_signal: True/False (upgraded)
      - fund_price_divergence: 资金强度与价格变化的背离度
      - detail: 中文说明
    """
    result = {
        "smart_money_phase": "无信号",
        "accumulation_score": 0,
        "fund_price_divergence": 0,
        "detail": "",
    }

    if ff_df is None or ff_df.empty or len(ff_df) < 5:
        return result

    vals = pd.to_numeric(ff_df[net_col], errors="coerce").fillna(0).tolist()
    if len(vals) < 5:
        return result

    net_3d = sum(vals[-3:])
    net_5d = sum(vals[-5:])

    positive_days_5 = sum(1 for v in vals[-5:] if v > 0)

    try:
        import akshare as _ak
        hist = _ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                    start_date=(datetime.now() - timedelta(days=15)).strftime("%Y%m%d"),
                                    end_date=datetime.now().strftime("%Y%m%d"), adjust="qfq")
        if hist is not None and len(hist) >= 5:
            closes = pd.to_numeric(hist["收盘"], errors="coerce").tolist()
            price_chg_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] else 0
            price_chg_3d = (closes[-1] - closes[-3]) / closes[-3] * 100 if closes[-3] else 0
        else:
            price_chg_5d = 0
            price_chg_3d = 0
    except Exception:
        price_chg_5d = 0
        price_chg_3d = 0

    fund_strength = 0
    if net_5d > 0:
        fund_strength += 30
    if net_3d > 0:
        fund_strength += 20
    if positive_days_5 >= 3:
        fund_strength += 15
    if positive_days_5 >= 4:
        fund_strength += 10

    if pct_col and pct_col in ff_df.columns:
        pcts = pd.to_numeric(ff_df[pct_col], errors="coerce").fillna(0).tolist()
        pct_3d = sum(pcts[-3:])
        if pct_3d > 1:
            fund_strength += 15
        elif pct_3d > 0.3:
            fund_strength += 8

    price_quiet = 0
    if abs(price_chg_5d) < 2:
        price_quiet += 30
    if abs(price_chg_5d) < 1:
        price_quiet += 10
    if price_chg_5d < 0 and price_chg_5d > -5:
        price_quiet += 10

    divergence = fund_strength - (price_chg_5d * 10 if price_chg_5d > 0 else 0)
    result["fund_price_divergence"] = round(divergence, 1)

    accum_score = min(100, max(0, int(fund_strength * 0.5 + price_quiet * 0.5)))
    result["accumulation_score"] = accum_score

    if fund_strength >= 50 and price_chg_5d < 2:
        result["smart_money_phase"] = "布局期"
        result["accumulation_signal"] = True
        if price_chg_5d < 0:
            result["detail"] = f"资金持续流入(5日{positive_days_5}天净流入)但股价微跌{price_chg_5d:.1f}%，典型吸筹模式"
        else:
            result["detail"] = f"资金持续流入(5日{positive_days_5}天净流入)股价横盘({price_chg_5d:+.1f}%)，主力悄悄建仓"
    elif fund_strength >= 40 and price_chg_5d > 5:
        result["smart_money_phase"] = "拉升期"
        result["accumulation_signal"] = False
        result["detail"] = f"资金流入且股价已涨{price_chg_5d:.1f}%，可能已进入拉升期，追高风险大"
    elif fund_strength < 20 and price_chg_5d > 3:
        result["smart_money_phase"] = "出货期"
        result["accumulation_signal"] = False
        result["detail"] = f"资金流出但股价仍涨{price_chg_5d:.1f}%，可能主力出货中"
    elif fund_strength < 20:
        result["smart_money_phase"] = "无信号"
        result["accumulation_signal"] = False
        result["detail"] = "资金流入不明显"
    else:
        result["smart_money_phase"] = "观察期"
        result["accumulation_signal"] = False
        result["detail"] = f"资金有流入迹象但尚未达到布局标准(得分{accum_score})"

    return result


# ── 3. 板块资金流向 (Sector Fund Flow) ──────────────────────

def fetch_sector_flow(sector_type: str = "行业资金流",
                      period: str = "今日") -> pd.DataFrame:
    """获取板块资金流向排名。

    sector_type: "行业资金流" / "概念资金流" / "地域资金流"
    period: "今日" / "5日" / "10日"
    """
    cache_name = f"{sector_type}_{period}_{_today_str()}.json"
    cache_path = os.path.join(_CACHE_SECTOR_FLOW, cache_name)
    if _cache_fresh(cache_path, max_age_hours=6):
        return pd.read_json(cache_path, encoding="utf-8")

    log.info("板块资金流向: %s %s ...", sector_type, period)
    try:
        time.sleep(0.5)
        df = _retry(ak.stock_sector_fund_flow_rank,
                     indicator=period, sector_type=sector_type,
                     retries=3, delay=2.0)
        if df is not None and not df.empty:
            df.to_json(cache_path, force_ascii=False, orient="records", indent=2)
            log.info("板块资金流向: 获取 %d 个板块", len(df))
            return df
    except Exception as e:
        log.warning("板块资金流向获取失败: %s", e)
    return pd.DataFrame()


def sector_rotation_score(sector_name: str) -> dict:
    """计算某板块的轮动热度评分。"""
    result = {"rank_today": 0, "rank_5d": 0, "momentum": 0, "is_hot": False}

    for period, key in [("今日", "rank_today"), ("5日", "rank_5d")]:
        df = fetch_sector_flow(period=period)
        if df.empty:
            continue
        name_col = None
        for col in df.columns:
            if "板块" in col and "名" in col:
                name_col = col
                break
        if name_col is None:
            continue
        total = len(df)
        match = df[df[name_col].str.contains(sector_name, na=False)]
        if not match.empty:
            idx = match.index[0]
            result[key] = round(1 - idx / max(total, 1), 3)

    if result["rank_today"] > 0 and result["rank_5d"] > 0:
        result["momentum"] = round(result["rank_today"] - result["rank_5d"], 3)
    result["is_hot"] = result["rank_today"] > 0.7

    return result


def get_hot_sectors(top_n: int = 10) -> list[str]:
    """获取今日资金流入排名前N的板块名称。"""
    df = fetch_sector_flow(period="今日")
    if df.empty:
        return []
    name_col = None
    for col in df.columns:
        if "板块" in col and "名" in col:
            name_col = col
            break
    if name_col is None:
        return []
    return df[name_col].head(top_n).tolist()


# ── 4. 龙虎榜 (Top Buyer/Seller Disclosure) ────────────────

def fetch_lhb_institutional(recent_days: int = 5) -> pd.DataFrame:
    """获取龙虎榜机构席位追踪数据。"""
    cache_path = os.path.join(_CACHE_LHB, f"track_{recent_days}d_{_today_str()}.json")
    if _cache_fresh(cache_path, max_age_hours=12):
        return pd.read_json(cache_path, encoding="utf-8")

    log.info("龙虎榜机构追踪: 最近 %d 天...", recent_days)
    try:
        df = _retry(ak.stock_lhb_jgzz_sina, symbol=str(recent_days))
        if df is not None and not df.empty:
            df.to_json(cache_path, force_ascii=False, orient="records", indent=2)
            log.info("龙虎榜: 获取 %d 条机构数据", len(df))
            return df
    except Exception as e:
        log.warning("龙虎榜获取失败: %s", e)
    return pd.DataFrame()


def fetch_lhb_detail() -> pd.DataFrame:
    """获取龙虎榜机构席位成交明细。"""
    cache_path = os.path.join(_CACHE_LHB, f"detail_{_today_str()}.json")
    if _cache_fresh(cache_path, max_age_hours=12):
        return pd.read_json(cache_path, encoding="utf-8")

    log.info("龙虎榜机构明细...")
    try:
        df = _retry(ak.stock_lhb_jgmx_sina)
        if df is not None and not df.empty:
            df.to_json(cache_path, force_ascii=False, orient="records", indent=2)
            log.info("龙虎榜明细: 获取 %d 条", len(df))
            return df
    except Exception as e:
        log.warning("龙虎榜明细获取失败: %s", e)
    return pd.DataFrame()


def stock_lhb_activity(symbol: str, recent_days: int = 5) -> dict:
    """查询某个股票在龙虎榜中的机构活动。"""
    result = {"appeared": False, "inst_net_buy": 0, "buy_count": 0, "sell_count": 0}

    df = fetch_lhb_institutional(recent_days)
    if df.empty:
        return result

    code_col = None
    for col in df.columns:
        if "代码" in col:
            code_col = col
            break
    if code_col is None:
        return result

    match = df[df[code_col].astype(str).str.contains(symbol, na=False)]
    if match.empty:
        return result

    result["appeared"] = True
    row = match.iloc[0]

    for col in match.columns:
        if "买入" in col and "额" in col:
            result["inst_net_buy"] += pd.to_numeric(row.get(col, 0), errors="coerce") or 0
        if "卖出" in col and "额" in col:
            result["inst_net_buy"] -= pd.to_numeric(row.get(col, 0), errors="coerce") or 0
        if "买入" in col and "次" in col:
            result["buy_count"] = int(pd.to_numeric(row.get(col, 0), errors="coerce") or 0)
        if "卖出" in col and "次" in col:
            result["sell_count"] = int(pd.to_numeric(row.get(col, 0), errors="coerce") or 0)

    result["inst_net_buy"] = round(result["inst_net_buy"], 2)
    return result


# ── 5. 融资融券 (Margin Trading) ────────────────────────────

def fetch_margin_data(days: int = 60) -> pd.DataFrame:
    """获取上交所融资融券汇总数据。"""
    cache_path = os.path.join(_CACHE_MARGIN, "sse.csv")
    if _cache_fresh(cache_path, max_age_hours=12):
        df = pd.read_csv(cache_path)
        if len(df) >= days * 0.5:
            return df.tail(days)

    end_date = _today_str()
    start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
    log.info("融资融券: %s ~ %s ...", start_date, end_date)
    try:
        df = _retry(ak.stock_margin_sse, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            log.info("融资融券: 获取 %d 条", len(df))
            return df.tail(days)
    except Exception as e:
        log.warning("融资融券获取失败: %s", e)

    if os.path.isfile(cache_path):
        return pd.read_csv(cache_path).tail(days)
    return pd.DataFrame()


def margin_sentiment(window: int = 5) -> dict:
    """融资融券情绪指标。"""
    df = fetch_margin_data(days=max(window + 10, 30))
    result = {"balance_change_pct": 0, "trend": "无数据", "balance_latest": 0}

    if df.empty or len(df) < 3:
        return result

    bal_col = None
    for col in df.columns:
        if "融资" in col and "余额" in col:
            bal_col = col
            break
    if bal_col is None:
        return result

    vals = pd.to_numeric(df[bal_col], errors="coerce").dropna().tolist()
    if len(vals) < 2:
        return result

    result["balance_latest"] = round(vals[-1], 2)
    if len(vals) >= window:
        old = vals[-window]
        if old > 0:
            result["balance_change_pct"] = round((vals[-1] - old) / old * 100, 3)

    chg = result["balance_change_pct"]
    if chg > 2:
        result["trend"] = "杠杆加速"
    elif chg > 0.5:
        result["trend"] = "温和加杠杆"
    elif chg > -0.5:
        result["trend"] = "平稳"
    elif chg > -2:
        result["trend"] = "温和去杠杆"
    else:
        result["trend"] = "快速去杠杆"

    return result


# ── 6. 涨跌停池 (Limit Up/Down Pool) ───────────────────────

def fetch_limit_pool(date: str = "", direction: str = "涨停") -> pd.DataFrame:
    """获取涨停或跌停池数据。"""
    if not date:
        date = _today_str()
    tag = "zt" if direction == "涨停" else "dt"
    cache_path = os.path.join(_CACHE_LIMIT, f"{date}_{tag}.json")
    if _cache_fresh(cache_path, max_age_hours=12):
        return pd.read_json(cache_path, encoding="utf-8")

    log.info("%s池: %s ...", direction, date)
    try:
        if direction == "涨停":
            df = _retry(ak.stock_zt_pool_em, date=date)
        else:
            df = _retry(ak.stock_dt_pool_em, date=date)
        if df is not None and not df.empty:
            df.to_json(cache_path, force_ascii=False, orient="records", indent=2)
            log.info("%s池: %d 只", direction, len(df))
            return df
    except Exception as e:
        log.debug("%s池 %s 获取失败: %s", direction, date, e)
    return pd.DataFrame()


def market_temperature(date: str = "") -> dict:
    """市场温度: 涨停/跌停数量比。"""
    zt = fetch_limit_pool(date, "涨停")
    dt = fetch_limit_pool(date, "跌停")
    zt_count = len(zt)
    dt_count = len(dt)
    total = zt_count + dt_count

    ratio = zt_count / max(total, 1)

    if ratio > 0.85 and zt_count > 30:
        mood = "极热"
    elif ratio > 0.7 and zt_count > 15:
        mood = "偏热"
    elif ratio < 0.3 and dt_count > 15:
        mood = "恐慌"
    elif ratio < 0.5 and dt_count > 10:
        mood = "偏冷"
    else:
        mood = "正常"

    return {
        "zt_count": zt_count,
        "dt_count": dt_count,
        "ratio": round(ratio, 3),
        "mood": mood,
        "date": date or _today_str(),
    }


# ── 7. 大盘资金流 (Market-wide Fund Flow) ──────────────────

def fetch_market_fund_flow(days: int = 60) -> pd.DataFrame:
    """获取大盘主力资金流向历史。"""
    cache_path = os.path.join(_CACHE_MARKET_FLOW, "history.csv")
    if _cache_fresh(cache_path, max_age_hours=8):
        df = pd.read_csv(cache_path)
        if len(df) >= days * 0.5:
            return df.tail(days)

    log.info("大盘资金流: 获取中...")
    try:
        df = _retry(ak.stock_market_fund_flow)
        if df is not None and not df.empty:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            log.info("大盘资金流: 获取 %d 条", len(df))
            return df.tail(days)
    except Exception as e:
        log.warning("大盘资金流获取失败: %s", e)

    if os.path.isfile(cache_path):
        return pd.read_csv(cache_path).tail(days)
    return pd.DataFrame()


# ── 8. 国家队监控 (National Team / ETF Share Tracking) ──────

_CACHE_NATIONAL = os.path.join(STOCK_CACHE_DIR, ".national_team")
os.makedirs(_CACHE_NATIONAL, exist_ok=True)

CORE_ETF_LIST = [
    {"code": "510300", "name": "300ETF", "exchange": "sse", "index": "沪深300", "type": "宽基"},
    {"code": "510500", "name": "500ETF", "exchange": "sse", "index": "中证500", "type": "宽基"},
    {"code": "510050", "name": "50ETF", "exchange": "sse", "index": "上证50", "type": "宽基"},
    {"code": "510880", "name": "红利ETF", "exchange": "sse", "index": "上证红利", "type": "宽基"},
    {"code": "159919", "name": "300ETF(深)", "exchange": "szse", "index": "沪深300", "type": "宽基"},
    {"code": "159915", "name": "创业板ETF", "exchange": "szse", "index": "创业板指", "type": "宽基"},
    {"code": "512100", "name": "1000ETF", "exchange": "sse", "index": "中证1000", "type": "宽基"},
    {"code": "159922", "name": "500ETF(深)", "exchange": "szse", "index": "中证500", "type": "宽基"},
    {"code": "588000", "name": "科创50ETF", "exchange": "sse", "index": "科创50", "type": "宽基"},
    {"code": "513050", "name": "中概互联ETF", "exchange": "sse", "index": "中国互联网50", "type": "行业"},
    {"code": "512010", "name": "医药ETF", "exchange": "sse", "index": "中证医药", "type": "行业"},
    {"code": "512880", "name": "证券ETF", "exchange": "sse", "index": "中证证券", "type": "行业"},
    {"code": "515030", "name": "新能源ETF", "exchange": "sse", "index": "中证新能", "type": "行业"},
    {"code": "512480", "name": "半导体ETF", "exchange": "sse", "index": "半导体", "type": "行业"},
    {"code": "512660", "name": "军工ETF", "exchange": "sse", "index": "中证军工", "type": "行业"},
    {"code": "515790", "name": "光伏ETF", "exchange": "sse", "index": "光伏产业", "type": "行业"},
]


def fetch_etf_shares_sse(date: str = "") -> pd.DataFrame:
    """获取上交所ETF份额数据。尝试今日,失败后回退近5个交易日。"""
    if not date:
        date = _today_str()

    cache_path = os.path.join(_CACHE_NATIONAL, f"sse_latest.csv")
    if _cache_fresh(cache_path, max_age_hours=12):
        return pd.read_csv(cache_path)

    dates_to_try = [date]
    for offset in range(1, 6):
        d = (datetime.now() - timedelta(days=offset))
        if d.weekday() < 5:
            dates_to_try.append(d.strftime("%Y%m%d"))

    for try_date in dates_to_try:
        log.info("上交所ETF份额: 尝试 %s ...", try_date)
        try:
            df = ak.fund_etf_scale_sse(date=try_date)
            if df is not None and not df.empty and len(df) > 5:
                df.to_csv(cache_path, index=False, encoding="utf-8-sig")
                log.info("上交所ETF: 获取 %d 只 (日期 %s)", len(df), try_date)
                return df
        except Exception as e:
            log.debug("上交所ETF %s 失败: %s", try_date, e)
            time.sleep(0.5)

    log.warning("上交所ETF份额: 所有日期均失败")
    if os.path.isfile(cache_path):
        return pd.read_csv(cache_path)
    return pd.DataFrame()


def fetch_etf_shares_szse() -> pd.DataFrame:
    """获取深交所ETF份额数据 (仅最新日)。"""
    cache_path = os.path.join(_CACHE_NATIONAL, f"szse_{_today_str()}.csv")
    if _cache_fresh(cache_path, max_age_hours=12):
        return pd.read_csv(cache_path)

    log.info("深交所ETF份额...")
    try:
        df = _retry(ak.fund_etf_scale_szse)
        if df is not None and not df.empty:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            log.info("深交所ETF: 获取 %d 只", len(df))
            return df
    except Exception as e:
        log.warning("深交所ETF份额获取失败: %s", e)
    return pd.DataFrame()


def _get_etf_share(etf_code: str, sse_df: pd.DataFrame,
                   szse_df: pd.DataFrame) -> float | None:
    """从已加载的交易所数据中提取指定ETF的份额。"""
    code_cols = ["基金代码", "代码", "证券代码"]
    share_cols = ["基金份额", "份额", "流通份额"]

    for df, label in [(sse_df, "SSE"), (szse_df, "SZSE")]:
        if df.empty:
            continue
        code_col = None
        share_col = None
        for c in code_cols:
            if c in df.columns:
                code_col = c
                break
        for c in share_cols:
            if c in df.columns:
                share_col = c
                break
        if code_col is None or share_col is None:
            continue

        match = df[df[code_col].astype(str).str.strip() == etf_code]
        if not match.empty:
            val = pd.to_numeric(match[share_col].iloc[0], errors="coerce")
            if pd.notna(val):
                return float(val)
    return None


def fetch_etf_share_history(etf_code: str, dates: list[str] = None) -> list[dict]:
    """获取ETF在多个日期的份额，用于计算变化趋势。

    如果不提供dates，默认取近5个交易日（近似）。
    """
    if dates is None:
        from datetime import timedelta
        now = datetime.now()
        dates = []
        for offset in [0, 1, 5, 10, 20, 60]:
            d = (now - timedelta(days=offset))
            if d.weekday() < 5:
                dates.append(d.strftime("%Y%m%d"))
            else:
                d = d - timedelta(days=d.weekday() - 4)
                dates.append(d.strftime("%Y%m%d"))
        dates = sorted(set(dates))

    history = []
    for date in dates:
        sse_df = fetch_etf_shares_sse(date)
        szse_df = pd.DataFrame()
        share = _get_etf_share(etf_code, sse_df, szse_df)
        if share is not None:
            history.append({"date": date, "shares": share})

    return history


def national_team_monitor() -> dict:
    """监控国家队核心ETF份额变化。

    Returns:
        {
            "date": str,
            "etf_snapshot": [
                {"code": "510300", "name": "300ETF", "shares": 4.24e10,
                 "shares_yi": 424.4, "type": "宽基", "index": "沪深300"},
                ...
            ],
            "total_broad_shares_yi": float,  # 宽基ETF总份额(亿份)
            "signals": {
                "broad_total_change": "大幅增持" | "温和增持" | "平稳" | "温和减持" | "大幅减持",
                "anomalies": [...],  # 异常变动
            },
        }
    """
    log.info("国家队ETF监控: 获取数据...")
    result = {
        "date": _today_str(),
        "etf_snapshot": [],
        "total_broad_shares_yi": 0,
        "total_sector_shares_yi": 0,
        "signals": {"broad_total_change": "无数据", "anomalies": []},
    }

    sse_df = fetch_etf_shares_sse()
    szse_df = fetch_etf_shares_szse()

    broad_total = 0
    sector_total = 0

    for etf in CORE_ETF_LIST:
        share = _get_etf_share(etf["code"], sse_df, szse_df)
        shares_yi = round(share / 1e8, 2) if share else None

        entry = {
            "code": etf["code"],
            "name": etf["name"],
            "index": etf["index"],
            "type": etf["type"],
            "shares": share,
            "shares_yi": shares_yi,
        }
        result["etf_snapshot"].append(entry)

        if shares_yi:
            if etf["type"] == "宽基":
                broad_total += shares_yi
            else:
                sector_total += shares_yi

    result["total_broad_shares_yi"] = round(broad_total, 2)
    result["total_sector_shares_yi"] = round(sector_total, 2)

    _detect_share_anomalies(result)

    cache_path = os.path.join(_CACHE_NATIONAL, f"snapshot_{_today_str()}.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    _append_history(result)
    _save_national_team_knowledge(result)

    log.info("国家队监控: 宽基总份额 %.1f 亿份, 行业总份额 %.1f 亿份",
             broad_total, sector_total)
    return result


def _detect_share_anomalies(result: dict):
    """对比历史快照,检测异常份额变化。"""
    history = _load_national_history()
    if not history:
        return

    prev = history[-1]
    prev_broad = prev.get("total_broad_shares_yi", 0)
    curr_broad = result["total_broad_shares_yi"]

    if prev_broad > 0 and curr_broad > 0:
        change_pct = (curr_broad - prev_broad) / prev_broad * 100
        if change_pct > 5:
            result["signals"]["broad_total_change"] = "大幅增持"
        elif change_pct > 1:
            result["signals"]["broad_total_change"] = "温和增持"
        elif change_pct < -5:
            result["signals"]["broad_total_change"] = "大幅减持"
        elif change_pct < -1:
            result["signals"]["broad_total_change"] = "温和减持"
        else:
            result["signals"]["broad_total_change"] = "平稳"

        prev_etfs = {e["code"]: e for e in prev.get("etf_snapshot", [])}
        for etf in result["etf_snapshot"]:
            code = etf["code"]
            curr_yi = etf.get("shares_yi")
            prev_etf = prev_etfs.get(code)
            if curr_yi and prev_etf and prev_etf.get("shares_yi"):
                prev_yi = prev_etf["shares_yi"]
                etf_chg = (curr_yi - prev_yi) / prev_yi * 100
                etf["change_pct"] = round(etf_chg, 2)

                if abs(etf_chg) > 3:
                    direction = "增持" if etf_chg > 0 else "减持"
                    result["signals"]["anomalies"].append({
                        "code": code,
                        "name": etf["name"],
                        "change_pct": round(etf_chg, 2),
                        "direction": direction,
                        "prev_yi": round(prev_yi, 2),
                        "curr_yi": round(curr_yi, 2),
                    })


def _append_history(snapshot: dict):
    """将快照追加到历史记录。"""
    history_path = os.path.join(_CACHE_NATIONAL, "history.json")
    history = _load_national_history()

    entry = {
        "date": _normalize_date(snapshot["date"]),
        "total_broad_shares_yi": snapshot["total_broad_shares_yi"],
        "total_sector_shares_yi": snapshot["total_sector_shares_yi"],
        "etf_snapshot": snapshot["etf_snapshot"],
    }

    if history and _normalize_date(history[-1].get("date", "")) == entry["date"]:
        history[-1] = entry
    else:
        history.append(entry)

    if len(history) > 365:
        history = history[-365:]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=str)


def _save_national_team_knowledge(snapshot: dict):
    """将国家队监控数据保存为RAG知识文件。"""
    try:
        knowledge_dir = os.path.normpath(
            os.environ.get("JARVIS_REPORTS_ROOT", "C:/reports/ai")
        )
        knowledge_dir = os.path.join(knowledge_dir, "knowledge", "stock")
        os.makedirs(knowledge_dir, exist_ok=True)

        date = snapshot.get("date", _today_str())
        broad = snapshot.get("total_broad_shares_yi", 0)
        sector = snapshot.get("total_sector_shares_yi", 0)
        sigs = snapshot.get("signals", {})

        lines = [
            f"# 国家队ETF监控报告 — {date}",
            "",
            f"## 总览",
            f"- 监控日期: {date}",
            f"- 宽基ETF总份额: {broad:.1f} 亿份",
            f"- 行业ETF总份额: {sector:.1f} 亿份",
            f"- 国家队动向信号: {sigs.get('broad_total_change', '无数据')}",
            "",
            "## 宽基ETF份额详情",
            "| ETF | 代码 | 跟踪指数 | 份额(亿份) | 变化 |",
            "|-----|------|---------|-----------|------|",
        ]

        for e in snapshot.get("etf_snapshot", []):
            if e.get("type") != "宽基":
                continue
            yi = f"{e['shares_yi']:.1f}" if e.get("shares_yi") else "N/A"
            chg = f"{e['change_pct']:+.1f}%" if e.get("change_pct") is not None else "-"
            lines.append(f"| {e['name']} | {e['code']} | {e.get('index','')} | {yi} | {chg} |")

        lines.extend([
            "",
            "## 行业ETF份额详情",
            "| ETF | 代码 | 跟踪指数 | 份额(亿份) | 变化 |",
            "|-----|------|---------|-----------|------|",
        ])

        for e in snapshot.get("etf_snapshot", []):
            if e.get("type") != "行业":
                continue
            yi = f"{e['shares_yi']:.1f}" if e.get("shares_yi") else "N/A"
            chg = f"{e['change_pct']:+.1f}%" if e.get("change_pct") is not None else "-"
            lines.append(f"| {e['name']} | {e['code']} | {e.get('index','')} | {yi} | {chg} |")

        anomalies = sigs.get("anomalies", [])
        if anomalies:
            lines.extend(["", "## 异常变动"])
            for a in anomalies:
                lines.append(
                    f"- **{a['name']}** ({a['code']}): "
                    f"{a['direction']} {a['change_pct']:+.1f}% "
                    f"({a['prev_yi']:.1f} → {a['curr_yi']:.1f} 亿份)"
                )

        history = _load_national_history()
        if len(history) >= 2:
            lines.extend(["", "## 历史趋势"])
            for h_entry in history[-10:]:
                h_broad = h_entry.get("total_broad_shares_yi", 0)
                lines.append(f"- {h_entry['date']}: 宽基 {h_broad:.1f} 亿份")

        content = "\n".join(lines) + "\n"
        out_path = os.path.join(knowledge_dir, f"national-team-{date}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        log.info("国家队知识文件: %s", out_path)
    except Exception as e:
        log.warning("保存国家队知识文件失败: %s", e)


def _load_national_history() -> list[dict]:
    history_path = os.path.join(_CACHE_NATIONAL, "history.json")
    if os.path.isfile(history_path):
        try:
            with open(history_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def national_team_trend(days: int = 30) -> dict:
    """获取国家队ETF份额趋势 (从历史快照)。"""
    history = _load_national_history()
    if not history:
        return {"trend": "无数据", "data_points": 0, "history": []}

    recent = history[-days:] if len(history) >= days else history
    if len(recent) < 2:
        return {"trend": "数据不足", "data_points": len(recent), "history": recent}

    first = recent[0].get("total_broad_shares_yi", 0)
    last = recent[-1].get("total_broad_shares_yi", 0)

    if first > 0:
        total_change = (last - first) / first * 100
    else:
        total_change = 0

    if total_change > 10:
        trend = "大规模建仓"
    elif total_change > 3:
        trend = "持续增持"
    elif total_change > 0:
        trend = "小幅增持"
    elif total_change > -3:
        trend = "小幅减持"
    elif total_change > -10:
        trend = "持续减持"
    else:
        trend = "大规模撤退"

    return {
        "trend": trend,
        "total_change_pct": round(total_change, 2),
        "first_broad_yi": round(first, 2),
        "last_broad_yi": round(last, 2),
        "data_points": len(recent),
        "history": [
            {"date": h["date"], "broad_yi": h.get("total_broad_shares_yi", 0)}
            for h in recent
        ],
    }


def _normalize_date(d: str) -> str:
    """Normalize date string to YYYY-MM-DD format."""
    d = d.strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def national_team_backfill_history(days: int = 90) -> dict:
    """Backfill history.json with weekly snapshots going back `days` days.

    Fetches both SSE and SZSE ETF share data for dates not already in history,
    sampling roughly every 5 trading days. Also patches existing entries that
    are missing SZSE data and normalizes all history dates to YYYY-MM-DD format.
    """
    history = _load_national_history()
    normalized = False
    for h in history:
        old_date = h.get("date", "")
        new_date = _normalize_date(old_date)
        if new_date != old_date:
            h["date"] = new_date
            normalized = True
    existing_dates = {h["date"] for h in history}

    now = datetime.now()
    target_dates = []
    for offset in range(0, days, 5):
        d = now - timedelta(days=offset)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        ds = d.strftime("%Y-%m-%d")
        if ds not in existing_dates:
            target_dates.append((ds, d.strftime("%Y%m%d")))

    target_dates = sorted(set(target_dates), key=lambda x: x[0])

    szse_codes = {e["code"] for e in CORE_ETF_LIST if e["exchange"] == "szse"}
    entries_needing_szse = [
        h for h in history
        if any(
            e["code"] in szse_codes and e.get("shares") is None
            for e in h.get("etf_snapshot", [])
        )
    ]
    need_szse_patch = len(entries_needing_szse) > 0

    if not target_dates and not need_szse_patch:
        return {"backfilled": 0, "total_history": len(history), "message": "历史数据已完整"}

    szse_daily_cache = {}

    def _fetch_szse_for_date(date_yyyymmdd: str) -> pd.DataFrame:
        if date_yyyymmdd in szse_daily_cache:
            return szse_daily_cache[date_yyyymmdd]
        try:
            df = _retry(ak.fund_scale_daily_szse,
                        start_date=date_yyyymmdd,
                        end_date=date_yyyymmdd,
                        symbol="ETF")
            if df is not None and not df.empty:
                szse_daily_cache[date_yyyymmdd] = df
                return df
        except Exception as e:
            log.debug("SZSE daily fetch failed for %s: %s", date_yyyymmdd, e)
        szse_daily_cache[date_yyyymmdd] = pd.DataFrame()
        return pd.DataFrame()

    if need_szse_patch:
        log.info("回填 %d 条历史记录的深交所数据...", len(entries_needing_szse))
        patched = 0
        for h_entry in entries_needing_szse:
            d_str = h_entry["date"].replace("-", "")
            szse_df = _fetch_szse_for_date(d_str)
            if szse_df.empty:
                time.sleep(0.3)
                continue
            szse_share_map = {}
            code_col = share_col = None
            for c in ["基金代码", "代码", "证券代码"]:
                if c in szse_df.columns:
                    code_col = c
                    break
            for c in ["基金份额", "份额", "流通份额"]:
                if c in szse_df.columns:
                    share_col = c
                    break
            if code_col and share_col:
                for _, row in szse_df.iterrows():
                    code = str(row[code_col]).strip()
                    val = pd.to_numeric(row[share_col], errors="coerce")
                    if code in szse_codes and pd.notna(val):
                        szse_share_map[code] = float(val)

            broad_total = 0
            sector_total = 0
            for etf_e in h_entry.get("etf_snapshot", []):
                if etf_e["code"] in szse_share_map and etf_e.get("shares") is None:
                    share = szse_share_map[etf_e["code"]]
                    etf_e["shares"] = share
                    etf_e["shares_yi"] = round(share / 1e8, 2)
                if etf_e.get("shares_yi"):
                    if etf_e.get("type") == "宽基":
                        broad_total += etf_e["shares_yi"]
                    else:
                        sector_total += etf_e["shares_yi"]
            h_entry["total_broad_shares_yi"] = round(broad_total, 2)
            h_entry["total_sector_shares_yi"] = round(sector_total, 2)
            patched += 1
            time.sleep(0.3)
        log.info("深交所数据回填: 修补了 %d 条记录", patched)

    backfilled = 0

    for date_str, date_sse in target_dates:
        try:
            sse_df = ak.fund_etf_scale_sse(date=date_sse)
            if sse_df is None or sse_df.empty or len(sse_df) < 5:
                continue
        except Exception:
            time.sleep(0.3)
            continue

        szse_df = _fetch_szse_for_date(date_sse)

        broad_total = 0
        sector_total = 0
        etf_snap = []
        for etf in CORE_ETF_LIST:
            share = _get_etf_share(etf["code"], sse_df, szse_df)
            shares_yi = round(share / 1e8, 2) if share else None
            etf_snap.append({
                "code": etf["code"], "name": etf["name"],
                "index": etf["index"], "type": etf["type"],
                "shares": share, "shares_yi": shares_yi,
            })
            if shares_yi:
                if etf["type"] == "宽基":
                    broad_total += shares_yi
                else:
                    sector_total += shares_yi

        if broad_total > 0:
            entry = {
                "date": date_str,
                "total_broad_shares_yi": round(broad_total, 2),
                "total_sector_shares_yi": round(sector_total, 2),
                "etf_snapshot": etf_snap,
            }
            history.append(entry)
            backfilled += 1

        time.sleep(0.5)

    history.sort(key=lambda h: h.get("date", ""))
    if len(history) > 365:
        history = history[-365:]

    history_path = os.path.join(_CACHE_NATIONAL, "history.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=str)

    log.info("国家队历史回填: 新增 %d 个数据点, 总计 %d 个", backfilled, len(history))
    return {
        "backfilled": backfilled,
        "total_history": len(history),
        "message": f"回填完成: 新增 {backfilled} 个历史数据点",
    }


def national_team_period_stats() -> dict:
    """Calculate ETF share changes over 1 week, 1 month, and 3 months from history."""
    history = _load_national_history()
    if len(history) < 2:
        return {"periods": [], "per_etf_periods": []}

    today = datetime.now()
    period_defs = [
        {"label": "1周", "key": "1w", "days": 7, "tolerance": 3},
        {"label": "1月", "key": "1m", "days": 30, "tolerance": 5},
        {"label": "3月", "key": "3m", "days": 90, "tolerance": 10},
    ]

    def _find_closest_entry(target_date_str: str, tolerance: int = 3) -> dict | None:
        target = datetime.strptime(target_date_str, "%Y-%m-%d")
        best = None
        best_delta = None
        for h in history:
            try:
                hd = datetime.strptime(h["date"], "%Y-%m-%d")
            except (KeyError, ValueError):
                continue
            delta = abs((hd - target).days)
            if delta <= tolerance and (best_delta is None or delta < best_delta):
                best = h
                best_delta = delta
        return best

    latest = history[-1]
    latest_broad = latest.get("total_broad_shares_yi", 0)
    latest_sector = latest.get("total_sector_shares_yi", 0)

    periods = []
    for pdef in period_defs:
        target_date = (today - timedelta(days=pdef["days"])).strftime("%Y-%m-%d")
        past_entry = _find_closest_entry(target_date, pdef["tolerance"])
        if not past_entry:
            periods.append({
                "key": pdef["key"], "label": pdef["label"],
                "broad_change_pct": None, "sector_change_pct": None,
                "broad_from": None, "broad_to": latest_broad,
                "sector_from": None, "sector_to": latest_sector,
                "ref_date": None,
            })
            continue
        past_broad = past_entry.get("total_broad_shares_yi", 0)
        past_sector = past_entry.get("total_sector_shares_yi", 0)
        broad_pct = ((latest_broad - past_broad) / past_broad * 100) if past_broad > 0 else None
        sector_pct = ((latest_sector - past_sector) / past_sector * 100) if past_sector > 0 else None
        periods.append({
            "key": pdef["key"], "label": pdef["label"],
            "broad_change_pct": round(broad_pct, 2) if broad_pct is not None else None,
            "sector_change_pct": round(sector_pct, 2) if sector_pct is not None else None,
            "broad_from": round(past_broad, 2),
            "broad_to": round(latest_broad, 2),
            "sector_from": round(past_sector, 2),
            "sector_to": round(latest_sector, 2),
            "ref_date": past_entry.get("date"),
        })

    latest_etfs = {e["code"]: e for e in latest.get("etf_snapshot", [])}
    per_etf = []
    for etf_info in CORE_ETF_LIST:
        code = etf_info["code"]
        curr = latest_etfs.get(code)
        if not curr or curr.get("shares_yi") is None:
            continue
        curr_yi = curr["shares_yi"]
        etf_periods = {"code": code, "name": etf_info["name"],
                       "type": etf_info["type"], "current_yi": round(curr_yi, 2)}
        for pdef in period_defs:
            target_date = (today - timedelta(days=pdef["days"])).strftime("%Y-%m-%d")
            past_entry = _find_closest_entry(target_date, pdef["tolerance"])
            pct = None
            past_yi = None
            if past_entry:
                past_etfs = {e["code"]: e for e in past_entry.get("etf_snapshot", [])}
                pe = past_etfs.get(code)
                if pe and pe.get("shares_yi") is not None:
                    past_yi = pe["shares_yi"]
                    if past_yi > 0:
                        pct = round((curr_yi - past_yi) / past_yi * 100, 2)
            etf_periods[pdef["key"]] = pct
            etf_periods[f"{pdef['key']}_from"] = round(past_yi, 2) if past_yi is not None else None
        per_etf.append(etf_periods)

    return {"periods": periods, "per_etf_periods": per_etf}


def fetch_institution_holdings(quarter: str = "") -> pd.DataFrame:
    """获取机构持股一览 (含汇金/社保/保险等)。

    quarter: 格式如 "20261" 表示2026年一季报, "20254" 表示2025年年报。
    不提供则自动推算最近一个季度。
    """
    if not quarter:
        now = datetime.now()
        year = now.year
        q = (now.month - 1) // 3
        if q == 0:
            quarter = f"{year - 1}4"
        else:
            quarter = f"{year}{q}"

    cache_path = os.path.join(_CACHE_NATIONAL, f"inst_hold_{quarter}.json")
    if _cache_fresh(cache_path, max_age_hours=72):
        return pd.read_json(cache_path, encoding="utf-8")

    log.info("机构持股: %s ...", quarter)
    try:
        df = _retry(ak.stock_institute_hold, symbol=quarter)
        if df is not None and not df.empty:
            df.to_json(cache_path, force_ascii=False, orient="records", indent=2)
            log.info("机构持股: 获取 %d 条", len(df))
            return df
    except Exception as e:
        log.warning("机构持股获取失败: %s", e)
    return pd.DataFrame()


def national_team_fund_signals() -> dict:
    """Aggregate fund flow + institution data to supplement ETF share monitoring.

    Returns market-wide main-force flow summary and institution holding highlights.
    """
    result = {"market_flow": None, "institution": None}

    try:
        df_flow = fetch_market_fund_flow(days=10)
        if df_flow is not None and not df_flow.empty:
            net_col = None
            for c in ["主力净流入-净额", "主力净流入", "净流入"]:
                if c in df_flow.columns:
                    net_col = c
                    break
            if net_col:
                df_flow[net_col] = pd.to_numeric(df_flow[net_col], errors="coerce")
                recent = df_flow.tail(5)
                latest_val = recent.iloc[-1][net_col] if len(recent) > 0 else 0
                avg_5d = recent[net_col].mean()
                consecutive = 0
                for val in reversed(recent[net_col].tolist()):
                    if val > 0:
                        consecutive += 1
                    else:
                        break
                consec_out = 0
                for val in reversed(recent[net_col].tolist()):
                    if val < 0:
                        consec_out += 1
                    else:
                        break
                latest_yi = round(latest_val / 1e8, 2) if abs(latest_val) > 1000 else round(latest_val, 2)
                avg_5d_yi = round(avg_5d / 1e8, 2) if abs(avg_5d) > 1000 else round(avg_5d, 2)

                if latest_val > 0 and consecutive >= 3:
                    signal = "主力持续流入"
                elif latest_val > 0:
                    signal = "主力净流入"
                elif latest_val < 0 and consec_out >= 3:
                    signal = "主力持续流出"
                elif latest_val < 0:
                    signal = "主力净流出"
                else:
                    signal = "资金平衡"

                result["market_flow"] = {
                    "latest_net_yi": latest_yi,
                    "avg_5d_net_yi": avg_5d_yi,
                    "consecutive_inflow": consecutive,
                    "consecutive_outflow": consec_out,
                    "signal": signal,
                }
    except Exception as e:
        log.warning("国家队资金信号-大盘资金流获取失败: %s", e)

    try:
        df_inst = fetch_institution_holdings()
        if df_inst is not None and not df_inst.empty:
            total = len(df_inst)
            name_col = None
            for c in ["机构名称", "名称", "持股机构"]:
                if c in df_inst.columns:
                    name_col = c
                    break
            highlights = []
            national_keywords = ["汇金", "社保", "保险", "证金", "梧桐树", "外管局"]
            if name_col:
                for kw in national_keywords:
                    matched = df_inst[df_inst[name_col].str.contains(kw, na=False)]
                    if not matched.empty:
                        highlights.append({"type": kw, "count": len(matched)})
            result["institution"] = {
                "total_records": total,
                "highlights": highlights,
            }
    except Exception as e:
        log.warning("国家队资金信号-机构持股获取失败: %s", e)

    return result


def national_team_institution_detail() -> dict:
    """Fetch institution holding details from quarterly reports.

    Queries 社保/QFII/保险 holding data via stock_report_fund_hold,
    providing concrete evidence of national-team-adjacent institutional activity.
    Returns top movers (biggest increases) for each category.
    """
    result = {"quarter": "", "categories": []}
    now = datetime.now()
    quarter_dates = []
    for y in range(now.year, now.year - 2, -1):
        for q_date in ["1231", "0930", "0630", "0331"]:
            quarter_dates.append(f"{y}{q_date}")
    quarter_dates = [d for d in quarter_dates if d <= now.strftime("%Y%m%d")]

    categories = [
        {"symbol": "社保持仓", "label": "社保基金", "icon": "shield"},
        {"symbol": "QFII持仓", "label": "QFII", "icon": "globe"},
        {"symbol": "保险持仓", "label": "保险资金", "icon": "umbrella"},
    ]

    cache_path = os.path.join(_CACHE_NATIONAL, "inst_detail.json")
    if _cache_fresh(cache_path, max_age_hours=24):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    found_quarter = ""
    for cat in categories:
        cat_data = None
        for qd in quarter_dates:
            try:
                df = _retry(ak.stock_report_fund_hold, symbol=cat["symbol"], date=qd)
                if df is not None and not df.empty and len(df) >= 10:
                    cat_data = df
                    if not found_quarter:
                        y, md = qd[:4], qd[4:]
                        q_map = {"0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "Q4"}
                        found_quarter = f"{y} {q_map.get(md, md)}"
                    break
            except Exception:
                continue

        if cat_data is None:
            continue

        code_col = "股票代码" if "股票代码" in cat_data.columns else None
        name_col = "股票简称" if "股票简称" in cat_data.columns else None
        change_col = "持股变化" if "持股变化" in cat_data.columns else None
        pct_col = "持股变动比例" if "持股变动比例" in cat_data.columns else None
        count_col = "持有基金家数" if "持有基金家数" in cat_data.columns else None
        value_col = "持股市值" if "持股市值" in cat_data.columns else None

        top_increase = []
        top_new = []
        if change_col:
            increased = cat_data[cat_data[change_col] == "增仓"]
            if pct_col and not increased.empty:
                increased = increased.copy()
                increased[pct_col] = pd.to_numeric(increased[pct_col], errors="coerce")
                top5 = increased.nlargest(5, pct_col)
                for _, row in top5.iterrows():
                    entry = {
                        "code": str(row.get(code_col, "")),
                        "name": str(row.get(name_col, "")),
                        "change": "增仓",
                        "change_pct": round(float(row[pct_col]), 2) if pd.notna(row[pct_col]) else None,
                    }
                    if count_col and pd.notna(row.get(count_col)):
                        entry["fund_count"] = int(row[count_col])
                    if value_col and pd.notna(row.get(value_col)):
                        entry["market_value_yi"] = round(float(row[value_col]) / 1e8, 2)
                    top_increase.append(entry)

            new_entries = cat_data[cat_data[change_col] == "新进"]
            if not new_entries.empty and value_col:
                new_entries = new_entries.copy()
                new_entries[value_col] = pd.to_numeric(new_entries[value_col], errors="coerce")
                top3 = new_entries.nlargest(3, value_col)
                for _, row in top3.iterrows():
                    entry = {
                        "code": str(row.get(code_col, "")),
                        "name": str(row.get(name_col, "")),
                        "change": "新进",
                    }
                    if count_col and pd.notna(row.get(count_col)):
                        entry["fund_count"] = int(row[count_col])
                    if value_col and pd.notna(row.get(value_col)):
                        entry["market_value_yi"] = round(float(row[value_col]) / 1e8, 2)
                    top_new.append(entry)

        top_decrease = []
        if change_col:
            decreased = cat_data[cat_data[change_col] == "减仓"]
            if pct_col and not decreased.empty:
                decreased = decreased.copy()
                decreased[pct_col] = pd.to_numeric(decreased[pct_col], errors="coerce")
                top5_dec = decreased.nsmallest(5, pct_col)
                for _, row in top5_dec.iterrows():
                    entry = {
                        "code": str(row.get(code_col, "")),
                        "name": str(row.get(name_col, "")),
                        "change": "减仓",
                        "change_pct": round(float(row[pct_col]), 2) if pd.notna(row[pct_col]) else None,
                    }
                    if count_col and pd.notna(row.get(count_col)):
                        entry["fund_count"] = int(row[count_col])
                    if value_col and pd.notna(row.get(value_col)):
                        entry["market_value_yi"] = round(float(row[value_col]) / 1e8, 2)
                    top_decrease.append(entry)

        summary = {
            "total": len(cat_data),
            "increased": int((cat_data[change_col] == "增仓").sum()) if change_col else 0,
            "decreased": int((cat_data[change_col] == "减仓").sum()) if change_col else 0,
            "new": int((cat_data[change_col] == "新进").sum()) if change_col else 0,
        }

        result["categories"].append({
            "symbol": cat["symbol"],
            "label": cat["label"],
            "icon": cat["icon"],
            "summary": summary,
            "top_increase": top_increase,
            "top_decrease": top_decrease,
            "top_new": top_new,
        })

    result["quarter"] = found_quarter

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

    return result


# ── Composite: Fetch All ────────────────────────────────────

def fetch_all_china_data() -> dict:
    """一次性获取所有中国特色数据，返回汇总字典。"""
    log.info("=" * 50)
    log.info("开始获取中国A股特色数据...")
    results = {}
    errors = []

    fetchers = [
        ("northbound", lambda: {"rows": len(fetch_northbound()),
                                "signals": northbound_momentum()}),
        ("sector_flow", lambda: {"rows": len(fetch_sector_flow())}),
        ("lhb", lambda: {"rows": len(fetch_lhb_institutional())}),
        ("margin", lambda: {"rows": len(fetch_margin_data()),
                            "signals": margin_sentiment()}),
        ("temperature", lambda: market_temperature()),
        ("market_flow", lambda: {"rows": len(fetch_market_fund_flow())}),
        ("national_team", lambda: national_team_monitor()),
    ]

    for name, fn in fetchers:
        try:
            results[name] = fn()
            log.info("✓ %s 完成", name)
        except Exception as e:
            log.error("✗ %s 失败: %s", name, e)
            errors.append(f"{name}: {e}")
            results[name] = {"error": str(e)}

    results["errors"] = errors
    results["fetched_at"] = datetime.now().isoformat()
    results["success_count"] = len(fetchers) - len(errors)
    results["total_count"] = len(fetchers)

    log.info("中国特色数据获取完成: %d/%d 成功", results["success_count"], results["total_count"])
    return results


# ── CLI Test ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("\n" + "=" * 60)
        print("中国A股特色数据 — 完整测试")
        print("=" * 60)

        result = fetch_all_china_data()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        print("\n--- 北向资金动量 ---")
        nb = northbound_momentum()
        print(json.dumps(nb, ensure_ascii=False, indent=2))

        print("\n--- 市场温度 ---")
        temp = market_temperature()
        print(json.dumps(temp, ensure_ascii=False, indent=2))

        print("\n--- 融资融券情绪 ---")
        mg = margin_sentiment()
        print(json.dumps(mg, ensure_ascii=False, indent=2))

        print("\n--- 热门板块 TOP 5 ---")
        hot = get_hot_sectors(5)
        for s in hot:
            print(f"  {s}")

        print("\n--- 国家队ETF监控 ---")
        nt = national_team_monitor()
        print(f"  宽基ETF总份额: {nt['total_broad_shares_yi']:.1f} 亿份")
        print(f"  行业ETF总份额: {nt['total_sector_shares_yi']:.1f} 亿份")
        print(f"  信号: {nt['signals']['broad_total_change']}")
        if nt["signals"]["anomalies"]:
            print("  异常变动:")
            for a in nt["signals"]["anomalies"]:
                print(f"    {a['name']} ({a['code']}): {a['direction']} {a['change_pct']:.1f}% "
                      f"({a['prev_yi']:.1f} → {a['curr_yi']:.1f} 亿份)")
        for etf in nt["etf_snapshot"]:
            if etf.get("shares_yi"):
                chg = f" ({etf['change_pct']:+.1f}%)" if etf.get("change_pct") is not None else ""
                print(f"    {etf['name']:12s} {etf['code']}: {etf['shares_yi']:>8.1f} 亿份{chg}")

        print("\n--- 国家队趋势 ---")
        trend = national_team_trend()
        print(json.dumps(trend, ensure_ascii=False, indent=2))

        if len(sys.argv) > 2:
            symbol = sys.argv[2]
            print(f"\n--- 个股资金流向 {symbol} ---")
            ff = stock_fund_flow_signals(symbol)
            print(json.dumps(ff, ensure_ascii=False, indent=2))

            print(f"\n--- 龙虎榜活动 {symbol} ---")
            lhb = stock_lhb_activity(symbol)
            print(json.dumps(lhb, ensure_ascii=False, indent=2))
    else:
        print("用法: python china_market_data.py --test [symbol]")
        print("示例: python china_market_data.py --test 600519")
