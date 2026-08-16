"""Quality + undervalued A-share scanner (value funnel + PB-ROE + DeepSeek).

Layer1 lives here first; later tasks add Layer2–4 and scan lifecycle.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from collections import defaultdict
from datetime import datetime

import pandas as pd

from board_filters import is_chinext

log = logging.getLogger("quality_value_scanner")

LAYER1_CAP = 100
_FINANCE_INDUSTRIES = ("银行", "非银金融", "保险", "证券", "多元金融")
_ST_MARKERS = ("ST", "*ST", "退市")


def is_finance_industry(industry: str | None) -> bool:
    text = str(industry or "")
    return any(k in text for k in _FINANCE_INDUSTRIES)


def _is_st(name: str) -> bool:
    n = str(name or "")
    return any(m in n for m in _ST_MARKERS)


def _industry_means(rows: list[dict]) -> dict[str, dict]:
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        ind = str(r.get("industry") or "").strip()
        if not ind:
            continue
        buckets[ind].append(r)
    out = {}
    for ind, items in buckets.items():
        pes = [float(x["pe"]) for x in items if x.get("pe") and float(x["pe"]) > 0]
        pbs = [float(x["pb"]) for x in items if x.get("pb") and float(x["pb"]) > 0]
        if len(pes) >= 2:
            out[ind] = {
                "pe_mean": sum(pes) / len(pes),
                "pb_mean": (sum(pbs) / len(pbs)) if pbs else None,
                "n": len(items),
            }
    return out


def layer1_coarse_filter(rows: list[dict], cap: int | None = None) -> tuple[list[dict], dict]:
    """Same-industry PE/PB cheap screen. Drop ST and ChiNext. Cap after ranking."""
    cleaned = []
    dropped_st = dropped_pe = dropped_chinext = 0
    for r in rows:
        if is_chinext(str(r.get("symbol") or "")):
            dropped_chinext += 1
            continue
        if _is_st(r.get("name", "")):
            dropped_st += 1
            continue
        pe = r.get("pe")
        try:
            pe_f = float(pe) if pe is not None else None
        except (TypeError, ValueError):
            pe_f = None
        if pe_f is None or pe_f <= 0:
            dropped_pe += 1
            continue
        item = dict(r)
        item["pe"] = pe_f
        try:
            item["pb"] = float(r["pb"]) if r.get("pb") is not None else None
        except (TypeError, ValueError):
            item["pb"] = None
        try:
            item["div_yield"] = float(r["div_yield"]) if r.get("div_yield") is not None else None
        except (TypeError, ValueError):
            item["div_yield"] = None
        cleaned.append(item)

    means = _industry_means(cleaned)
    kept = []
    for r in cleaned:
        ind = str(r.get("industry") or "").strip()
        if not ind or ind not in means:
            r["industry_unknown"] = True
            if r.get("div_yield") is not None and r["div_yield"] < 2.5:
                continue
            kept.append(r)
            continue
        m = means[ind]
        if r["pe"] >= m["pe_mean"]:
            continue
        if r.get("pb") is not None and m.get("pb_mean") and r["pb"] >= m["pb_mean"]:
            continue
        if r.get("div_yield") is not None and r["div_yield"] < 2.5:
            continue
        r["industry_pe_mean"] = round(m["pe_mean"], 2)
        r["industry_pb_mean"] = round(m["pb_mean"], 2) if m.get("pb_mean") else None
        if is_finance_industry(ind) and r.get("pb") is not None and r["pb"] < 1:
            r["finance_pb_undervalue"] = True
        pe_m = m["pe_mean"] or r["pe"]
        pb_m = m.get("pb_mean") or r.get("pb") or 1.0
        r["cheapness"] = (r["pe"] / pe_m) * ((r["pb"] / pb_m) if r.get("pb") else 1.0)
        kept.append(r)
    kept.sort(key=lambda x: x.get("cheapness", 9e9))
    if cap is None:
        cap = LAYER1_CAP
    kept = kept[:cap]
    stats = {
        "in": len(rows),
        "out": len(kept),
        "dropped_st": dropped_st,
        "dropped_pe": dropped_pe,
        "dropped_chinext": dropped_chinext,
    }
    return kept, stats


def layer2_fundamental_filter(rows: list[dict]) -> tuple[list[dict], dict]:
    """ROE/growth/debt landmines. Finance skips debt gate. Missing 扣非/分红 → unknown, keep."""
    kept = []
    for r in rows:
        roe = r.get("roe")
        growth = r.get("np_cagr_3y")
        if roe is None or float(roe) < 10:
            continue
        if growth is None or float(growth) < 5:
            continue
        finance = is_finance_industry(r.get("industry"))
        debt = r.get("debt_ratio")
        if not finance:
            if debt is None or float(debt) >= 60:
                continue
        else:
            if r.get("div_yield") is not None and float(r["div_yield"]) < 2.5:
                continue
        nr = r.get("nonrecurring_ratio")
        item = dict(r)
        if nr is None:
            item["nonrecurring_status"] = "unknown"
        else:
            if float(nr) < 0.80:
                continue
            item["nonrecurring_status"] = "ok"
        payout = r.get("payout_stable")
        if payout is False:
            continue
        if payout is None:
            item["payout_status"] = "unknown"
        else:
            item["payout_status"] = "ok"
        kept.append(item)
    return kept, {"in": len(rows), "out": len(kept)}


def _percentile_rank(value: float, series: pd.Series) -> float | None:
    """Share of strictly-lower positive history. Do not import valuation._percentile_rank."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean > 0]
    if not len(clean) or value is None or value <= 0:
        return None
    return float((clean < value).sum() / len(clean) * 100)


