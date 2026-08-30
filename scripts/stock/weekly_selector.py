"""周线选股 + 策略回测.

策略:
  选股 (周线级别, 每周五收盘后筛选): 连续 3 周收盘价较前一周上涨 (周K三连阳).
  买入: 满足条件后的第四周第一个交易日 (周一) 开盘买入.
  持仓: 持有 5 个交易日; 期间亏损 >= 5% 立即止损; 否则满 5 日卖出.
  仓位: 每只股票等权 (1/N).

复用 fetch_market_data (akshare 后复权日线, 已缓存) 与 backtest_engine 的手续费/印花税常量.
后台线程 + 进度 JSON, 与 scanner 模式一致.
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from config import STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

WEEKLY_DIR = os.path.join(STOCK_REPORTS_ROOT, "weekly")
os.makedirs(WEEKLY_DIR, exist_ok=True)

STOP_LOSS_PCT = 0.05
HOLD_DAYS = 5
MIN_LISTING_DAYS = 60

# 交易成本 (与 backtest_engine 一致)
BUY_COMMISSION = 0.00025
SELL_COMMISSION = 0.00025
STAMP_TAX = 0.001
SLIPPAGE = 0.001
MIN_COMMISSION = 5.0

# 后台线程状态
_select_thread = None
_select_lock = threading.Lock()
_select_status = {"status": "idle", "progress": 0, "step": "", "result": None}

_bt_thread = None
_bt_lock = threading.Lock()
_bt_status = {"status": "idle", "progress": 0, "step": "", "result": None}

# 选股与回测各自独立的停止信号, 互不干扰 (Critical-1)
_select_stop = threading.Event()
_bt_stop = threading.Event()


def _ensure_dirs():
    os.makedirs(WEEKLY_DIR, exist_ok=True)


def _set_status(status_dict, **kw):
    status_dict.update(kw)


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def _ensure_stock_config():
    """后台线程中强制注入 stock config, 避免 RAG config 竞态导致 STOCK_DATA_DIR 缺失."""
    import importlib.util as _ilu
    _stock_dir = os.path.dirname(os.path.abspath(__file__))
    if _stock_dir not in sys.path:
        sys.path.insert(0, _stock_dir)
    _cfg_path = os.path.join(_stock_dir, "config.py")
    _spec = _ilu.spec_from_file_location("config", _cfg_path)
    _cfg = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_cfg)
    sys.modules["config"] = _cfg
    return _cfg


def _symbol_name_from_local(symbol_dir, symbol):
    """从本地 profile/realtime 取名称, 失败则用代码本身."""
    for fname in ("realtime.json", "profile.json"):
        path = os.path.join(symbol_dir, fname)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("名称") or data.get("name") or data.get("股票简称") or ""
            if name:
                return str(name)
        except Exception:
            continue
    return symbol


def _get_universe_from_local():
    """从本地 STOCK_DATA_DIR 构建股票池 (有 daily.csv 的代码). 不依赖网络."""
    _ensure_stock_config()
    from config import STOCK_DATA_DIR
    if not os.path.isdir(STOCK_DATA_DIR):
        return []
    out = []
    for code in os.listdir(STOCK_DATA_DIR):
        if not code.isdigit():
            continue
        sdir = os.path.join(STOCK_DATA_DIR, code)
        if not os.path.isfile(os.path.join(sdir, "daily.csv")):
            continue
        name = _symbol_name_from_local(sdir, code)
        if "ST" in name or "退" in name:
            continue
        out.append({"symbol": code.zfill(6), "name": name})
    log.info("本地股票池: %d 只 (来自 %s)", len(out), STOCK_DATA_DIR)
    return out


def _rows_from_spot_df(df):
    """把全市场快照 DataFrame 转成 [{symbol,name}, ...], 剔除 ST/退市/停牌."""
    out = []
    for _, row in df.iterrows():
        name = str(row.get("名称", ""))
        code = str(row.get("代码", "")).zfill(6)
        if not code or not code.isdigit():
            continue
        if "ST" in name or "退" in name:
            continue
        latest = row.get("最新价", None)
        vol = row.get("成交量", None)
        try:
            latest_ok = latest is not None and pd.notna(latest) and float(latest) > 0
        except Exception:
            latest_ok = False
        try:
            vol_ok = vol is not None and pd.notna(vol) and float(vol) > 0
        except Exception:
            vol_ok = False
        if not latest_ok or not vol_ok:
            continue
        out.append({"symbol": code, "name": name})
    return out


def _get_universe(prefer_local=False):
    """返回股票代码+名称列表.

    prefer_local=True (选股默认): 直接用本地缓存目录, 不依赖 akshare 行情快照.
    prefer_local=False: 优先全市场快照, 失败再回退 scanner / 本地缓存.
    """
    _ensure_stock_config()

    if prefer_local:
        local = _get_universe_from_local()
        if local:
            return local
        log.warning("本地股票池为空, 尝试网络行情源...")

    import akshare as ak
    df = None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.warning("akshare 全市场行情失败: %s", e)

    if df is None or df.empty:
        try:
            _ensure_stock_config()
            from scanner import _fetch_market_eastmoney
            df = _fetch_market_eastmoney()
        except Exception as e2:
            log.warning("备用行情源失败: %s", e2)

    if df is not None and not df.empty:
        out = _rows_from_spot_df(df)
        if out:
            return out

    # 最终兜底: 本地缓存目录
    local = _get_universe_from_local()
    if local:
        log.warning("行情源均失败, 已回退本地股票池 %d 只", len(local))
        return local
    return []


def _normalize_daily(df):
    """把缓存 CSV (中文列名) 规整为 date/open/close/high/low/volume."""
    if df is None or df.empty:
        return None
    col_map = {
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
    }
    have = {c: df[c] for c in col_map if c in df.columns}
    if "date" not in {col_map[c] for c in have}:
        return None
    out = pd.DataFrame(have)
    out = out.rename(columns={c: col_map[c] for c in have})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ("open", "close", "high", "low", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return out


def _select_lookback_days(weeks=3, for_network=False):
    """选股所需日历日回溯.

    for_network=True: 只为判定连涨 N 周, 尽量短 (约 N+3 周), 加快逐只补抓.
    for_network=False: 本地模式可稍长, 便于次新股判定.
    """
    if for_network:
        # N+1 根周K + 2 周缓冲, 约 (N+3)*7 天
        return max(40, int(weeks + 3) * 10)
    return max(120, int(weeks + 1) * 14 + int(MIN_LISTING_DAYS * 1.8) + 30)


def _is_subnew(daily, ref_date):
    """判断在 ref_date 当日是否为次新股 (上市不满 MIN_LISTING_DAYS 个交易日).

    短窗口联网补抓时行数天然 < 60, 无法可靠判定 → 不按次新剔除 (放行).
    """
    if daily is None or daily.empty:
        return True
    ref = pd.Timestamp(ref_date)
    covered = daily[daily["date"] <= ref]
    if covered.empty:
        return True
    cnt = len(covered)
    if cnt >= MIN_LISTING_DAYS:
        return False
    # 数据跨度本身就短 (典型短窗口补抓) → 无法判定, 不剔除
    span_days = (covered["date"].iloc[-1] - covered["date"].iloc[0]).days
    if span_days < MIN_LISTING_DAYS:
        return False
    return True


def _cache_usable(norm, start_date=None, end_date=None, min_rows=MIN_LISTING_DAYS):
    """缓存是否足够做周线判定: 末尾够新 + 覆盖区间有足够交易日."""
    if norm is None or norm.empty:
        return False
    ref_end = pd.Timestamp(end_date) if end_date else pd.Timestamp(datetime.now().date())
    today = pd.Timestamp(datetime.now().date())
    # 回测会把 fetch_end 设成 end+20 天; 不能用未来日期把今日缓存判过期
    if ref_end > today:
        ref_end = today
    # 末尾落后目标日超过 10 天则视为过期
    if norm["date"].iloc[-1] < ref_end - pd.Timedelta(days=10):
        return False
    covered = norm[norm["date"] <= ref_end]
    if len(covered) < min_rows:
        return False
    if start_date:
        # 只需近期有数据, 不要求缓存从多年前开始
        if covered["date"].iloc[0] > pd.Timestamp(start_date) + pd.Timedelta(days=30):
            # 缓存起始太晚, 可能不够算次新股, 但仍可用近期周线; 行数够则放行
            if len(covered) < min_rows:
                return False
    return True


def _fetch_short_ohlcv(symbol, start_date, end_date, period="daily"):
    """短窗口抓取 (仅内存), 不覆盖本地长期 daily.csv.

    period: "daily" | "weekly" — 选股联网补缺优先用 weekly, 一次返回周K, 更快.
    """
    import akshare as ak
    sd = pd.Timestamp(start_date).strftime("%Y%m%d")
    ed = pd.Timestamp(end_date).strftime("%Y%m%d")
    try:
        raw = ak.stock_zh_a_hist(
            symbol=symbol, period=period,
            start_date=sd, end_date=ed, adjust="hfq",
        )
        return _normalize_daily(raw)
    except Exception as e:
        log.debug("短窗口抓取 %s (%s) 失败: %s", symbol, period, e)
        return None


def _load_daily(symbol, start_date=None, end_date=None, short_fetch=True, allow_network=True):
    """加载后复权日线.

    short_fetch=True (选股默认): 缓存可用则用缓存; 否则只抓 start~end 短窗口,
    不写盘覆盖长期缓存. short_fetch=False (回测): 需要长历史时走 fetch_daily_ohlcv.
    allow_network=False: 仅用本地缓存, 不可用则返回 None (选股快速模式).
    """
    from fetch_market_data import load_daily_ohlcv, fetch_daily_ohlcv

    cached = load_daily_ohlcv(symbol)
    norm = _normalize_daily(cached) if cached is not None else None
    if _cache_usable(norm, start_date, end_date):
        return norm

    # 选股快速模式: 不联网. 有过期缓存且行数够做周线判定时仍可用
    if not allow_network:
        if norm is not None and len(norm) >= max(20, MIN_LISTING_DAYS // 2):
            return norm
        return None

    # 缓存不可用 → 网络短抓 (优先周线, 失败再日线)
    if short_fetch and start_date and end_date:
        short = _fetch_short_ohlcv(symbol, start_date, end_date, period="weekly")
        if short is None or short.empty:
            short = _fetch_short_ohlcv(symbol, start_date, end_date, period="daily")
        if short is not None and not short.empty:
            return short
        if norm is not None and len(norm) >= 20:
            log.debug("%s 短抓失败, 回退过期缓存 (%d 行)", symbol, len(norm))
            return norm
        return None

    # 回测等长历史场景
    try:
        sd = pd.Timestamp(start_date).strftime("%Y%m%d") if start_date else None
        ed = pd.Timestamp(end_date).strftime("%Y%m%d") if end_date else None
        df = fetch_daily_ohlcv(symbol, start_date=sd, end_date=ed, adjust="hfq")
        return _normalize_daily(df)
    except Exception as e:
        log.debug("抓取 %s 失败: %s", symbol, e)
        return norm


def _to_weekly(daily):
    """日线重采样为周线 (W-FRI, 周五为周末标签).

    若输入已是周频 (相邻间隔中位数 >= 5 天, 如 akshare period=weekly), 直接当作周线.
    """
    if daily is None or daily.empty:
        return None
    d = daily.copy()
    gaps = d["date"].diff().dt.days.dropna()
    if len(gaps) and float(gaps.median()) >= 5:
        w = d.rename(columns={"date": "week_end"})
        cols = [c for c in ("week_end", "open", "close", "high", "low", "volume") if c in w.columns]
        return w[cols].dropna(subset=["close"]).reset_index(drop=True)
    d = d.set_index("date")
    w = d.resample("W-FRI").agg(
        open=("open", "first"), close=("close", "last"),
        high=("high", "max"), low=("low", "min"), volume=("volume", "sum"),
    ).dropna(subset=["close"])
    w = w.reset_index().rename(columns={"date": "week_end"})
    return w


def _latest_friday(today=None):
    today = today or datetime.now().date()
    # weekday: Mon=0 ... Fri=4, Sat=5, Sun=6
    offset = (today.weekday() - 4) % 7
    return today - timedelta(days=offset)


def _parse_friday(date_str):
    """解析用户输入的周五日期, 容错多种格式. 返回 date 或 None."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 选股条件与单笔交易模拟
