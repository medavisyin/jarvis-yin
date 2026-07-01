"""
Jarvis Stock Module — Right-Side Trading Scanner (右侧交易推荐).

与短期 scanner(左侧/抄底吸筹)互补：右侧交易的核心是"确认后跟进"——
等待主力资金由流出转为持续净流入，并伴随趋势/突破确认后再入场，
而非在下跌中抄底。

三层漏斗:
  Layer 1  全市场快筛    (~5000 → ~60)    活跃流动性 + 价格未极端
  Layer 2  资金反转+技术 (~60 → ~10)      主力由出转进 + 均线/放量确认
  Layer 3  LLM右侧判断   (~10 → 0-5)      右侧入场 verdict + 操作策略

入场确认条件（用户选定 Q3=C）: 主力资金由流出转为持续净流入。
"""
import os
import sys
import json
import re
import time
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import akshare as ak

log = logging.getLogger("right-side-scanner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

try:
    import config
    from fetch_market_data import fetch_daily_ohlcv
    from technical_analysis import load_ohlcv, compute_indicators
    import china_market_data as cmd
    import scan_cache
    from config import call_deepseek, OLLAMA_HOST, MODEL_USAGE, STOCK_REPORTS_ROOT, STOCK_PROXY
except ImportError:
    _base = os.path.dirname(os.path.abspath(__file__))
    if _base not in sys.path:
        sys.path.insert(0, _base)
    import config
    from fetch_market_data import fetch_daily_ohlcv
    from technical_analysis import load_ohlcv, compute_indicators
    import china_market_data as cmd
    import scan_cache
    from config import call_deepseek, OLLAMA_HOST, MODEL_USAGE, STOCK_REPORTS_ROOT, STOCK_PROXY

_PROXIES = {"http": STOCK_PROXY, "https": STOCK_PROXY} if STOCK_PROXY else None

TOP_N = 5
LAYER2_CAP = 60
LAYER3_CAP = 8
MIN_RIGHTSIDE_SCORE = 60

# 资金反转参数
REVERSAL_3D_NET_MIN = 0.0          # 3日主力净流入必须为正
REVERSAL_3D_PCT_MIN = 3.0          # 3日主力净占比 >= +3%（持续净流入强度）
REVERSAL_10D_NET_MAX = 0.0         # 10日主力净流入曾为负（前期流出）

# Globals persisted on sys to survive decorator re-imports.
if not hasattr(sys, "_rs_scan_lock"):
    sys._rs_scan_lock = threading.Lock()
if not hasattr(sys, "_rs_stop_event"):
    sys._rs_stop_event = threading.Event()
if not hasattr(sys, "_rs_scan_status"):
    sys._rs_scan_status = {
        "status": "idle",
        "progress": 0,
        "step": "",
        "started_at": "",
        "elapsed_ms": 0,
        "error": None,
        "results_count": 0,
    }
if not hasattr(sys, "_rs_scan_thread"):
    sys._rs_scan_thread = None

_scan_lock = sys._rs_scan_lock
_stop_event = sys._rs_stop_event
_scan_status = sys._rs_scan_status

RS_DATA_DIR = os.path.join(STOCK_REPORTS_ROOT, "data", "right_side_scan")
RS_REPORTS_DIR = os.path.join(STOCK_REPORTS_ROOT, "right_side_scan_reports")
os.makedirs(RS_DATA_DIR, exist_ok=True)
os.makedirs(RS_REPORTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_right_side_scan_status() -> dict:
    with _scan_lock:
        status_copy = _scan_status.copy()
    if status_copy["status"] == "running" and status_copy["started_at"]:
        try:
            start_t = datetime.strptime(status_copy["started_at"], "%Y-%m-%d %H:%M:%S")
            status_copy["elapsed_ms"] = int((datetime.now() - start_t).total_seconds() * 1000)
        except Exception:
            pass
    return status_copy


def start_right_side_scan(use_deepseek: bool = True) -> dict:
    global _scan_status
    log.info("start_right_side_scan called (use_deepseek=%s)", use_deepseek)
    with _scan_lock:
        if sys._rs_scan_thread is not None and sys._rs_scan_thread.is_alive():
            return {
                "ok": False,
                "error": "右侧交易扫描正在运行中...",
                "status": get_right_side_scan_status(),
            }
        _stop_event.clear()
        _scan_status.clear()
        _scan_status.update({
            "status": "running",
            "progress": 0,
            "step": "初始化右侧交易扫描器...",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_ms": 0,
            "error": None,
            "results_count": 0,
        })
        sys._rs_scan_thread = threading.Thread(
            target=_run_rs_scan_thread,
            args=(use_deepseek,),
            daemon=True,
            name="right-side-scanner",
        )
        sys._rs_scan_thread.start()
        return {"ok": True, "message": "右侧交易扫描已启动"}


def stop_right_side_scan() -> dict:
    _stop_event.set()
    return {"ok": True, "message": "已向右侧交易扫描线程发送停止信号"}


def get_latest_right_side_result() -> dict | None:
    if not os.path.exists(RS_DATA_DIR):
        return None
    files = [f for f in os.listdir(RS_DATA_DIR) if f.startswith("right_side_scan_") and f.endswith(".json")]
    if not files:
        return None
    files.sort(reverse=True)
    try:
        with open(os.path.join(RS_DATA_DIR, files[0]), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("加载最近右侧扫描结果失败: %s", e)
        return None


def list_right_side_scan_dates() -> list[str]:
    if not os.path.exists(RS_DATA_DIR):
        return []
    files = [f for f in os.listdir(RS_DATA_DIR) if f.startswith("right_side_scan_") and f.endswith(".json")]
    dates = sorted({f.replace("right_side_scan_", "").replace(".json", "") for f in files}, reverse=True)
    return dates


def get_right_side_result_by_date(date_str: str) -> dict | None:
    path = os.path.join(RS_DATA_DIR, f"right_side_scan_{date_str}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("加载 %s 右侧扫描结果失败: %s", date_str, e)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num_val(v):
    if v == "-" or v == "" or v is None:
        return None
    return v


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def _fetch_market_eastmoney_direct() -> pd.DataFrame:
    log.info("Layer 1: 东财极速行情API获取实时快照...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5500",
        "po": "1", "np": "1",
        "ut": "bd1d9dd10319470d11d3d66416f1c148",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:1 t:80",
        "fields": "f12,f14,f2,f3,f4,f5,f6,f8,f9,f15,f16,f17,f18,f20,f21",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15, proxies=_PROXIES)
    resp.raise_for_status()
    data = resp.json()
    diff = data.get("data", {}).get("diff", [])
    if not diff:
        raise ValueError("东财API返回空数据")
    rows = []
    for item in diff:
        code = str(item.get("f12", ""))
        if not code or not code.startswith(("60", "00", "30", "688", "43", "83")):
            continue
        rows.append({
            "代码": code,
            "名称": str(item.get("f14", "")),
            "最新价": _num_val(item.get("f2")),
            "涨跌幅": _num_val(item.get("f3")),
            "成交量": _num_val(item.get("f5")),
            "成交额": _num_val(item.get("f6")),
            "换手率": _num_val(item.get("f8")),
            "市盈率-动态": _num_val(item.get("f9")),
            "总市值": _num_val(item.get("f20")),
            "流通市值": _num_val(item.get("f21")),
        })
    df = pd.DataFrame(rows)
    for col in ["最新价", "涨跌幅", "换手率", "成交额", "市盈率-动态", "总市值"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log.info("东财极速行情API: 成功采集 %d 只 A 股实时行情", len(df))
    return df


def _fetch_market_sina_pagination() -> pd.DataFrame:
    log.info("Layer 1: 新浪市场中心分页备用API...")
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    all_rows = []
    page = 1
    while True:
        params = {"page": str(page), "num": "80", "sort": "changepercent", "asc": "0", "node": "hs_a", "symbol": ""}
        items = None
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=12, proxies=_PROXIES)
                if resp.status_code == 200:
                    items = resp.json()
                    break
                time.sleep(1.5 + attempt * 2.0)
            except Exception:
                time.sleep(1.5)
        if items is None or not items:
            break
        for item in items:
            all_rows.append({
                "代码": str(item.get("code", "")),
                "名称": str(item.get("name", "")),
                "最新价": item.get("trade"),
                "涨跌幅": item.get("changepercent"),
                "成交额": item.get("amount"),
                "换手率": item.get("turnoverratio"),
                "市盈率-动态": item.get("per"),
                "总市值": item.get("mktcap"),
            })
        page += 1
        if len(items) < 80 or page > 80:
            break
        time.sleep(0.3)
    if not all_rows:
        raise ValueError("新浪分页API未采集到行情数据")
    df = pd.DataFrame(all_rows)
    for col in ["最新价", "涨跌幅", "换手率", "成交额", "市盈率-动态", "总市值"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log.info("新浪备用API: 成功采集 %d 只股票", len(df))
    return df


# ---------------------------------------------------------------------------
# Scan thread
# ---------------------------------------------------------------------------
def _run_rs_scan_thread(use_deepseek: bool):
    try:
        _run_rs_scan_inner(use_deepseek, market_df=_shared_market_df)
    except Exception as e:
        log.exception("右侧扫描线程发生未捕获异常:")
        with _scan_lock:
            _scan_status["status"] = "failed"
            _scan_status["error"] = str(e)


# Shared market snapshot for unified scanner (None = fetch normally)
_shared_market_df = None


def set_shared_market_df(df):
    global _shared_market_df
    _shared_market_df = df


def clear_shared_market_df():
    global _shared_market_df
    _shared_market_df = None


def _run_rs_scan_inner(use_deepseek: bool, market_df=None):
    global _scan_status
    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    # --- Layer 1 ---------------------------------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 1: 获取全市场实时行情并执行活跃度过滤..."
        _scan_status["progress"] = 10
    log.info("Layer 1: 获取全市场实时快照...")

    df = market_df
    if df is None:
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as e:
            log.warning("akshare 全市场行情失败: %s, 尝试东财直连...", e)

    if df is None or df.empty:
        try:
            df = _fetch_market_eastmoney_direct()
        except Exception as e2:
            log.warning("东财直连失败: %s, 尝试新浪分页...", e2)
            try:
                df = _fetch_market_sina_pagination()
            except Exception as e3:
                with _scan_lock:
                    _scan_status["status"] = "failed"
                    _scan_status["error"] = f"多路由实时行情采集均失败: {e3}"
                return

    if df is None or df.empty:
        with _scan_lock:
            _scan_status["status"] = "failed"
            _scan_status["error"] = "实时行情数据为空"
        return

    # 右侧交易 Layer 1 过滤：活跃流动性 + 价格未极端（不要求低位，允许右侧追高）
    # 1. 排除 ST/退市
    # 2. 主板(60/00)或创业板(30)
    # 3. 价格 3~100 元
    # 4. 今日涨跌幅 -1% ~ +7%：允许温和上行（趋势启动），排除涨停板（T+1追高风险）与大跌股
    # 5. 换手率 >= 1.5%（活跃）
    # 6. 成交额 >= 3000万（流动性）
    # 7. 总市值 20亿~500亿
    #    注意单位：akshare `stock_zh_a_spot_em` 的 总市值 单位是【万元】，
    #    东财直连可能返回【元】。先归一化到元再比较，否则万元单位下
    #    `between(2e9, 50e9)` 会把所有股票筛掉（2e9万元=20万亿）。
    try:
        _mcap = df["总市值"].apply(lambda x: _safe_float(x) or 0)
        if _mcap.max() < 1e10:
            # 万元 → 元 (最大A股市值约2e12元=2e8万元，1e10可区分两种单位)
            _mcap = _mcap * 1e4
        mask = (
            df["名称"].apply(lambda x: "ST" not in str(x) and "退" not in str(x))
            & df["代码"].apply(lambda x: str(x).startswith(("60", "00", "30")))
            & df["最新价"].between(3, 100)
            & df["涨跌幅"].between(-1, 7)
            & (df["换手率"].apply(lambda x: _safe_float(x) or 0) >= 1.5)
            & (df["成交额"].apply(lambda x: _safe_float(x) or 0) >= 30_000_000)
            & (_mcap.between(2e9, 50e9))
        )
        candidates_df = df[mask].copy()
    except Exception as e:
        with _scan_lock:
            _scan_status["status"] = "failed"
            _scan_status["error"] = f"Layer 1 筛选异常: {e}"
        return

    log.info("Layer 1: 首层筛选完毕，共 %d 只候选", len(candidates_df))
    if candidates_df.empty:
        _save_results_empty(date_str)
        return

    candidates = []
    for _, row in candidates_df.iterrows():
        candidates.append({
            "symbol": str(row["代码"]),
            "name": str(row["名称"]),
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]),
            "turnover_rate": float(row["换手率"]),
            "amount": float(row["成交额"]),
            "market_cap": float(row["总市值"]),
            "pe": float(row["市盈率-动态"]) if pd.notna(row.get("市盈率-动态")) else None,
        })

    # 控制 Layer 2 规模：按换手率×成交额排序取前 LAYER2_CAP
    if len(candidates) > LAYER2_CAP:
        candidates.sort(key=lambda x: x["turnover_rate"] * (x["amount"] / 1e8), reverse=True)
        candidates = candidates[:LAYER2_CAP]

    # --- Layer 2: 资金反转 + 技术确认 -----------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 2: 主力资金反转 + 趋势/放量确认分析..."
        _scan_status["progress"] = 30
    log.info("Layer 2: 对 %d 只候选执行资金反转与技术确认...", len(candidates))

    enriched = []
    enriched_lock = threading.Lock()

    def analyze_single(stock_dict):
        if _stop_event.is_set():
            return
        sym = stock_dict["symbol"]
        ff_signals = {}
        reversal_ok = False
        tech_score = 50
        price_above_ma5 = False
        near_ma20 = False
        ma20_val = None
        rsi_val = None
        volume_ratio = None

        # 技术面：MA5/MA20、RSI、量比
        try:
            if not scan_cache.ohlcv_done(sym):
                fetch_daily_ohlcv(sym)
                scan_cache.mark_ohlcv(sym)
            hist_df = load_ohlcv(sym)
            if hist_df is not None and len(hist_df) >= 20:
                hist_df = compute_indicators(hist_df)
                last_row = hist_df.iloc[-1]
                ma5 = last_row.get("MA5")
                ma20 = last_row.get("MA20")
                curr = stock_dict["price"]
                if ma5 and curr > ma5:
                    tech_score += 15
                    price_above_ma5 = True
                if ma20:
                    ma20_val = float(ma20)
                    if curr > ma20:
                        tech_score += 15
                    elif ma20 and abs(curr - ma20) / ma20 < 0.03:
                        tech_score += 8  # 逼近 MA20，待突破
                        near_ma20 = True
                if ma5 and ma20 and ma5 > ma20:
                    tech_score += 10
                rsi = last_row.get("RSI")
                if rsi is not None:
                    rsi_val = float(rsi)
                    if 50 <= rsi <= 70:
                        tech_score += 10
                    elif rsi > 80:
                        tech_score -= 10  # 超买预警
                # 量比：近5日均量
                if "volume" in hist_df.columns and len(hist_df) >= 6:
                    recent_vol = pd.to_numeric(hist_df["volume"].tail(6).head(5), errors="coerce").mean()
                    last_vol = pd.to_numeric(hist_df["volume"].iloc[-1], errors="coerce")
                    if recent_vol and recent_vol > 0 and last_vol:
                        volume_ratio = float(last_vol / recent_vol)
                        if volume_ratio >= 1.5:
                            tech_score += 10
                tech_score = max(0, min(100, tech_score))
        except Exception as e:
            log.debug("  %s 技术面分析异常: %s", sym, e)

        # 资金面：核心右侧信号 —— 由流出转为持续净流入
        try:
            cached_ff = scan_cache.get_ff(sym)
            if cached_ff is not None:
                ff = cached_ff
            else:
                ff = cmd.stock_fund_flow_signals(sym)
                scan_cache.set_ff(sym, ff)
            if ff and ff.get("data_days", 0) >= 3:
                ff_signals = ff
                main_net_3d = float(ff.get("main_net_3d", 0) or 0)
                main_net_10d = float(ff.get("main_net_10d", 0) or 0)
                main_pct_3d = float(ff.get("main_pct_3d", 0) or 0)
                # 反转条件：前期10日流出 + 近3日转正且强度达标
                reversal_ok = (
                    main_net_10d <= REVERSAL_10D_NET_MAX
                    and main_net_3d >= REVERSAL_3D_NET_MIN
                    and main_pct_3d >= REVERSAL_3D_PCT_MIN
                )
        except Exception as e:
            log.debug("  %s 资金流向分析异常: %s", sym, e)

        # 资金反转评分
        ff_score = 50
        if ff_signals:
            phase = ff_signals.get("smart_money_phase", "无信号")
            main_net_3d = float(ff_signals.get("main_net_3d", 0) or 0)
            main_pct_3d = float(ff_signals.get("main_pct_3d", 0) or 0)
            if reversal_ok:
                ff_score = 75 + min(main_pct_3d * 1.5, 20)  # 反转强度越高分越高
            elif phase == "布局期":
                ff_score = 70
            elif main_net_3d > 0:
                ff_score = 60
            elif phase == "出货期" or main_net_3d < 0:
                ff_score = 25  # 仍在流出，右侧未成立
            ff_score = max(0, min(100, ff_score))

        # 复合得分：右侧重视资金反转(50%) + 技术确认(35%) + 活跃度(15%)
        tr_score = min(100, stock_dict["turnover_rate"] * 10 + 30)
        vr_score = min(100, (volume_ratio or 1.0) * 20 + 30)
        composite = ff_score * 0.50 + tech_score * 0.35 + (tr_score + vr_score) / 2 * 0.15
        if reversal_ok and price_above_ma5:
            composite += 5  # 反转+趋势确认 bonus

        stock_dict.update({
            "tech_score": round(tech_score, 1),
            "ff_score": round(ff_score, 1),
            "ff_signals": ff_signals,
            "fund_reversal": reversal_ok,
            "price_above_ma5": price_above_ma5,
            "near_ma20": near_ma20,
            "ma20": round(ma20_val, 2) if ma20_val else None,
            "rsi": round(rsi_val, 1) if rsi_val else None,
            "volume_ratio": round(volume_ratio, 2) if volume_ratio else None,
            "composite_score": round(composite, 1),
        })
        with enriched_lock:
            enriched.append(stock_dict)

    max_workers = min(8, len(candidates)) if candidates else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_single, s): s for s in candidates}
        for future in as_completed(futures):
            if _stop_event.is_set():
                break
            try:
                future.result(timeout=20)
            except Exception as e:
                log.warning("Layer 2 分析异常: %s", e)

    if _stop_event.is_set():
        with _scan_lock:
            _scan_status["status"] = "idle"
            _scan_status["step"] = "扫描已终止"
        return

    # 右侧硬条件：必须资金反转成立（fund_reversal=True），否则不进入 Layer 3
    reversed_only = [s for s in enriched if s.get("fund_reversal")]
    log.info("Layer 2: 资金反转成立 %d / %d 只", len(reversed_only), len(enriched))

    if not reversed_only:
        _save_results_empty(date_str, enriched_count=len(enriched))
        return

    reversed_only.sort(key=lambda x: x["composite_score"], reverse=True)
    top = reversed_only[:LAYER3_CAP]

    log.info("Layer 2: 进入 Layer 3 的右侧候选:")
    for i, st in enumerate(top, 1):
        log.info("  %d. %s (%s) 综合:%.1f 资金反转:%s 3日净流入:%.2e",
                 i, st["name"], st["symbol"], st["composite_score"], st["fund_reversal"],
                 float(st.get("ff_signals", {}).get("main_net_3d", 0) or 0))

    # --- Layer 3: DeepSeek 右侧判断 -------------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 3: 呼叫 DeepSeek 执行右侧交易入场评判..."
        _scan_status["progress"] = 60

    system_prompt = (
        "你是一位顶级A股量化分析师，专注于**右侧交易**选股与买入判断（与左侧抄底吸筹互补）。\n\n"
        "右侧交易核心理念：不预测底，等待**确认后跟进**。当主力资金由流出转为持续净流入，"
        "并伴随趋势/突破确认后，在确认信号出现时入场，而非在下跌中抄底。\n\n"
        "右侧入场判定准则（必须全部考量）：\n"
        "1. **资金面右侧确认（核心）**：10日主力曾净流出但近3日转为持续净流入且3日净占比>=+3%，"
        "表明主力态度由派发转为回补/吸筹，是右侧入场的根本依据。\n"
        "2. **趋势确认**：价格站上MA5，逼近或突破MA20，均线有望转多头排列；"
        "若已放量突破关键阻力位更佳。\n"
        "3. **量能配合**：近期成交量放大（量比>=1.5），反弹有量、回调缩量为佳。\n"
        "4. **允许追高但严控风险**：右侧入场不要求低位，允许在突破位/确认位买入，"
        "但因A股T+1，必须设置明确止损（如跌破MA5或突破位-3%）；接近涨停板不追。\n"
        "5. **持有周期与目标**：2周到2、3个月内持有，预期盈利10%以上。\n"
        "6. **基本面底线**：盈利能力与财务健康至少中等，规避绩差/高负债股。\n\n"
        "判断纪律：\n"
        "- 若资金反转信号不成立、或趋势未确认、或风险>收益，必须判定\"不买入\"。\n"
        "- 宁可错过确认前的涨幅，不可在信号未成立时提前埋伏（那是左侧的事）。\n\n"
        "输出要求：只输出一个JSON对象，不要任何其他文字或```json围栏：\n"
        '{"verdict":"买入","score":75,"reason":"右侧入场核心理由3-5条（必须论证资金反转+趋势确认）","risk":"主要风险","buy_low":9.50,"buy_high":10.00,"stop_loss":9.10,"target_price":10.80,"strategy":"右侧入场操作路径：确认信号、分批仓位、止损、止盈","entry_type":"右侧"}\n'
        "verdict 只能是 \"买入\" 或 \"不买入\"。score 0-100。"
        "buy_low/buy_high 为建议买入价区间（参考当前价，允许在突破位追高）。"
        "stop_loss 为严格止损价。target_price 为2-3个月目标价（+10%以上）。"
        "entry_type 固定为 \"右侧\"。"
    )

    final_picks = []
    picks_lock = threading.Lock()

    def evaluate_l3(stock):
        if _stop_event.is_set():
            return
        with picks_lock:
            if len(final_picks) >= TOP_N:
                return
        sym = stock["symbol"]
        log.info("Layer 3: 右侧评估 %s (%s)...", sym, stock["name"])
        user_prompt = _build_rs_prompt(stock)
        try:
            if use_deepseek:
                result = call_deepseek(system_prompt, user_prompt, max_tokens=1200, reasoning_effort="medium")
                if result["ok"]:
                    parsed = _parse_rs_json(result["content"], stock)
                    parsed["judged_by"] = "deepseek"
                    parsed["deepseek_reasoning"] = result.get("reasoning_content", "")
                    if parsed.get("verdict") == "买入" and parsed.get("final_score", 0) >= MIN_RIGHTSIDE_SCORE:
                        with picks_lock:
                            if len(final_picks) < TOP_N:
                                final_picks.append(parsed)
                else:
                    log.warning("DeepSeek 失败: %s, 启用本地LLM", result.get("error"))
                    parsed = _call_local_rs_judge(system_prompt, user_prompt, stock)
                    if parsed.get("verdict") == "买入" and parsed.get("final_score", 0) >= MIN_RIGHTSIDE_SCORE:
                        with picks_lock:
                            if len(final_picks) < TOP_N:
                                final_picks.append(parsed)
            else:
                parsed = _call_local_rs_judge(system_prompt, user_prompt, stock)
                if parsed.get("verdict") == "买入" and parsed.get("final_score", 0) >= MIN_RIGHTSIDE_SCORE:
                    with picks_lock:
                        if len(final_picks) < TOP_N:
                            final_picks.append(parsed)
        except Exception as e:
            log.error("Layer 3 评估 %s 失败: %s", sym, e)

    max_l3 = min(3, len(top)) if top else 1
    with ThreadPoolExecutor(max_workers=max_l3) as executor:
        futures_l3 = [executor.submit(evaluate_l3, s) for s in top]
        for future in as_completed(futures_l3):
            if _stop_event.is_set():
                break
            try:
                future.result(timeout=40)
            except Exception as e:
                log.warning("Layer 3 任务异常: %s", e)

    if _stop_event.is_set():
        with _scan_lock:
            _scan_status["status"] = "idle"
            _scan_status["step"] = "扫描已终止"
        return

    final_picks.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    final_picks = final_picks[:TOP_N]

    with _scan_lock:
        _scan_status["step"] = "保存右侧扫描结果并生成报告..."
        _scan_status["progress"] = 90
    _save_rs_results(final_picks, top, date_str, start_time)

    with _scan_lock:
        _scan_status["status"] = "completed"
        _scan_status["progress"] = 100
        _scan_status["step"] = "右侧交易扫描完成！"
        _scan_status["results_count"] = len(final_picks)
    log.info("右侧交易扫描完成，共选出 %d 只右侧推荐", len(final_picks))


# ---------------------------------------------------------------------------
# Prompt / parse / local fallback
# ---------------------------------------------------------------------------
def _build_rs_prompt(stock: dict) -> str:
    ff = stock.get("ff_signals", {}) or {}
    if ff:
        ff_desc = (
            f"- 3日主力净流入: {float(ff.get('main_net_3d',0) or 0)/1e8:.2f}亿\n"
            f"- 10日主力净流入: {float(ff.get('main_net_10d',0) or 0)/1e8:.2f}亿\n"
            f"- 3日主力净占比: {float(ff.get('main_pct_3d',0) or 0):.2f}%\n"
            f"- 超大单占比: {ff.get('super_large_ratio', 'N/A')}\n"
            f"- 聪明钱阶段: {ff.get('smart_money_phase', '无信号')}\n"
            f"- 吸筹评分: {ff.get('accumulation_score', 0)}/100"
        )
    else:
        ff_desc = "无主力资金数据"

    reversal_str = "是（10日曾流出→3日转正且强度达标）" if stock.get("fund_reversal") else "否"
    trend_str = []
    if stock.get("price_above_ma5"):
        trend_str.append("价格站上MA5")
    if stock.get("ma20") is not None:
        trend_str.append(f"逼近/突破MA20(¥{stock['ma20']})")
    trend_desc = "、".join(trend_str) if trend_str else "趋势未确认"

    return f"""请评估这只股票是否符合**右侧交易**买入要求（确认后跟进，非抄底）。

当前数据：
- 股票: {stock['name']} ({stock['symbol']})
- 最新价: ¥{stock['price']}
- 今日涨跌幅: {stock['change_pct']}%
- 换手率: {stock['turnover_rate']}%
- 成交额: {stock['amount']/1e8:.2f}亿
- 动态PE: {stock.get('pe', 'N/A')}
- 总市值: {stock['market_cap']/1e8:.1f}亿
- 技术特征:
  - 趋势确认: {trend_desc}
  - RSI: {stock.get('rsi', 'N/A')}
  - 量比(相对5日均量): {stock.get('volume_ratio', 'N/A')}
- 主力资金特征（右侧核心）:
  {ff_desc}
  - 资金反转成立: {reversal_str}

请基于"资金由流出转为持续净流入 + 趋势/突破确认"的右侧逻辑做出判断（"买入"或"不买入"），
并给出右侧入场操作策略（确认信号、分批仓位、严格止损、2-3个月目标价）。
只输出JSON对象，不要任何外围文字或围栏。"""


def _call_local_rs_judge(system_prompt: str, user_prompt: str, stock: dict) -> dict:
    model = MODEL_USAGE.get("prediction_reasoning", "qwen3.5:4b")
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.3, "num_predict": 600},
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        return _parse_rs_json(raw, stock)
    except Exception as e:
        log.warning("本地 LLM 右侧评分 %s 失败: %s", stock["symbol"], e)
        stock["verdict"] = "不买入"
        stock["final_score"] = stock.get("composite_score", 50)
        stock["reasoning"] = "本地LLM不可用"
        stock["entry_type"] = "右侧"
        return stock