def pb_roe_score(row: dict) -> float:
    roe = float(row.get("roe") or 0)
    pb = float(row.get("pb") or 0)
    if pb <= 0:
        return 0.0
    return roe / pb


def layer3_rank_and_cap(rows: list[dict], per_industry: int = 2, top_n: int = 20) -> list[dict]:
    scored = []
    for r in rows:
        item = dict(r)
        item["pb_roe"] = round(pb_roe_score(r), 4)
        scored.append(item)
    scored.sort(key=lambda x: x["pb_roe"], reverse=True)
    counts: dict[str, int] = defaultdict(int)
    out = []
    for r in scored:
        ind = str(r.get("industry") or "未知")
        if counts[ind] >= per_industry:
            continue
        counts[ind] += 1
        out.append(r)
        if len(out) >= top_n:
            break
    return out


def pe_percentile_in_window(current_pe: float, hist: pd.DataFrame, as_of=None, years: int = 5) -> float | None:
    if hist is None or hist.empty or current_pe is None or current_pe <= 0:
        return None
    as_of = pd.Timestamp(as_of or datetime.now())
    df = hist.copy()
    col = "数据日期" if "数据日期" in df.columns else df.columns[0]
    df[col] = pd.to_datetime(df[col], errors="coerce")
    pe_col = "PE(TTM)" if "PE(TTM)" in df.columns else None
    if pe_col is None:
        return None
    start = as_of - pd.DateOffset(years=years)
    window = df[(df[col] > start) & (df[col] <= as_of)][pe_col]
    pct = _percentile_rank(float(current_pe), window)
    return round(pct, 1) if pct is not None else None


def apply_pe_percentile_gate(rows: list[dict], max_pct: float = 30.0) -> list[dict]:
    kept = []
    for r in rows:
        pct = r.get("pe_percentile_5y")
        item = dict(r)
        if pct is None:
            item["pe_percentile_status"] = "unknown"
            kept.append(item)
            continue
        if float(pct) > max_pct:
            continue
        item["pe_percentile_status"] = "ok"
        kept.append(item)
    return kept