# ---------------------------------------------------------------------------

def _n_up(weekly, target_friday, n=3):
    """检查 target_friday 当周及此前连续 n 周收涨 (周K n 连阳).

    需要 n+1 根周收盘严格递增: close[T] > close[T-1] > ... > close[T-n].
    返回 (bool, 涨幅列表 [w1..wn]) 或 (False, None).
    """
    if weekly is None or len(weekly) < n + 1:
        return False, None
    target = pd.Timestamp(target_friday)
    # 找到 <= target 的最近一个周末
    sub = weekly[weekly["week_end"] <= target]
    if len(sub) < n + 1:
        return False, None
    last = sub.tail(n + 1).reset_index(drop=True)
    c = last["close"].astype(float).tolist()
    if all(c[i + 1] > c[i] for i in range(n)):
        rets = [round((c[i + 1] / c[i] - 1) * 100, 2) for i in range(n)]
        return True, rets
    return False, None


def _three_up(weekly, target_friday):
    """向后兼容: 连续 3 周收涨."""
    return _n_up(weekly, target_friday, 3)


def _simulate_hold(daily, entry_friday):
    """模拟买入持有: entry_friday 后第一个交易日开盘买入, 持有 HOLD_DAYS 日.

    T+1: 买入当日不可卖出. 止损: 从第 2 个交易日起, 若当日最低价 <=
    buy_price*(1-STOP_LOSS_PCT), 以止损价卖出; 否则第 HOLD_DAYS 日收盘卖出.
    返回 dict: entry_date, exit_date, entry_price, exit_price, reason.
    """
    if daily is None or daily.empty:
        return None
    target = pd.Timestamp(entry_friday)
    after = daily[daily["date"] > target].reset_index(drop=True)
    if len(after) < HOLD_DAYS:
        return None
    entry_day = after.iloc[0]
    entry_price = float(entry_day["open"]) * (1 + SLIPPAGE)
    stop_price = entry_price * (1 - STOP_LOSS_PCT)
    exit_date = None
    exit_price = None
    reason = "hold5"
    for i in range(1, HOLD_DAYS):
        row = after.iloc[i]
        low = float(row["low"])
        if low <= stop_price:
            exit_date = row["date"]
            exit_price = stop_price * (1 - SLIPPAGE)
            reason = "stoploss"
            break
    if exit_date is None:
        last = after.iloc[HOLD_DAYS - 1]
        exit_date = last["date"]
        exit_price = float(last["close"]) * (1 - SLIPPAGE)
    return {
        "entry_date": entry_day["date"].strftime("%Y-%m-%d"),
        "exit_date": exit_date.strftime("%Y-%m-%d"),
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "reason": reason,
    }