def _parse_rs_json(raw: str, stock: dict) -> dict:
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_str = text[start:end].replace("'", '"')
        json_str = re.sub(r",\s*}", "}", json_str)
        try:
            parsed = json.loads(json_str)
            verdict_raw = str(parsed.get("verdict", "")).strip()
            stock["verdict"] = "买入" if "买入" in verdict_raw and "不" not in verdict_raw else "不买入"
            stock["final_score"] = float(parsed.get("score", stock.get("composite_score", 50)))
            stock["reasoning"] = parsed.get("reason", "")
            stock["risk"] = parsed.get("risk", "")
            stock["buy_low"] = _safe_float(parsed.get("buy_low"))
            stock["buy_high"] = _safe_float(parsed.get("buy_high"))
            stock["stop_loss"] = _safe_float(parsed.get("stop_loss"))
            stock["target_price"] = _safe_float(parsed.get("target_price"))
            stock["strategy"] = parsed.get("strategy", "")
            stock["entry_type"] = "右侧"
            return stock
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("右侧 LLM JSON 解析失败: %s", e)
    stock["verdict"] = "不买入"
    stock["final_score"] = stock.get("composite_score", 50)
    stock["reasoning"] = "LLM输出解析失败"
    stock["entry_type"] = "右侧"
    return stock