def _extract_json(raw: str):
    text = str(raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    for start_char, end_char in (("[", "]"), ("{", "}")):
        s = text.find(start_char)
        e = text.rfind(end_char)
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    return None


def parse_value_verdict(raw: str) -> dict:
    data = _extract_json(raw)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return {}
    return data


def parse_value_verdict_list(raw: str) -> list[dict]:
    data = _extract_json(raw)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def select_final_picks(cands: list[dict], max_n: int = 5) -> list[dict]:
    eligible = []
    for c in cands:
        llm = c.get("llm") or {}
        if llm.get("verdict") != "买入":
            continue
        if llm.get("trap") is True:
            continue
        if llm.get("cycle") == "衰退":
            continue
        item = dict(c)
        item["_score"] = float(llm.get("score") or 0)
        eligible.append(item)
    eligible.sort(key=lambda x: x["_score"], reverse=True)
    out = []
    for item in eligible[:max_n]:
        item.pop("_score", None)
        out.append(item)
    return out


def apply_layer4_batch(cands: list[dict], raw: str) -> list[dict]:
    """Merge one batch LLM JSON array onto candidates, then veto/cap."""
    verdicts = parse_value_verdict_list(raw)
    by_sym = {str(v.get("symbol") or "").zfill(6): v for v in verdicts}
    merged = []
    for c in cands:
        item = dict(c)
        sym = str(item.get("symbol") or "").zfill(6)
        llm = by_sym.get(sym)
        if llm is None:
            continue
        item["llm"] = llm
        merged.append(item)
    return select_final_picks(merged, max_n=5)


VALUE_CLIST_FIELDS = (
    "f12,f14,f2,f3,f4,f5,f6,f8,f9,f15,f16,f17,f18,f20,f21,f23,f133,f37"
)


def _num_val(v):
    if v in ("-", "", None):
        return None
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_clist_row(item: dict) -> dict:
    code = str(item.get("f12") or "").zfill(6)
    div = _num_val(item.get("f133"))
    if div is None:
        div = _num_val(item.get("f37"))
    return {
        "symbol": code,
        "name": str(item.get("f14") or ""),
        "price": _num_val(item.get("f2")),
        "pe": _num_val(item.get("f9")),
        "pb": _num_val(item.get("f23")),
        "div_yield": div,
        "market_cap": _num_val(item.get("f20")),
    }


def rows_from_spot_df(df: pd.DataFrame) -> list[dict]:
    rows = []
    if df is None or df.empty:
        return rows
    for _, rec in df.iterrows():
        code = str(rec.get("代码") or "").zfill(6)
        div = rec.get("股息率") if "股息率" in df.columns else None
        pb = rec.get("市净率") if "市净率" in df.columns else None
        pe = rec.get("市盈率-动态") if "市盈率-动态" in df.columns else None
        rows.append({
            "symbol": code,
            "name": str(rec.get("名称") or ""),
            "pe": _num_val(pe),
            "pb": _num_val(pb),
            "div_yield": _num_val(div),
        })
    return rows


def _load_industry_cache() -> dict[str, str]:
    """Read-only. Never rebuild Eastmoney industry boards here."""
    import os
    paths = []
    try:
        from config import STOCK_CACHE_DIR
        paths.append(os.path.join(STOCK_CACHE_DIR, ".industry_map.json"))
        paths.append(os.path.join(STOCK_CACHE_DIR, ".valuation", "industry_map.json"))
    except Exception:
        pass
    for path in paths:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k).zfill(6): str(v) for k, v in data.items()}
        except Exception:
            continue
    return {}


def attach_industry(rows: list[dict], industry_map: dict | None = None) -> list[dict]:
    mapping = industry_map if industry_map is not None else _load_industry_cache()
    out = []
    for r in rows:
        item = dict(r)
        sym = str(item.get("symbol") or "").zfill(6)
        item["symbol"] = sym
        if not item.get("industry"):
            item["industry"] = mapping.get(sym, "")
        out.append(item)
    return out


def _parse_cn_number(val):
    if val is None or val is False:
        return None
    s = str(val).strip().rstrip("%")
    if not s or s in ("False", "-", "None", "nan"):
        return None
    multiplier = 1.0
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