def _trade_return_pct(fact, per_stock_capital):
    """根据交易事实与单只分配资金计算净收益率 (含手续费/印花税, 含最低佣金)."""
    buy_price = fact["entry_price"]
    shares = per_stock_capital / buy_price
    buy_amount = shares * buy_price
    buy_comm = max(buy_amount * BUY_COMMISSION, MIN_COMMISSION)
    sell_amount = shares * fact["exit_price"]
    sell_comm = max(sell_amount * SELL_COMMISSION, MIN_COMMISSION) + sell_amount * STAMP_TAX
    net_pnl = sell_amount - buy_amount - buy_comm - sell_comm
    return net_pnl / buy_amount if buy_amount else 0.0


# ---------------------------------------------------------------------------
# 选股 (单次)
# ---------------------------------------------------------------------------

def get_select_status():
    with _select_lock:
        return dict(_select_status)


def get_select_result():
    with _select_lock:
        res = _select_status.get("result")
        return res


def select_weekly(date_str=None, weeks=3, allow_network=False):
    """启动周线选股 (后台线程).

    date_str: 目标周五, 默认最近周五
    weeks: 连续收涨周数
    allow_network: False=仅本地缓存(推荐, 通常数分钟内完成);
                   True=缺缓存时联网补抓(全市场可能数小时, 受东财限流)
    """
    global _select_thread
    weeks = max(1, min(int(weeks or 3), 26))
    allow_network = bool(allow_network)
    target = _parse_friday(date_str) or _latest_friday()
    with _select_lock:
        if _select_thread is not None and _select_thread.is_alive():
            return {"ok": False, "error": "选股正在进行中"}
        _select_status.update(
            status="running", progress=0, step="准备中",
            target=target.strftime("%Y-%m-%d"),
            weeks=weeks, allow_network=allow_network, result=None,
        )
    _select_stop.clear()

    def _eval_one(st, start_date, end_date):
        """单票评估. 返回 ('pick'|'skip'|'miss', payload)."""
        sym = st["symbol"]
        daily = _load_daily(
            sym, start_date, end_date,
            short_fetch=True, allow_network=allow_network,
        )
        if daily is None or daily.empty:
            return "miss", None
        if _is_subnew(daily, target):
            return "skip", None
        weekly = _to_weekly(daily)
        ok, rets = _n_up(weekly, target, weeks)
        if not ok:
            return "skip", None
        w = weekly[weekly["week_end"] <= pd.Timestamp(target)].tail(1).iloc[0]
        return "pick", {
            "symbol": sym,
            "name": st["name"],
            "week_end": target.strftime("%Y-%m-%d"),
            "week_close": round(float(w["close"]), 2),
            "returns": rets,
        }

    def _run():
        from concurrent.futures import ThreadPoolExecutor, as_completed
        try:
            _ensure_stock_config()
            # 默认仅本地: 股票池也来自本地缓存目录, 不依赖 akshare 快照
            universe = _get_universe(prefer_local=not allow_network)
            total = len(universe)
            if total == 0:
                _set_status(_select_status, status="error", step="无法获取市场行情", progress=0)
                return
            lookback = _select_lookback_days(weeks, for_network=allow_network)
            start_date = (target - timedelta(days=lookback)).strftime("%Y-%m-%d")
            end_date = target.strftime("%Y-%m-%d")
            mode = "联网补缺(逐只短窗口周K)" if allow_network else "仅本地缓存(快)"
            _set_status(
                _select_status,
                step=f"{total} 只 · {mode} · 回溯 {lookback} 天",
                progress=2,
            )
            picks = []
            n_miss = 0
            n_skip = 0
            done = 0
            # 本地高并发; 联网适度并发 (东财无全市场历史批量接口, 只能逐只)
            workers = 8 if allow_network else 12
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {
                    ex.submit(_eval_one, st, start_date, end_date): st
                    for st in universe
                }
                for fut in as_completed(futs):
                    if _select_stop.is_set():
                        for f in futs:
                            f.cancel()
                        _set_status(_select_status, status="stopped", step="已停止")
                        return
                    done += 1
                    try:
                        kind, payload = fut.result()
                    except Exception as e:
                        n_miss += 1
                        log.debug("选股失败: %s", e)
                        kind, payload = "miss", None
                    if kind == "pick" and payload:
                        picks.append(payload)
                    elif kind == "miss":
                        n_miss += 1
                    else:
                        n_skip += 1
                    if done % 20 == 0 or done == total:
                        _set_status(
                            _select_status,
                            step=f"扫描 {done}/{total} · 入选 {len(picks)} · 无缓存跳过 {n_miss}",
                            progress=int(2 + done / total * 96),
                        )
            picks.sort(key=lambda x: sum(x["returns"]), reverse=True)
            result = {
                "target": target.strftime("%Y-%m-%d"),
                "weeks": weeks,
                "allow_network": allow_network,
                "universe_total": total,
                "scanned": done,
                "skipped_no_data": n_miss,
                "count": len(picks),
                "picks": picks,
                "generated_at": datetime.now().isoformat(),
            }
            out_path = os.path.join(WEEKLY_DIR, f"select_{target.strftime('%Y%m%d')}_w{weeks}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            _set_status(
                _select_status, status="done",
                step=f"完成, 入选 {len(picks)} 只 (无缓存跳过 {n_miss})",
                progress=100, result=result,
            )
        except Exception as e:
            log.exception("周线选股失败")
            _set_status(_select_status, status="error", step=str(e), progress=0)

    with _select_lock:
        _select_thread = threading.Thread(target=_run, daemon=True)
        _select_thread.start()
    return {
        "ok": True,
        "message": "选股已启动" + ("" if allow_network else " (仅本地缓存)"),
        "target": target.strftime("%Y-%m-%d"),
    }