# ---------------------------------------------------------------------------
# Save / report
# ---------------------------------------------------------------------------
def _save_results_empty(date_str: str, enriched_count: int = 0):
    global _scan_status
    with _scan_lock:
        started_at = _scan_status["started_at"]
    data = {
        "scan_type": "right_side",
        "date": date_str,
        "started_at": started_at,
        "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "picks": [],
        "all_candidates_count": enriched_count,
        "message": "右侧扫描完毕，今日无资金反转+趋势确认的右侧标的。",
    }
    path = os.path.join(RS_DATA_DIR, f"right_side_scan_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _generate_rs_markdown_report([], [], date_str, data)
    with _scan_lock:
        _scan_status["status"] = "completed"
        _scan_status["progress"] = 100
        _scan_status["step"] = "右侧扫描结束，无符合条件的右侧推荐标的。"


def _save_rs_results(picks: list[dict], all_cand: list[dict], date_str: str, start_time: float):
    global _scan_status
    elapsed = int((time.time() - start_time) * 1000)
    with _scan_lock:
        started_at = _scan_status["started_at"]
    data = {
        "scan_type": "right_side",
        "date": date_str,
        "started_at": started_at,
        "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_ms": elapsed,
        "picks": picks,
        "all_candidates_count": len(all_cand),
    }
    path = os.path.join(RS_DATA_DIR, f"right_side_scan_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _generate_rs_markdown_report(picks, all_cand, date_str, data)


def _generate_rs_markdown_report(picks: list[dict], all_cand: list[dict], date_str: str, meta: dict):
    lines = [
        f"# AI股票推荐报告(右侧交易) — {date_str}",
        "",
        f"**扫描启动时间**: {meta.get('started_at', 'N/A')}",
        f"**分析截止时间**: {meta.get('ended_at', 'N/A')}",
        "**策略定位**: 右侧交易（确认后跟进：主力资金由流出转为持续净流入 + 趋势/突破确认后入场）",
        "**目标周期**: 短期 (2周到2、3个月内持有)",
        "**预期盈利**: 10%以上",
        f"**资金反转候选**: {meta.get('all_candidates_count', 0)} 只",
        f"**终极右侧推荐**: {len(picks)} 只",
        "",
        "---",
        "",
    ]

    if not picks:
        lines.extend([
            "## 本次扫描结果：今日暂无右侧推荐",
            "",
            "经全市场资金反转信号筛选与 AI 右侧模型评判，**今日没有同时满足：**",
            "- 主力资金由10日流出转为3日持续净流入（3日净占比>=+3%）",
            "- 价格站上MA5并逼近/突破MA20（趋势确认）",
            "- 量能配合且风险可控 等条件的右侧标的。",
            "",
            "**右侧交易讲究耐心等待确认信号。无信号即不入场，是右侧交易的纪律。**",
            "",
        ])
    else:
        lines.extend([
            "## 右侧推荐买入 (最多5只)",
            "以下股票出现**主力资金由流出转为持续净流入**的右侧信号，并伴随**趋势/突破确认**，"
            "符合“确认后跟进”的右侧交易入场条件。",
            "",
        ])
        for i, pick in enumerate(picks, 1):
            judged = pick.get("judged_by", "local")
            judge_tag = "DeepSeek 右侧决策" if judged == "deepseek" else "本地LLM"
            ff = pick.get("ff_signals", {}) or {}
            lines.extend([
                f"### {i}. {pick['name']} ({pick['symbol']}) — {judge_tag}",
                "",
                f"- **操作指令**: **买入** (右侧交易评级)",
                f"- **综合推荐指数**: {pick.get('final_score', 0):.1f}/100",
                f"- **入场类型**: {pick.get('entry_type', '右侧')}",
                f"- **当前价**: ¥{pick['price']}",
                f"- **建议买入区间**: {_buy_range_str(pick)}",
                f"- **严格止损价**: ¥{pick.get('stop_loss', 'N/A')}",
                f"- **2-3个月目标价**: ¥{pick.get('target_price', 'N/A')}",
                f"- **资金反转信号**: 3日主力净流入 {float(ff.get('main_net_3d',0) or 0)/1e8:.2f}亿 / 3日净占比 {float(ff.get('main_pct_3d',0) or 0):.2f}%",
                f"- **趋势确认**: {'站上MA5' if pick.get('price_above_ma5') else '未确认'} / MA20={pick.get('ma20','N/A')}",
                f"- **推荐理由**: {pick.get('reasoning', 'N/A')}",
                f"- **操作策略**: {pick.get('strategy', 'N/A')}",
                f"- **主要风险**: {pick.get('risk', 'N/A')}",
                "",
            ])

    if all_cand:
        lines.extend([
            "---",
            "## 资金反转候选池评分一览",
            "以下为通过资金反转硬条件、进入 Layer 3 评估的候选（按综合得分排序）：",
            "",
            "| 排名 | 代码 | 名称 | 综合分 | 资金评分 | 技术评分 | 3日净流入(亿) | 趋势确认 |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for r, st in enumerate(all_cand[:10], 1):
            ff = st.get("ff_signals", {}) or {}
            mn3 = float(ff.get("main_net_3d", 0) or 0) / 1e8
            trend = "站上MA5" if st.get("price_above_ma5") else "未确认"
            lines.append(
                f"| {r} | {st['symbol']} | {st['name']} | {st['composite_score']} | "
                f"{st['ff_score']} | {st['tech_score']} | {mn3:.2f} | {trend} |"
            )

    lines.extend([
        "",
        "---",
        f"*本报告由 Jarvis AI 右侧交易扫描系统于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 自动生成*",
        "*免责声明: 右侧交易需严格止损纪律，本报告不构成绝对投资承诺。*",
    ])

    report_path = os.path.join(RS_REPORTS_DIR, f"right_side_scan_report_{date_str}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info("右侧交易报告已写入: %s", report_path)

    try:
        _index_rs_report_to_rag(report_path, date_str)
    except Exception as e:
        log.error("右侧报告 RAG 索引失败: %s", e)


def _buy_range_str(pick: dict) -> str:
    lo = pick.get("buy_low")
    hi = pick.get("buy_high")
    if lo and hi:
        return f"¥{lo} ~ ¥{hi}"
    if lo:
        return f"¥{lo} 起"
    return "N/A"


def _index_rs_report_to_rag(report_path: str, date_str: str):
    try:
        from scanner import _index_scan_report_to_rag
        _index_scan_report_to_rag(report_path, date_str)
        log.info("右侧报告已索引至 Qdrant RAG。")
    except Exception as e:
        log.warning("调用 scanner RAG 索引失败: %s", e)


if __name__ == "__main__":
    print("Starting right-side scan test...")
    start_right_side_scan(use_deepseek=False)
    while True:
        st = get_right_side_scan_status()
        print(f"Status: {st['status']} | {st['progress']}% | {st['step']}")
        if st["status"] in ("completed", "failed"):
            break
        time.sleep(3)