def _parse_pct(val):
    if val is None or val is False:
        return None
    s = str(val).strip().rstrip("%")
    if not s or s in ("False", "-", "None", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _col(df: pd.DataFrame, *needles: str) -> str | None:
    cols = list(df.columns)
    for n in needles:
        for c in cols:
            if str(c) == n:
                return c
        for c in cols:
            if n in str(c):
                return c
    return None


def _nonrecurring_ratio(raw, net_profit: float | None) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s in ("-", "None", "nan"):
        return None
    if "%" in s:
        pct = _parse_pct(s)
        return None if pct is None else pct / 100.0
    if "亿" in s or "万" in s:
        amt = _parse_cn_number(s)
        if amt is None or not net_profit:
            return None
        return amt / net_profit
    try:
        num = float(s)
    except ValueError:
        return None
    if abs(num) <= 1.0:
        return num
    if abs(num) <= 100:
        return num / 100.0
    if not net_profit:
        return None
    return num / net_profit


def parse_ths_annuals(df: pd.DataFrame | None) -> dict:
    """ROE / debt / 3y NP CAGR / 扣非 ratio from Tonghuashun annual abstract."""
    empty = {
        "roe": None, "debt_ratio": None, "np_cagr_3y": None, "nonrecurring_ratio": None,
    }
    if df is None or df.empty:
        return empty
    work = df.copy()
    date_col = _col(work, "报告期") or work.columns[0]
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col, ascending=False)
    if work.empty:
        return empty
    latest = work.iloc[0]
    roe_col = _col(work, "净资产收益率")
    debt_col = _col(work, "资产负债率")
    np_col = _col(work, "净利润")
    nr_col = _col(work, "扣非")
    net_profit = _parse_cn_number(latest.get(np_col)) if np_col else None
    profits = []
    if np_col:
        for _, row in work.head(3).iterrows():
            profits.append(_parse_cn_number(row.get(np_col)))
    cagr = None
    if len(profits) >= 3 and profits[0] and profits[-1] and profits[-1] > 0 and profits[0] > 0:
        cagr = round(((profits[0] / profits[-1]) ** (1 / 2) - 1) * 100, 1)
    nr_raw = latest.get(nr_col) if nr_col else None
    return {
        "roe": _parse_pct(latest.get(roe_col)) if roe_col else None,
        "debt_ratio": _parse_pct(latest.get(debt_col)) if debt_col else None,
        "np_cagr_3y": cagr,
        "nonrecurring_ratio": _nonrecurring_ratio(nr_raw, net_profit),
    }


def _year_from_cell(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        n = int(float(val))
        if 1990 <= n <= 2100:
            return n
    except (TypeError, ValueError):
        pass
    dt = pd.to_datetime(val, errors="coerce")
    if pd.isna(dt):
        return None
    return int(dt.year)


def infer_payout_stable(div_df: pd.DataFrame | None) -> bool | None:
    """True if ≥2 of the last 3 years paid cash dividend; False if history shows otherwise."""
    if div_df is None or getattr(div_df, "empty", True):
        return None
    year_col = _col(div_df, "年度", "报告期", "除权除息日")
    amt_col = _col(div_df, "现金分红", "每股派息", "派息", "分红金额")
    if year_col is None:
        return None
    years: dict[int, float] = {}
    for _, row in div_df.iterrows():
        y = _year_from_cell(row.get(year_col))
        if y is None:
            continue
        amt = 0.0
        if amt_col is not None:
            amt = _parse_cn_number(row.get(amt_col)) or 0.0
        years[y] = years.get(y, 0.0) + amt
    if len(years) < 3:
        return None
    recent = sorted(years.keys(), reverse=True)[:3]
    paid = sum(1 for y in recent if years[y] > 0)
    return paid >= 2


def _quality_value_cache_dir(cache_dir: str | None = None) -> str:
    if cache_dir:
        return cache_dir
    try:
        from config import STOCK_CACHE_DIR
        return os.path.join(STOCK_CACHE_DIR, ".quality_value")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".quality_value")


def _read_fresh_fund_cache(path: str, now: datetime, hours: float = 24) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        fetched = datetime.fromisoformat(str(data.get("fetched_at") or ""))
        if (now - fetched).total_seconds() < hours * 3600:
            return data
    except Exception:
        return None
    return None