def stop_select():
    _select_stop.set()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 回测
# ---------------------------------------------------------------------------

def get_bt_status():
    with _bt_lock:
        return dict(_bt_status)


def get_bt_result():
    with _bt_lock:
        return _bt_status.get("result")


def _fridays_between(start, end):
    """枚举 [start, end] 之间所有周五 (含)."""
    out = []
    d = start
    while d.weekday() != 4:
        d += timedelta(days=1)
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def backtest_weekly(start_date, end_date, initial_capital=1000000, weeks=3):
    """启动周线策略回测 (后台线程). weeks 为连续收涨周数."""
    global _bt_thread
    weeks = max(1, min(int(weeks or 3), 26))
    try:
        start = datetime.strptime(str(start_date).strip()[:10], "%Y-%m-%d").date()
        end = datetime.strptime(str(end_date).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return {"ok": False, "error": "日期格式应为 YYYY-MM-DD"}
    cap = float(initial_capital) if initial_capital else 1000000.0

    with _bt_lock:
        if _bt_thread is not None and _bt_thread.is_alive():
            return {"ok": False, "error": "回测正在进行中"}
        _bt_status.update(status="running", progress=0, step="准备中",
                          start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
                          capital=cap, result=None)
    _bt_stop.clear()

    def _run():
        try:
            _ensure_stock_config()
            universe = _get_universe(prefer_local=False)
            total = len(universe)
            if total == 0:
                _set_status(_bt_status, status="error", step="无法获取市场行情", progress=0)
                return
            # 需要更早的日线用于周线回看 + 持仓模拟
            fetch_start = (start - timedelta(days=MIN_LISTING_DAYS * 2 + 60)).strftime("%Y-%m-%d")
            fetch_end = (end + timedelta(days=20)).strftime("%Y-%m-%d")
            # trades_by_entry: {entry_date_str: [trade_fact, ...]}
            trades_by_entry = {}
            for i, st in enumerate(universe):
                if _bt_stop.is_set():
                    _set_status(_bt_status, status="stopped", step="已停止")
                    return
                sym = st["symbol"]
                try:
                    daily = _load_daily(sym, fetch_start, fetch_end, short_fetch=False)
                    if daily is None or len(daily) < MIN_LISTING_DAYS:
                        continue
                    # 剔除回测起点前仍未上市的股票
                    if daily["date"].iloc[0] > pd.Timestamp(start):
                        continue
                    weekly = _to_weekly(daily)
                    for fri in _fridays_between(start, end):
                        if _is_subnew(daily, fri):  # 入场当日仍为次新股则跳过 (Critical-2)
                            continue
                        ok, _ = _n_up(weekly, fri, weeks)
                        if not ok:
                            continue
                        fact = _simulate_hold(daily, fri)
                        if fact is None:
                            continue
                        fact["symbol"] = sym
                        fact["name"] = st["name"]
                        trades_by_entry.setdefault(fact["entry_date"], []).append(fact)
                except Exception as e:
                    log.debug("回测 %s 失败: %s", sym, e)
                if (i + 1) % 10 == 0 or i + 1 == total:
                    _set_status(_bt_status, step=f"扫描 {i+1}/{total}",
                                progress=int((i+1)/total*90))

            # 按入场日顺序模拟组合权益 (各批次不重叠: 周一买, 周五卖)
            equity = cap
            equity_curve = [{"date": start.strftime("%Y-%m-%d"), "equity": round(equity, 2)}]
            all_trades = []
            for entry_date in sorted(trades_by_entry.keys()):
                facts = trades_by_entry[entry_date]
                n = len(facts)
                per_stock = equity / n
                batch_pnl = 0.0
                for fact in facts:
                    r = _trade_return_pct(fact, per_stock)
                    pnl = per_stock * r
                    batch_pnl += pnl
                    all_trades.append({
                        "entry_date": entry_date,
                        "exit_date": fact["exit_date"],
                        "symbol": fact["symbol"],
                        "name": fact["name"],
                        "entry_price": fact["entry_price"],
                        "exit_price": fact["exit_price"],
                        "return_pct": round(r * 100, 2),
                        "reason": fact["reason"],
                    })
                equity += batch_pnl
                exit_date = max(f["exit_date"] for f in facts)
                equity_curve.append({"date": exit_date, "equity": round(equity, 2)})

            metrics = _compute_metrics(equity_curve, all_trades, cap)
            result = {
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "weeks": weeks,
                "initial_capital": cap,
                "final_capital": round(equity, 2),
                "universe_total": total,
                "metrics": metrics,
                "equity_curve": equity_curve,
                "trades": all_trades,
                "trade_count": len(all_trades),
                "generated_at": datetime.now().isoformat(),
            }
            tag = f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}_w{weeks}"
            out_path = os.path.join(WEEKLY_DIR, f"backtest_{tag}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            _set_status(_bt_status, status="done", step=f"完成, {len(all_trades)} 笔交易",
                        progress=100, result=result)
        except Exception as e:
            log.exception("周线回测失败")
            _set_status(_bt_status, status="error", step=str(e), progress=0)

    with _bt_lock:
        _bt_thread = threading.Thread(target=_run, daemon=True)
        _bt_thread.start()
    return {"ok": True, "message": "回测已启动"}


