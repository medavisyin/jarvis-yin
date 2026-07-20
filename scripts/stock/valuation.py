"""
估值体系 — 同业比较、历史分位、简化 DCF、综合评级.

Phase 2 (ch9-enhancement-roadmap): 从打分制升级到定价制.
"""
import json
import logging
import os
import random
import threading
import time
from datetime import datetime

import akshare as ak
import numpy as np
import pandas as pd
import requests

from config import STOCK_CACHE_DIR, STOCK_DATA_DIR

log = logging.getLogger(__name__)

_CACHE_ROOT = os.path.join(STOCK_CACHE_DIR, ".valuation")
_CACHE_HISTORY = os.path.join(_CACHE_ROOT, "history")
_CACHE_SPOT = os.path.join(_CACHE_ROOT, "market_spot.csv")
_CACHE_INDUSTRY = os.path.join(_CACHE_ROOT, "industry_peers")
_CACHE_INDUSTRY_MAP = os.path.join(_CACHE_ROOT, "industry_map.json")
_CACHE_BOARD_NAMES = os.path.join(_CACHE_ROOT, "industry_board_names.json")

MARKET_SPOT_TTL_HOURS = 48
MARKET_SPOT_STALE_MAX_HOURS = 168


def _request_proxies():
    try:
        from network_policy import get_proxies
        return get_proxies()
    except Exception:
        return None

for _d in [_CACHE_ROOT, _CACHE_HISTORY, _CACHE_INDUSTRY]:
    os.makedirs(_d, exist_ok=True)

_RETRY_DELAY = 1.5
_MAX_RETRIES = 3
_DEFAULT_WACC = 0.10
_DEFAULT_TERMINAL_GROWTH = 0.03


def _safe_float(val, default=None):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        v = float(val)
        return default if pd.isna(v) else v
    except (ValueError, TypeError):
        return default


def _cache_fresh(path: str, max_age_hours: float = 12) -> bool:
    if not os.path.isfile(path):
        return False
    return (time.time() - os.path.getmtime(path)) < max_age_hours * 3600