def _default_ths_fetcher(symbol: str):
    import akshare as ak
    return ak.stock_financial_abstract_ths(symbol=symbol, indicator="按年度")


def _default_dividend_fetcher(symbol: str):
    import akshare as ak
    from eastmoney_throttle import eastmoney_slot
    with eastmoney_slot():
        try:
            return ak.stock_fhps_detail_em(symbol=symbol)
        except Exception:
            try:
                return ak.stock_history_dividend_detail(symbol=symbol, indicator="分红")
            except Exception:
                return None


def fetch_fundamentals_for_value(
    symbol: str,
    *,
    cache_dir: str | None = None,
    now: datetime | None = None,
    ths_fetcher=None,
    dividend_fetcher=None,
) -> dict:
    """THS annuals + dividend history. 24h JSON cache. Failures stay None."""
    now = now or datetime.now()
    sym = str(symbol).zfill(6)
    root = _quality_value_cache_dir(cache_dir)
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{sym}.json")
    cached = _read_fresh_fund_cache(path, now)
    if cached is not None:
        return cached
    out = {
        "symbol": sym,
        "fetched_at": now.isoformat(),
        "roe": None,
        "np_cagr_3y": None,
        "debt_ratio": None,
        "nonrecurring_ratio": None,
        "payout_stable": None,
    }
    try:
        fetcher = ths_fetcher or _default_ths_fetcher
        parsed = parse_ths_annuals(fetcher(sym))
        out.update({k: parsed.get(k) for k in (
            "roe", "np_cagr_3y", "debt_ratio", "nonrecurring_ratio",
        )})
    except Exception as e:
        log.warning("价值选股财务失败 %s: %s", sym, e)
    try:
        dfetch = dividend_fetcher or _default_dividend_fetcher
        out["payout_stable"] = infer_payout_stable(dfetch(sym))
    except Exception as e:
        log.warning("价值选股分红失败 %s: %s", sym, e)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        log.warning("价值选股缓存写入失败 %s: %s", sym, e)
    return out


def attach_pe_percentile(rows: list[dict]) -> list[dict]:
    """Attach 5y PE percentile; missing history stays None (unknown)."""
    out = []
    for r in rows:
        item = dict(r)
        try:
            from valuation import fetch_valuation_history
            hist = fetch_valuation_history(str(item.get("symbol") or ""))
            item["pe_percentile_5y"] = pe_percentile_in_window(item.get("pe"), hist)
        except Exception:
            item["pe_percentile_5y"] = None
        out.append(item)
    return out


try:
    from config import STOCK_REPORTS_ROOT
except ImportError:
    STOCK_REPORTS_ROOT = os.path.join(os.path.expanduser("~"), "reports", "stock")

QUALITY_VALUE_DIR = os.path.join(STOCK_REPORTS_ROOT, "quality_value")
PROGRESS_FILE = os.path.join(QUALITY_VALUE_DIR, "qv_progress.json")

if not hasattr(sys, "_qv_scan_lock"):
    sys._qv_scan_lock = threading.Lock()
if not hasattr(sys, "_qv_stop_event"):
    sys._qv_stop_event = threading.Event()
if not hasattr(sys, "_qv_thread"):
    sys._qv_thread = None
if not hasattr(sys, "_qv_scan_status"):
    sys._qv_scan_status = {
        "status": "idle",
        "progress": 0,
        "step": "",
        "started_at": "",
        "error": None,
        "picks_count": 0,
    }


def _ensure_dirs():
    os.makedirs(QUALITY_VALUE_DIR, exist_ok=True)