def stop_backtest():
    _bt_stop.set()
    return {"ok": True}


def _compute_metrics(equity_curve, trades, initial_capital):
    final = equity_curve[-1]["equity"] if equity_curve else initial_capital
    total_return = (final / initial_capital - 1) * 100 if initial_capital else 0.0

    # 年化: 按权益曲线覆盖天数
    days = 252
    if len(equity_curve) >= 2:
        d0 = pd.Timestamp(equity_curve[0]["date"])
        d1 = pd.Timestamp(equity_curve[-1]["date"])
        days = max((d1 - d0).days, 1)
    years = days / 365.25
    if years > 0 and final > 0:
        annual = ((final / initial_capital) ** (1 / years) - 1) * 100
    else:
        annual = 0.0

    # 最大回撤
    max_dd = 0.0
    peak = initial_capital
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

    # 夏普: 按批次收益率
    rets = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        cur = equity_curve[i]["equity"]
        if prev > 0:
            rets.append(cur / prev - 1)
    if rets and len(rets) > 1:
        mu = float(np.mean(rets))
        sd = float(np.std(rets, ddof=1))
        sharpe = (mu / sd) * (52 ** 0.5) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    # 胜率 / 盈亏比 / 平均每笔
    wins = [t for t in trades if t["return_pct"] > 0]
    losses = [t for t in trades if t["return_pct"] < 0]
    total_n = len(trades)
    win_rate = (len(wins) / total_n * 100) if total_n else 0.0
    gross_profit = sum(t["return_pct"] for t in wins)
    gross_loss = -sum(t["return_pct"] for t in losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float(gross_profit > 0)
    avg_return = (sum(t["return_pct"] for t in trades) / total_n) if total_n else 0.0

    return {
        "total_return_pct": round(total_return, 2),
        "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "total_trades": total_n,
        "avg_return_pct": round(avg_return, 2),
    }