def _retry(fn, *args, retries=_MAX_RETRIES, delay=_RETRY_DELAY, **kwargs):
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            log.warning("尝试 %d/%d 失败: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt) + random.uniform(0, 0.5))
    raise last_err


def _parse_cn_number(val):
    if val is None or val is False:
        return None
    s = str(val).strip().rstrip("%")
    if not s or s.lower() == "false":
        return None
    multiplier = 1
    if s.endswith("亿"):
        multiplier = 100_000_000
        s = s[:-1]
    elif s.endswith("万"):
        multiplier = 10_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def _percentile_rank(value: float, series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean > 0]
    if not len(clean) or value is None or value <= 0:
        return None
    return float((clean < value).sum() / len(clean) * 100)


def _load_profile(symbol: str) -> dict:
    path = os.path.join(STOCK_DATA_DIR, symbol, "profile.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        from fetch_market_data import fetch_company_profile
        return fetch_company_profile(symbol)
    except Exception as e:
        log.warning("获取 %s 公司信息失败: %s", symbol, e)
        return {}


def _load_realtime(symbol: str) -> dict:
    path = os.path.join(STOCK_DATA_DIR, symbol, "realtime.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        from fetch_market_data import fetch_realtime_quote
        return fetch_realtime_quote(symbol)
    except Exception as e:
        log.warning("获取 %s 实时行情失败: %s", symbol, e)
        return {}


def fetch_valuation_history(symbol: str, max_age_hours: float = 24) -> pd.DataFrame:
    """加载个股历史估值序列 (PE/PB 等), 按 symbol 磁盘缓存."""
    cache_path = os.path.join(_CACHE_HISTORY, f"{symbol}.csv")
    if _cache_fresh(cache_path, max_age_hours=max_age_hours):
        df = pd.read_csv(cache_path, parse_dates=["数据日期"], encoding="utf-8-sig")
        if not df.empty:
            log.info("估值历史 %s: 缓存 %d 行", symbol, len(df))
            return df

    log.info("估值历史 %s: 从东方财富获取...", symbol)
    holder = [None, None]

    def _fetch():
        try:
            holder[0] = ak.stock_value_em(symbol=symbol)
        except Exception as e:
            holder[1] = e

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=45)
    if t.is_alive() or holder[1] or holder[0] is None:
        if os.path.isfile(cache_path):
            return pd.read_csv(cache_path, parse_dates=["数据日期"], encoding="utf-8-sig")
        raise TimeoutError(holder[1] or "stock_value_em 超时")

    df = holder[0]
    if df is None or df.empty:
        if os.path.isfile(cache_path):
            return pd.read_csv(cache_path, parse_dates=["数据日期"], encoding="utf-8-sig")
        return pd.DataFrame()

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    log.info("估值历史 %s: 已缓存 %d 行", symbol, len(df))
    return df


def _current_pe_pb(symbol: str, pe: float | None = None, pb: float | None = None) -> tuple[float | None, float | None]:
    """从实时行情或估值历史末行解析当前 PE/PB."""
    if pe is None or pb is None:
        rt = _load_realtime(symbol)
        if pe is None:
            pe = _safe_float(rt.get("市盈率-动态"))
        if pb is None:
            pb = _safe_float(rt.get("市净率"))

    if pe is None or pb is None:
        try:
            hist = fetch_valuation_history(symbol)
            if not hist.empty:
                last = hist.iloc[-1]
                if pe is None and "PE(TTM)" in hist.columns:
                    pe = _safe_float(last["PE(TTM)"])
                if pb is None and "市净率" in hist.columns:
                    pb = _safe_float(last["市净率"])
        except Exception as e:
            log.debug("估值历史 PE/PB 回退失败: %s", e)

    return pe, pb


def historical_percentile(symbol: str, pe: float | None = None, pb: float | None = None) -> dict:
    """当前 PE/PB 在自身历史分布中的百分位."""
    pe, pb = _current_pe_pb(symbol, pe=pe, pb=pb)

    hist = fetch_valuation_history(symbol)
    out = {
        "pe_current": pe,
        "pb_current": pb,
        "history_days": len(hist),
        "pe_percentile": None,
        "pb_percentile": None,
        "pe_zone": "未知",
        "pb_zone": "未知",
    }
    if hist.empty:
        out["error"] = "无历史估值数据"
        return out

    pe_col = "PE(TTM)" if "PE(TTM)" in hist.columns else None
    pb_col = "市净率" if "市净率" in hist.columns else None

    if pe_col and pe:
        pe_hist = hist[pe_col]
        out["pe_percentile"] = round(_percentile_rank(pe, pe_hist), 1)
        if out["pe_percentile"] is not None:
            if out["pe_percentile"] <= 20:
                out["pe_zone"] = "低估区域"
            elif out["pe_percentile"] >= 80:
                out["pe_zone"] = "高估区域"
            else:
                out["pe_zone"] = "中性"

    if pb_col and pb:
        pb_hist = hist[pb_col]
        out["pb_percentile"] = round(_percentile_rank(pb, pb_hist), 1)
        if out["pb_percentile"] is not None:
            if out["pb_percentile"] <= 20:
                out["pb_zone"] = "低估区域"
            elif out["pb_percentile"] >= 80:
                out["pb_zone"] = "高估区域"
            else:
                out["pb_zone"] = "中性"

    return out


def _fetch_market_spot_sina() -> pd.DataFrame:
    """新浪分页全市场行情 (东财不可用时的备用, 含 PE/PB)."""
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    all_rows = []
    page = 1
    while page <= 80:
        params = {
            "page": str(page), "num": "80",
            "sort": "changepercent", "asc": "0",
            "node": "hs_a", "symbol": "",
        }
        items = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    url, params=params, headers=headers, timeout=15, proxies=_request_proxies(),
                )
                if resp.status_code == 200:
                    items = resp.json()
                    break
                time.sleep(1.5 * (attempt + 1))
            except Exception as e:
                log.warning("新浪行情页 %d 失败: %s", page, e)
                time.sleep(1.5)
        if not items:
            break
        for item in items:
            code = str(item.get("code", "")).zfill(6)
            per = item.get("per")
            pb = item.get("pb")
            all_rows.append({
                "代码": code,
                "名称": str(item.get("name", "")),
                "最新价": item.get("trade"),
                "涨跌幅": item.get("changepercent"),
                "市盈率-动态": per if per not in (None, "", "-") else None,
                "市净率": pb if pb not in (None, "", "-") else None,
            })
        if len(items) < 80:
            break
        page += 1
        time.sleep(0.25)

    if not all_rows:
        raise ValueError("新浪分页未返回数据")
    df = pd.DataFrame(all_rows)
    log.info("新浪全市场快照: %d 只", len(df))
    return df


def _load_market_spot_cached_only() -> pd.DataFrame:
    """估值/UI 只读本地快照, 不触发网络拉取."""
    if not os.path.isfile(_CACHE_SPOT):
        return pd.DataFrame()
    age_h = (time.time() - os.path.getmtime(_CACHE_SPOT)) / 3600
    if age_h > MARKET_SPOT_STALE_MAX_HOURS:
        log.warning("全市场快照已超过 %dh, 请运行「数据预热」", int(MARKET_SPOT_STALE_MAX_HOURS))
    return pd.read_csv(_CACHE_SPOT, encoding="utf-8-sig")


def refresh_market_spot(force: bool = False) -> dict:
    """拉取全市场 PE/PB 快照 — 仅由数据预热任务调用."""
    from network_policy import ensure_network

    if not ensure_network(force=True):
        raise RuntimeError("网络不可用 (直连与代理均失败)")

    if not force and _cache_fresh(_CACHE_SPOT, max_age_hours=MARKET_SPOT_TTL_HOURS):
        df = _load_market_spot_cached_only()
        src = "cached"
        if "_spot_source" in df.columns and len(df):
            src = str(df["_spot_source"].iloc[0])
        return {"rows": len(df), "source": src, "skipped": True}

    df = None
    source = "eastmoney"

    log.info("全市场估值快照: 尝试东方财富...")
    try:
        df = _retry(ak.stock_zh_a_spot_em, retries=3)
    except Exception as e:
        log.warning("东财全市场快照失败: %s", e)

    if df is None or df.empty:
        log.info("全市场估值快照: 尝试新浪分页...")
        try:
            df = _fetch_market_spot_sina()
            source = "sina"
        except Exception as e2:
            log.warning("新浪全市场快照失败: %s", e2)

    if df is not None and not df.empty:
        df["_spot_source"] = source
        df.to_csv(_CACHE_SPOT, index=False, encoding="utf-8-sig")
        log.info("全市场估值快照已缓存 %d 只 (source=%s)", len(df), source)
        return {"rows": len(df), "source": source, "skipped": False}

    if os.path.isfile(_CACHE_SPOT):
        df = _load_market_spot_cached_only()
        return {"rows": len(df), "source": "stale_cache", "skipped": False}
    raise RuntimeError("全市场快照拉取失败且无本地缓存")


def rebuild_industry_map() -> int:
    """从本地 profile.json 重建行业映射 (预热任务用)."""
    mapping: dict[str, list[str]] = {}
    if not os.path.isdir(STOCK_DATA_DIR):
        return 0

    for entry in os.scandir(STOCK_DATA_DIR):
        if not entry.is_dir():
            continue
        prof_path = os.path.join(entry.path, "profile.json")
        if not os.path.isfile(prof_path):
            continue
        try:
            with open(prof_path, encoding="utf-8") as f:
                prof = json.load(f)
            for key in ("行业", "证监会行业"):
                ind = (prof.get(key) or "").strip()
                if ind:
                    mapping.setdefault(ind, [])
                    if entry.name not in mapping[ind]:
                        mapping[ind].append(entry.name)
        except Exception:
            continue

    with open(_CACHE_INDUSTRY_MAP, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    log.info("行业映射已重建: %d 个行业", len(mapping))
    return len(mapping)


def refresh_watchlist_industry_peers() -> dict:
    """预热时刷新自选股涉及行业的成分股缓存 (东财→本地 profile 降级)."""
    from watchlist import list_stocks

    industries: set[str] = set()
    for s in list_stocks():
        sym = s.get("symbol", "")
        if not sym:
            continue
        prof = _load_profile(sym)
        for key in ("行业", "证监会行业"):
            ind = (prof.get(key) or s.get("sector") or "").strip()
            if ind:
                industries.add(ind)

    refreshed = 0
    for ind in industries:
        try:
            codes = _industry_peer_codes(ind, cached_only=False)
            if codes:
                refreshed += 1
        except Exception as e:
            log.warning("行业成分预热 %s 失败: %s", ind, e)

    return {"industries": len(industries), "refreshed": refreshed}


def _load_industry_map_from_profiles() -> dict[str, list[str]]:
    """从本地 profile.json 汇总 行业→代码列表 (不依赖东财)."""
    if _cache_fresh(_CACHE_INDUSTRY_MAP, max_age_hours=24):
        try:
            with open(_CACHE_INDUSTRY_MAP, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    mapping: dict[str, list[str]] = {}
    if not os.path.isdir(STOCK_DATA_DIR):
        return mapping

    for entry in os.scandir(STOCK_DATA_DIR):
        if not entry.is_dir():
            continue
        prof_path = os.path.join(entry.path, "profile.json")
        if not os.path.isfile(prof_path):
            continue
        try:
            with open(prof_path, encoding="utf-8") as f:
                prof = json.load(f)
            for key in ("行业", "证监会行业"):
                ind = (prof.get(key) or "").strip()
                if ind:
                    mapping.setdefault(ind, [])
                    if entry.name not in mapping[ind]:
                        mapping[ind].append(entry.name)
        except Exception:
            continue

    try:
        with open(_CACHE_INDUSTRY_MAP, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return mapping


def _resolve_industry_board_name(industry: str) -> str:
    """将 profile 行业名映射到东财板块名 (模糊匹配)."""
    if not industry:
        return industry
    if _cache_fresh(_CACHE_BOARD_NAMES, max_age_hours=168):
        try:
            names = json.load(open(_CACHE_BOARD_NAMES, encoding="utf-8"))
        except Exception:
            names = []
    else:
        names = []
        try:
            df = _retry(ak.stock_board_industry_name_em, retries=2)
            col = "板块名称" if "板块名称" in df.columns else df.columns[1]
            names = [str(x) for x in df[col].tolist()]
            with open(_CACHE_BOARD_NAMES, "w", encoding="utf-8") as f:
                json.dump(names, f, ensure_ascii=False)
        except Exception as e:
            log.debug("行业板块列表获取失败: %s", e)

    if industry in names:
        return industry
    for n in names:
        if industry in n or n in industry:
            return n
    return industry


def _industry_peer_codes(industry: str, cached_only: bool = False) -> list[str]:
    if not industry:
        return []

    cache_path = os.path.join(_CACHE_INDUSTRY, f"{industry}.json")
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f).get("codes", [])
                if cached:
                    return cached
        except Exception:
            pass

    codes: list[str] = []
    board_name = industry
    if not cached_only:
        board_name = _resolve_industry_board_name(industry)
        try:
            df = _retry(ak.stock_board_industry_cons_em, symbol=board_name, retries=3)
            code_col = "代码" if "代码" in df.columns else df.columns[1]
            codes = [str(c).zfill(6) for c in df[code_col].astype(str)]
            log.info("行业成分 %s (%s): %d 只", industry, board_name, len(codes))
        except Exception as e:
            log.warning("东财行业成分 %s 失败: %s", board_name, e)

    if len(codes) < 3:
        profile_map = _load_industry_map_from_profiles()
        for key, syms in profile_map.items():
            if key == industry or industry in key or key in industry:
                for s in syms:
                    if s not in codes:
                        codes.append(s)

    if codes:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "industry": industry,
                "board_name": board_name,
                "codes": codes,
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

    return codes


def _apply_peer_stats(peers: pd.DataFrame, pe_col: str, pb_col: str,
                      pe: float | None, pb: float | None, out: dict) -> dict:
    if peers.empty:
        return out

    peer_pe = pd.to_numeric(peers[pe_col], errors="coerce")
    peer_pe = peer_pe[(peer_pe > 0) & (peer_pe < 500)]
    peer_pb = pd.to_numeric(peers[pb_col], errors="coerce")
    peer_pb = peer_pb[(peer_pb > 0) & (peer_pb < 50)]

    out["peer_count"] = len(peers)
    out["peer_with_pe"] = int(len(peer_pe))
    out["peer_with_pb"] = int(len(peer_pb))

    if len(peer_pe) >= 3:
        out["pe_median"] = round(float(peer_pe.median()), 2)
        out["pe_p25"] = round(float(peer_pe.quantile(0.25)), 2)
        out["pe_p75"] = round(float(peer_pe.quantile(0.75)), 2)
        if pe and pe > 0:
            out["pe_percentile_in_industry"] = round(_percentile_rank(pe, peer_pe), 1)
            if out["pe_median"]:
                out["pe_premium_pct"] = round((pe - out["pe_median"]) / out["pe_median"] * 100, 1)

    if len(peer_pb) >= 3:
        out["pb_median"] = round(float(peer_pb.median()), 2)
        if pb and pb > 0:
            out["pb_percentile_in_industry"] = round(_percentile_rank(pb, peer_pb), 1)
            if out["pb_median"]:
                out["pb_premium_pct"] = round((pb - out["pb_median"]) / out["pb_median"] * 100, 1)

    return out


def peer_comparison(symbol: str) -> dict:
    """同业 PE/PB 比较与溢价率."""
    profile = _load_profile(symbol)
    industry = profile.get("行业", "") or profile.get("证监会行业", "")
    pe, pb = _current_pe_pb(symbol)

    out = {
        "symbol": symbol,
        "industry": industry or "未知",
        "pe": pe,
        "pb": pb,
        "peer_count": 0,
        "pe_median": None,
        "pb_median": None,
        "pe_p25": None,
        "pe_p75": None,
        "pe_percentile_in_industry": None,
        "pb_percentile_in_industry": None,
        "pe_premium_pct": None,
        "pb_premium_pct": None,
        "data_source": "industry",
        "spot_source": None,
    }

    spot = _load_market_spot_cached_only()
    if spot.empty:
        out["error"] = "全市场行情缓存为空, 请在非高峰时段运行「数据预热」"
        out["data_source"] = "unavailable"
        return out

    cache_age_h = (
        (time.time() - os.path.getmtime(_CACHE_SPOT)) / 3600
        if os.path.isfile(_CACHE_SPOT) else None
    )
    if cache_age_h is not None and cache_age_h > MARKET_SPOT_TTL_HOURS:
        out["cache_stale_hours"] = round(cache_age_h, 1)
        out["cache_note"] = "快照已超过 48h, 建议运行数据预热"

    out["spot_source"] = (
        str(spot["_spot_source"].iloc[0])
        if "_spot_source" in spot.columns and len(spot) else "cached"
    )
    code_col = "代码"
    spot = spot.copy()
    spot[code_col] = spot[code_col].astype(str).str.zfill(6)
    pe_col = "市盈率-动态"
    pb_col = "市净率"

    peer_codes = _industry_peer_codes(industry, cached_only=True) if industry else []
    peers = pd.DataFrame()

    if peer_codes:
        peers = spot[spot[code_col].isin(peer_codes)].copy()
        out["data_source"] = "industry"
        out["industry_peer_codes"] = len(peer_codes)

    if len(peers) < 3:
        out["data_source"] = "market_wide"
        out["note"] = (
            f"行业 '{industry}' 有效样本不足 ({len(peers)} 只), "
            "以下为全 A 股市场 PE/PB 参考"
        )
        peers = spot.copy()

    out = _apply_peer_stats(peers, pe_col, pb_col, pe, pb, out)

    if out.get("pe_median") is None and out.get("peer_with_pe", 0) < 3:
        out["warning"] = "同业 PE 有效样本不足, 可刷新自选股/公司信息后重试"

    return out


def _fetch_fcf_history(symbol: str, years: int = 3) -> list[dict]:
    """近 N 年经营现金流与近似 FCF (经营现金流 - 资本开支)."""
    try:
        df = _retry(ak.stock_financial_cash_ths, symbol=symbol, indicator="按年度")
    except Exception as e:
        log.warning("现金流 %s 获取失败: %s", symbol, e)
        return []

    if df is None or df.empty:
        return []

    ocf_col = "*经营活动产生的现金流量净额"
    capex_col = "购建固定资产、无形资产和其他长期资产支付的现金"
    records = []
    for _, row in df.head(years).iterrows():
        ocf = _parse_cn_number(row.get(ocf_col))
        capex = _parse_cn_number(row.get(capex_col)) if capex_col in df.columns else None
        if ocf is None:
            continue
        capex = abs(capex) if capex else 0
        records.append({
            "report_date": str(row.get("报告期", "")),
            "operating_cf": ocf,
            "capex": capex,
            "fcf": ocf - capex,
        })
    return records


def _revenue_cagr(symbol: str) -> float | None:
    try:
        from fundamental_analysis import load_fundamentals, fetch_fundamentals
        data = load_fundamentals(symbol) or fetch_fundamentals(symbol)
        yoy = data.get("financials", {}).get("revenue_yoy")
        if yoy is not None:
            return min(max(yoy / 100, -0.2), 0.15)
    except Exception:
        pass
    return 0.08


def _dcf_intrinsic(fcf: float, growth: float, wacc: float = _DEFAULT_WACC,
                   terminal_growth: float = _DEFAULT_TERMINAL_GROWTH, years: int = 5) -> float | None:
    if fcf <= 0 or wacc <= terminal_growth:
        return None
    pv = 0.0
    cf = fcf
    for t in range(1, years + 1):
        cf *= (1 + growth)
        pv += cf / ((1 + wacc) ** t)
    terminal = cf * (1 + terminal_growth) / (wacc - terminal_growth)
    pv += terminal / ((1 + wacc) ** years)
    return pv


def simplified_dcf(symbol: str, price: float | None = None, wacc: float = _DEFAULT_WACC) -> dict:
    """三情景简化 DCF (乐观/中性/悲观)."""
    rt = _load_realtime(symbol)
    if price is None:
        price = _safe_float(rt.get("最新价"))

    fcf_hist = _fetch_fcf_history(symbol, years=3)
    base_growth = _revenue_cagr(symbol)

    shares = None
    hist = fetch_valuation_history(symbol)
    if not hist.empty and "总股本" in hist.columns:
        shares = _safe_float(hist.iloc[-1]["总股本"])
    if not shares:
        prof = _load_profile(symbol)
        shares = _safe_float(prof.get("总股本"))

    out = {
        "price": price,
        "wacc": wacc,
        "fcf_history": fcf_hist,
        "shares": shares,
        "scenarios": {},
        "data_available": bool(fcf_hist),
    }

    if not fcf_hist:
        out["error"] = "无现金流数据, 无法计算 DCF"
        return out

    avg_fcf = float(np.mean([r["fcf"] for r in fcf_hist if r["fcf"] is not None]))
    if avg_fcf <= 0:
        out["error"] = "近3年平均 FCF 为负, DCF 不适用"
        return out

    scenario_defs = {
        "悲观": max(base_growth - 0.04, 0.02),
        "中性": base_growth,
        "乐观": min(base_growth + 0.04, 0.15),
    }

    for name, growth in scenario_defs.items():
        enterprise_value = _dcf_intrinsic(avg_fcf, growth, wacc=wacc)
        intrinsic_per_share = None
        margin_of_safety = None
        premium_pct = None
        if enterprise_value and shares and shares > 0:
            intrinsic_per_share = round(enterprise_value / shares, 2)
            if price and intrinsic_per_share > 0:
                margin_of_safety = round((intrinsic_per_share - price) / intrinsic_per_share * 100, 1)
                premium_pct = round((price - intrinsic_per_share) / intrinsic_per_share * 100, 1)
        out["scenarios"][name] = {
            "growth_rate": round(growth * 100, 1),
            "avg_fcf": round(avg_fcf / 100_000_000, 2),
            "enterprise_value_yi": round(enterprise_value / 100_000_000, 2) if enterprise_value else None,
            "intrinsic_value_per_share": intrinsic_per_share,
            "margin_of_safety_pct": margin_of_safety,
            "premium_pct": premium_pct,
        }

    return out


def composite_rating(historical: dict, peer: dict, dcf: dict) -> dict:
    """三项估值信号合并为综合评级."""
    checks = []

    pe_ind = peer.get("pe_percentile_in_industry")
    if pe_ind is not None:
        ok = pe_ind <= 25
        checks.append({
            "name": "同业PE分位",
            "value": f"{pe_ind}%",
            "pass": ok,
            "meaning": "相对同行便宜" if ok else "相对同行偏贵",
        })

    pe_hist = historical.get("pe_percentile")
    if pe_hist is not None:
        ok = pe_hist <= 20
        checks.append({
            "name": "历史PE分位",
            "value": f"{pe_hist}%",
            "pass": ok,
            "meaning": "相对自身历史便宜" if ok else "相对自身历史偏贵",
        })

    mos = None
    if dcf.get("scenarios", {}).get("中性", {}).get("margin_of_safety_pct") is not None:
        mos = dcf["scenarios"]["中性"]["margin_of_safety_pct"]
        ok = mos >= 30
        checks.append({
            "name": "DCF安全边际(中性)",
            "value": f"{mos}%",
            "pass": ok,
            "meaning": "估值缓冲充足" if ok else "估值缓冲不足",
        })

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    if total == 0:
        verdict = "数据不足"
    elif passed >= 2:
        verdict = "估值合理"
    elif passed == 1:
        verdict = "估值中性"
    else:
        verdict = "估值偏高"

    return {
        "checks": checks,
        "passed": passed,
        "total": total,
        "verdict": verdict,
    }


def compute_valuation(symbol: str) -> dict:
    """运行完整估值分析, 返回结构化结果."""
    profile = _load_profile(symbol)
    rt = _load_realtime(symbol)
    pe, pb = _current_pe_pb(symbol)
    price = _safe_float(rt.get("最新价"))
    if not price:
        try:
            hist = fetch_valuation_history(symbol)
            if not hist.empty and "当日收盘价" in hist.columns:
                price = _safe_float(hist.iloc[-1]["当日收盘价"])
        except Exception:
            pass

    historical = historical_percentile(symbol, pe=pe, pb=pb)
    peer = peer_comparison(symbol)
    dcf = simplified_dcf(symbol, price=price)
    rating = composite_rating(historical, peer, dcf)

    return {
        "symbol": symbol,
        "name": profile.get("股票简称", profile.get("name", "")),
        "industry": profile.get("行业", ""),
        "price": price,
        "pe": pe,
        "pb": pb,
        "historical": historical,
        "peer": peer,
        "dcf": dcf,
        "rating": rating,
        "computed_at": datetime.now().isoformat(),
    }


def generate_valuation_report(symbol: str) -> str:
    """生成中文估值分析 Markdown 报告."""
    data = compute_valuation(symbol)
    name = data.get("name") or symbol
    hist = data["historical"]
    peer = data["peer"]
    dcf = data["dcf"]
    rating = data["rating"]

    lines = [
        f"# {name} ({symbol}) 估值分析报告",
        f"> 综合评级: **{rating['verdict']}** ({rating['passed']}/{rating['total']} 项达标)",
        "",
        "## 估值仪表盘",
        "",
        "| 指标 | 数值 | 状态 |",
        "|------|------|------|",
    ]

    for chk in rating["checks"]:
        status = "✅" if chk["pass"] else "—"
        lines.append(f"| {chk['name']} | {chk['value']} | {status} {chk['meaning']} |")

    lines.extend([
        "",
        "## 历史估值分位",
        "",
        f"- 历史样本: {hist.get('history_days', 0)} 个交易日",
        f"- 当前 PE: {hist.get('pe_current', 'N/A')} → 历史分位 **{hist.get('pe_percentile', 'N/A')}%** ({hist.get('pe_zone', '')})",
        f"- 当前 PB: {hist.get('pb_current', 'N/A')} → 历史分位 **{hist.get('pb_percentile', 'N/A')}%** ({hist.get('pb_zone', '')})",
        "",
        "## 同业比较",
        "",
        f"- 行业: {peer.get('industry', 'N/A')} (样本 {peer.get('peer_count', 0)} 只, "
        f"有效PE {peer.get('peer_with_pe', '?')} 只, 来源: {peer.get('data_source', '')}, "
        f"行情: {peer.get('spot_source', 'cached')})",
    ])
    if peer.get("note"):
        lines.append(f"- 说明: {peer['note']}")
    if peer.get("warning"):
        lines.append(f"- ⚠ {peer['warning']}")

    if peer.get("pe_median") is not None:
        lines.append(f"- 行业 PE 中位数: {peer['pe_median']} (P25={peer.get('pe_p25')}, P75={peer.get('pe_p75')})")
        lines.append(f"- 标的 PE 同业分位: {peer.get('pe_percentile_in_industry', 'N/A')}%")
        if peer.get("pe_premium_pct") is not None:
            prem = peer["pe_premium_pct"]
            tag = "溢价" if prem > 0 else "折价"
            lines.append(f"- 相对行业中位 PE **{tag} {abs(prem)}%**")
    else:
        lines.append("- 同业 PE 数据不足")

    lines.extend(["", "## 简化 DCF (三情景)", ""])
    if dcf.get("error"):
        lines.append(f"> {dcf['error']}")
    else:
        lines.append("| 情景 | 增长率 | 每股内在价值 | 安全边际 | 溢价/折价 |")
        lines.append("|------|--------|-------------|---------|----------|")
        for scen_name, scen in dcf.get("scenarios", {}).items():
            iv = scen.get("intrinsic_value_per_share", "N/A")
            mos = scen.get("margin_of_safety_pct")
            prem = scen.get("premium_pct")
            mos_s = f"{mos}%" if mos is not None else "N/A"
            prem_s = f"{prem}%" if prem is not None else "N/A"
            lines.append(
                f"| {scen_name} | {scen.get('growth_rate')}% | ¥{iv} | {mos_s} | {prem_s} |"
            )
        lines.extend([
            "",
            f"> WACC={dcf.get('wacc', 0.1)*100:.0f}%, 基于近3年平均 FCF。"
            " DCF 对增长率假设敏感, 请结合三情景综合判断。",
        ])

    lines.extend([
        "",
        "---",
        f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
    ])

    report = "\n".join(lines)
    out_path = os.path.join(STOCK_DATA_DIR, symbol, "valuation-report.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("估值报告已保存 → %s", out_path)
    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    print(generate_valuation_report(sym))