def _save_progress(prog: dict):
    _ensure_dirs()
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(prog, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        log.warning("保存进度失败: %s", e)


def get_qv_status() -> dict:
    st = dict(getattr(sys, "_qv_scan_status", {}))
    if os.path.isfile(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                disk = json.load(f)
            st.update(disk)
        except Exception:
            pass
    return st


def _set_status(**kwargs):
    st = getattr(sys, "_qv_scan_status")
    st.update(kwargs)
    _save_progress(st)


def _fetch_market_snapshot_rows() -> list[dict]:
    """Eastmoney clist with PB/div fields, then akshare spot. Tests monkeypatch this."""
    try:
        import requests
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "5500", "po": "1", "np": "1",
            "ut": "bd1d9dd10319470d11d3d66416f1c148",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:1 t:80",
            "fields": VALUE_CLIST_FIELDS,
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        diff = (resp.json().get("data") or {}).get("diff") or []
        return [parse_clist_row(item) for item in diff if item.get("f12")]
    except Exception as e:
        log.warning("东财快照失败, 尝试 akshare: %s", e)
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        return rows_from_spot_df(df)
    except Exception as e:
        log.error("全市场快照失败: %s", e)
        return []


def _generate_report(picks: list[dict], stats: dict, use_deepseek: bool) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 优质低估选股报告 — {date_str}",
        "",
        "> ⚠️ **不构成投资建议**。筛选仅供参考，最终投资决策需自行判断。",
        "",
        f"- DeepSeek 终审: {'失败（未用规则层顶替，宁缺毋滥）' if stats.get('llm_failed') else ('是' if use_deepseek else '否（规则层 Top5，未经 AI 终审）')}",
        f"- Layer1 入围: {stats.get('layer1_out', 0)}",
        "",
    ]
    if not picks:
        lines.extend([
            "## 推荐: 暂无",
            "",
            "本次未选出标的（**宁缺毋滥**）。漏斗过严或当日没有同时满足优质+低估的股票——这是功能，不是故障。",
            "",
        ])
        return "\n".join(lines)
    lines.append(f"## 推荐 ({len(picks)} 只)")
    lines.append("")
    for p in picks:
        lines.append(f"### {p.get('name', '')} ({p.get('symbol', '')})")
        lines.append(f"- 行业: {p.get('industry', '')}")
        lines.append(f"- PE / PB / 股息率: {p.get('pe')} / {p.get('pb')} / {p.get('div_yield')}")
        lines.append(f"- ROE / PB-ROE: {p.get('roe')} / {p.get('pb_roe')}")
        lines.append("")
    return "\n".join(lines)


def _index_report_to_rag(report_path: str, date_str: str, item_type: str, title: str):
    try:
        from long_term_scanner import _index_report_to_rag as _lt_index
        _lt_index(report_path, date_str, item_type, title)
    except Exception as e:
        log.warning("RAG 索引失败: %s", e)


def _save_results(picks: list[dict], stats: dict, use_deepseek: bool):
    _ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")
    result_path = os.path.join(QUALITY_VALUE_DIR, f"{date_str}.json")
    payload = {
        "date": date_str,
        "picks": picks,
        "stats": stats,
        "use_deepseek": use_deepseek,
        "llm_skipped": not use_deepseek,
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    report = _generate_report(picks, stats, use_deepseek)
    report_path = os.path.join(QUALITY_VALUE_DIR, f"{date_str}-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    _index_report_to_rag(report_path, date_str, "stock_scan_quality_value", f"优质低估 {date_str}")


def _call_value_llm(cands: list[dict]) -> str:
    """One batch DeepSeek/Ollama call. Tests may monkeypatch this."""
    try:
        from llm_reasoning import build_quality_value_system_prompt
        from config import call_deepseek
        lines = []
        for c in cands:
            lines.append(
                f"- {c.get('symbol')} {c.get('name','')} 行业={c.get('industry')} "
                f"PE={c.get('pe')} PB={c.get('pb')} 股息={c.get('div_yield')} "
                f"ROE={c.get('roe')} PB-ROE={c.get('pb_roe')} "
                f"PE分位={c.get('pe_percentile_5y')} 扣非={c.get('nonrecurring_status')}"
            )
        user = "请对以下候选做价值终审，输出JSON数组：\n" + "\n".join(lines)
        result = call_deepseek(
            build_quality_value_system_prompt(),
            user,
        )
        if isinstance(result, dict):
            return str(result.get("content") or result.get("text") or "")
        return str(result or "")
    except Exception as e:
        log.warning("价值终审 LLM 失败: %s", e)
        return ""


def _run_qv_scan(use_deepseek: bool = False):
    _set_status(
        status="running", progress=5, step="layer1",
        started_at=datetime.now().isoformat(), error=None, picks_count=0,
    )
    try:
        if sys._qv_stop_event.is_set():
            _set_status(status="stopped", step="stopped")
            return
        rows = _fetch_market_snapshot_rows()
        rows = attach_industry(rows)
        layer1, l1_stats = layer1_coarse_filter(rows)
        stats = {"layer1_in": l1_stats.get("in", 0), "layer1_out": l1_stats.get("out", 0)}
        _set_status(progress=40, step="layer2")
        if sys._qv_stop_event.is_set():
            _set_status(status="stopped", step="stopped")
            return
        picks = []
        if layer1:
            enriched = []
            n = len(layer1)
            for i, r in enumerate(layer1):
                if sys._qv_stop_event.is_set():
                    _set_status(status="stopped", step="stopped")
                    return
                fund = fetch_fundamentals_for_value(r.get("symbol") or "")
                item = dict(r)
                for k in ("roe", "np_cagr_3y", "debt_ratio", "nonrecurring_ratio", "payout_stable"):
                    if k in fund:
                        item[k] = fund[k]
                enriched.append(item)
                if n:
                    _set_status(progress=40 + int(30 * (i + 1) / n), step="layer2")
            layer2, l2_stats = layer2_fundamental_filter(enriched)
            stats["layer2_in"] = l2_stats.get("in", 0)
            stats["layer2_out"] = l2_stats.get("out", 0)
            _set_status(progress=75, step="layer3")
            ranked = layer3_rank_and_cap(layer2, per_industry=2, top_n=20)
            ranked = attach_pe_percentile(ranked)
            ranked = apply_pe_percentile_gate(ranked)
            stats["layer3_out"] = len(ranked)
            _set_status(progress=88, step="layer4")
            if use_deepseek:
                raw = _call_value_llm(ranked[:10])
                if raw:
                    picks = apply_layer4_batch(ranked[:10], raw)
                else:
                    picks = []
                    stats["llm_failed"] = True
            else:
                picks = ranked[:5]
                for p in picks:
                    p["llm_skipped"] = True
        _save_results(picks, stats, use_deepseek)
        _set_status(status="done", progress=100, step="done", picks_count=len(picks))
    except Exception as e:
        log.exception("优质低估扫描失败")
        _set_status(status="error", error=str(e), step="error")


def start_qv_scan(use_deepseek: bool = False) -> dict:
    with sys._qv_scan_lock:
        t = getattr(sys, "_qv_thread", None)
        if t is not None and t.is_alive():
            return {"ok": False, "error": "优质低估扫描正在进行中", "status": get_qv_status()}
        sys._qv_stop_event.clear()
        sys._qv_thread = threading.Thread(
            target=_run_qv_scan, kwargs={"use_deepseek": use_deepseek},
            daemon=True, name="qv-scanner",
        )
        sys._qv_thread.start()
        return {"ok": True, "message": "优质低估扫描已启动"}


def stop_qv_scan() -> dict:
    sys._qv_stop_event.set()
    return {"ok": True, "message": "已发送停止信号"}


def get_qv_latest_result() -> dict | None:
    _ensure_dirs()
    files = sorted(
        [f for f in os.listdir(QUALITY_VALUE_DIR)
         if f.endswith(".json") and f not in ("qv_progress.json", "history.json")],
        reverse=True,
    )
    if not files:
        return None
    try:
        with open(os.path.join(QUALITY_VALUE_DIR, files[0]), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_qv_history() -> list[dict]:
    path = os.path.join(QUALITY_VALUE_DIR, "history.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_qv_result_by_date(date_str: str) -> dict | None:
    path = os.path.join(QUALITY_VALUE_DIR, f"{date_str}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_qv_scan_dates() -> list[str]:
    _ensure_dirs()
    dates = []
    for f in os.listdir(QUALITY_VALUE_DIR):
        if f.endswith(".json") and f not in ("qv_progress.json", "history.json"):
            dates.append(f.replace(".json", ""))
    dates.sort(reverse=True)
    return dates
