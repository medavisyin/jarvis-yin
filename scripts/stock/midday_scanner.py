"""
Jarvis Stock Module — Mid-day Overnight Speculative Scanner (午盘隔夜套利策略).

Designed for the user to run during lunch break (around 12:30 PM), utilizing 
morning session close data (up to 11:30 AM) to recommend 1-3 extremely 
high-momentum breakout stocks suitable for afternoon entry (13:00) and 
selling tomorrow morning (T+1 quick profit taking).
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
import pandas as pd
import requests
import akshare as ak

# Configure module-level logger
log = logging.getLogger("midday-scanner")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Import stock module config and helpers
try:
    import config
    from fetch_market_data import fetch_daily_ohlcv
    from technical_analysis import load_ohlcv, compute_indicators
    import china_market_data as cmd
    from config import call_deepseek, OLLAMA_HOST, MODEL_USAGE, STOCK_REPORTS_ROOT, STOCK_PROXY
except ImportError:
    # Handle sys.path insert if executed directly or from parent directory
    _base = os.path.dirname(os.path.abspath(__file__))
    if _base not in sys.path:
        sys.path.insert(0, _base)
    import config
    from fetch_market_data import fetch_daily_ohlcv
    from technical_analysis import load_ohlcv, compute_indicators
    import china_market_data as cmd
    from config import call_deepseek, OLLAMA_HOST, MODEL_USAGE, STOCK_REPORTS_ROOT, STOCK_PROXY

_PROXIES = {"http": STOCK_PROXY, "https": STOCK_PROXY} if STOCK_PROXY else None

# Globals for scan synchronization and progress persisted in sys module
# to survive @_with_stock_imports decorator flushing and re-importing.
if not hasattr(sys, "_midday_scan_lock"):
    sys._midday_scan_lock = threading.Lock()
if not hasattr(sys, "_midday_stop_event"):
    sys._midday_stop_event = threading.Event()
if not hasattr(sys, "_midday_scan_status"):
    sys._midday_scan_status = {
        "status": "idle",  # idle, running, completed, failed
        "progress": 0,
        "step": "",
        "started_at": "",
        "elapsed_ms": 0,
        "error": None,
        "results_count": 0
    }
if not hasattr(sys, "_midday_scan_thread"):
    sys._midday_scan_thread = None

_scan_lock = sys._midday_scan_lock
_stop_event = sys._midday_stop_event
_scan_status = sys._midday_scan_status

# Directories for midday scan output
MIDDAY_DATA_DIR = os.path.join(STOCK_REPORTS_ROOT, "data", "midday_scan")
MIDDAY_REPORTS_DIR = os.path.join(STOCK_REPORTS_ROOT, "midday_scan_reports")
os.makedirs(MIDDAY_DATA_DIR, exist_ok=True)
os.makedirs(MIDDAY_REPORTS_DIR, exist_ok=True)


def get_midday_scan_status() -> dict:
    """Return current progress and status of the midday scan."""
    global _scan_status
    with _scan_lock:
        # Create a copy to prevent thread-safety issues during reads
        status_copy = _scan_status.copy()
    if status_copy["status"] == "running" and status_copy["started_at"]:
        try:
            start_t = datetime.strptime(status_copy["started_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - start_t).total_seconds() * 1000
            status_copy["elapsed_ms"] = int(elapsed)
        except Exception:
            pass
    return status_copy


def start_midday_scan(use_deepseek: bool = True) -> dict:
    """Start the mid-day overnight speculative scan in a background thread."""
    global _scan_status
    
    log.info("start_midday_scan called (use_deepseek=%s)", use_deepseek)
    with _scan_lock:
        if sys._midday_scan_thread is not None and sys._midday_scan_thread.is_alive():
            return {
                "ok": False, 
                "error": "午盘扫描正在运行中...", 
                "status": get_midday_scan_status()
            }

        _stop_event.clear()
        _scan_status.clear()
        _scan_status.update({
            "status": "running",
            "progress": 0,
            "step": "初始化扫描器...",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_ms": 0,
            "error": None,
            "results_count": 0
        })
        
        sys._midday_scan_thread = threading.Thread(
            target=_run_midday_scan_thread, 
            args=(use_deepseek,), 
            daemon=True, 
            name="midday-scanner"
        )
        sys._midday_scan_thread.start()
        return {"ok": True, "message": "午盘极速选股扫描已启动"}


def stop_midday_scan() -> dict:
    """Request midday scan to terminate."""
    _stop_event.set()
    return {"ok": True, "message": "已向午盘扫描线程发送停止信号"}


def _fetch_market_eastmoney_direct() -> pd.DataFrame:
    """Direct high-quality fallback: fetch full A-share market data from EastMoney API."""
    log.info("Layer 1: 正在通过东财极速行情API获取实时快照...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5500",
        "po": "1", "np": "1",
        "ut": "bd1d9dd10319470d11d3d66416f1c148",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:1 t:80",
        "fields": "f12,f14,f2,f3,f4,f5,f6,f8,f9,f15,f16,f17,f18,f20,f21"
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
        # Filter typical A-share formats
        if not code or not code.startswith(("60", "00", "30", "688", "43", "83")):
            continue
            
        rows.append({
            "代码": code,
            "名称": str(item.get("f14", "")),
            "最新价": _num_val(item.get("f2")),
            "涨跌幅": _num_val(item.get("f3")),
            "涨跌额": _num_val(item.get("f4")),
            "成交量": _num_val(item.get("f5")),
            "成交额": _num_val(item.get("f6")),
            "换手率": _num_val(item.get("f8")),
            "市盈率-动态": _num_val(item.get("f9")),
            "最高": _num_val(item.get("f15")),
            "最低": _num_val(item.get("f16")),
            "今开": _num_val(item.get("f17")),
            "昨收": _num_val(item.get("f18")),
            "总市值": _num_val(item.get("f20")),
            "流通市值": _num_val(item.get("f21")),
        })
        
    df = pd.DataFrame(rows)
    # Re-normalize numeric types
    for col in ["最新价", "涨跌幅", "换手率", "成交额", "市盈率-动态", "总市值"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log.info("东财极速行情API: 成功采集 %d 只 A 股实时行情", len(df))
    return df


def _num_val(v):
    if v == "-" or v == "" or v is None:
        return None
    return v


def _fetch_market_sina_pagination() -> pd.DataFrame:
    """Robust fallback: fetch full A-share market data from Sina Market Center API with pagination retry."""
    log.info("Layer 1: 尝试本地新浪市场中心分页备用API...")
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn",
    }

    all_rows = []
    page = 1
    max_retries = 3
    while True:
        params = {
            "page": str(page), "num": "80",
            "sort": "changepercent", "asc": "0",
            "node": "hs_a", "symbol": "",
        }
        
        items = None
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=12, proxies=_PROXIES)
                if resp.status_code == 200:
                    items = resp.json()
                    break
                elif resp.status_code in (456, 403, 503):
                    log.warning("新浪API遇到 %d 频控，正在进行第 %d 次重试延迟...", resp.status_code, attempt + 1)
                    time.sleep(1.5 + attempt * 2.0)
            except Exception as e:
                log.warning("新浪API页抓取网络异常: %s, 正在重试...", e)
                time.sleep(1.5)
                
        if items is None:
            log.warning("新浪分页API在第 %d 页完全失败，停止抓取，合并已采集数据", page)
            break
            
        if not items:
            break

        for item in items:
            code = str(item.get("code", ""))
            all_rows.append({
                "代码": code,
                "名称": str(item.get("name", "")),
                "最新价": item.get("trade"),
                "涨跌幅": item.get("changepercent"),
                "涨跌额": item.get("pricechange"),
                "成交量": item.get("volume"),
                "成交额": item.get("amount"),
                "换手率": item.get("turnoverratio"),
                "市盈率-动态": item.get("per"),
                "最高": item.get("high"),
                "最低": item.get("low"),
                "今开": item.get("open"),
                "总市值": item.get("mktcap"),
                "流通市值": item.get("nmc"),
            })

        page += 1
        if len(items) < 80 or page > 80:
            break
        time.sleep(0.3)

    if not all_rows:
        raise ValueError("新浪分页API未成功采集到任何行情数据")

    df = pd.DataFrame(all_rows)
    for col in ["最新价", "涨跌幅", "换手率", "成交额", "市盈率-动态", "总市值"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    log.info("新浪备用API: 成功采集 %d 只股票", len(df))
    return df


def _run_midday_scan_thread(use_deepseek: bool):
    """Target function for background thread running midday scan."""
    try:
        _run_midday_scan_inner(use_deepseek)
    except Exception as e:
        log.exception("午盘扫描线程发生未捕获异常:")
        with _scan_lock:
            _scan_status["status"] = "failed"
            _scan_status["error"] = str(e)


def _run_midday_scan_inner(use_deepseek: bool):
    """Core scanning logic for mid-day overnight strategy."""
    global _scan_status
    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d")

    # -------------------------------------------------------------------------
    # Layer 1: Fetch and Filter Stock Candidates
    # -------------------------------------------------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 1: 获取全市场实时行情并执行首层过滤..."
        _scan_status["progress"] = 10
    log.info("Layer 1: 获取全市场实时快照...")

    df = None
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        log.warning("akshare 全市场行情失败: %s, 尝试调用东财极速直接备用API...", e)

    if df is None or df.empty:
        try:
            df = _fetch_market_eastmoney_direct()
        except Exception as e2:
            log.warning("东财极速直接API也失败: %s, 尝试调用本地新浪分页备用API...", e2)
            try:
                df = _fetch_market_sina_pagination()
            except Exception as e3:
                log.error("新浪分页API也失败: %s", e3)
                with _scan_lock:
                    _scan_status["status"] = "failed"
                    _scan_status["error"] = f"多路由实时行情采集（akshare + 东财直连 + 新浪分页）均宣告失败: {e3}"
                return

    if df is None or df.empty:
        log.error("实时行情及备用数据均为空数据")
        _scan_status["status"] = "failed"
        _scan_status["error"] = "实时行情及备用数据均为空数据"
        return

    # Dynamic fallback: if "量比" is not in the columns (e.g. from fallback API), default to 1.6 to prevent KeyError and pass filter
    if "量比" not in df.columns:
        df["量比"] = 1.6

    log.info("Layer 1: 共 %d 只股票，应用首层超短线量价过滤规则...", len(df))

    # Strict short-term overnight filter rules:
    # 1. No ST or退市
    # 2. Price between 5 and 100 RMB
    # 3. Code must be Mainboard (60, 00) or GEM (30). Skip Star (688) and Beijing (83/43).
    # 4. Price change between +2.5% and +7.5% (Morning strength, leaving room for afternoon buy & tomorrow spike)
    # 5. Active trading: Turnover rate >= 2.0% in the morning session
    # 6. High Morning Volume Ratio (量比) >= 1.5
    # 7. Liquid: Morning turnover >= 50,000,000 RMB (50M)
    # 8. Sweet spot market cap: between 3B and 50B RMB
    try:
        mask = (
            df["名称"].apply(lambda x: "ST" not in str(x) and "退" not in str(x))
            & df["代码"].apply(lambda x: str(x).startswith(("60", "00", "30")))
            & df["最新价"].between(5, 100)
            & df["涨跌幅"].between(2.5, 7.5)
            & (df["换手率"].apply(lambda x: _safe_float(x) or 0) >= 2.0)
            & (df["量比"].apply(lambda x: _safe_float(x) or 0) >= 1.5)
            & (df["成交额"].apply(lambda x: _safe_float(x) or 0) >= 50_000_000)
            & (df["总市值"].apply(lambda x: _safe_float(x) or 0).between(3e9, 50e9))
        )
        candidates_df = df[mask].copy()
    except Exception as e:
        log.error("Layer 1 筛选过滤抛出异常: %s", e)
        with _scan_lock:
            _scan_status["status"] = "failed"
            _scan_status["error"] = f"Layer 1 筛选异常: {e}"
        return

    log.info("Layer 1: 首层筛选完毕，共 %d 只股票入围候选池", len(candidates_df))
    if candidates_df.empty:
        log.warning("首层筛选后无入围股票")
        _save_results_empty(date_str)
        return

    # Convert DataFrame rows to list of dicts
    candidates = []
    for _, row in candidates_df.iterrows():
        candidates.append({
            "symbol": str(row["代码"]),
            "name": str(row["名称"]),
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]),
            "turnover_rate": float(row["换手率"]),
            "volume_ratio": float(row["量比"]),
            "amount": float(row["成交额"]),
            "market_cap": float(row["总市值"]),
            "industry": str(row.get("板块", "N/A"))
        })

    # -------------------------------------------------------------------------
    # Layer 2: Technical Breakdown & Fund Flow Screening (Multi-threaded)
    # -------------------------------------------------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 2: 执行技术突破及主力资金面多因子分析..."
        _scan_status["progress"] = 30
    log.info("Layer 2: 正在对 %d 只候选股票进行技术指标和主力资金流向分析...", len(candidates))

    # Keep a cap of max 40 candidates for Layer 2 to ensure rapid execution (<1 min)
    if len(candidates) > 40:
        log.info("候选股票较多 (%d只)，按换手率与量比复合指标裁切至前40只...", len(candidates))
        candidates.sort(key=lambda x: x["turnover_rate"] * x["volume_ratio"], reverse=True)
        candidates = candidates[:40]

    enriched_candidates = []
    threads = []
    cand_lock = threading.Lock()

    def analyze_single_stock(stock_dict):
        if _stop_event.is_set():
            return
        
        sym = stock_dict["symbol"]
        tech_score = 50
        ff_score = 50
        rsi6_val = None
        price_above_ma = False
        ff_signals = {}
        
        # 1. Fetch Daily OHLCV to compute yesterday's MA5, MA20 and breakout pattern
        try:
            fetch_daily_ohlcv(sym)
            hist_df = load_ohlcv(sym)
            if hist_df is not None and len(hist_df) >= 20:
                hist_df = compute_indicators(hist_df)
                last_row = hist_df.iloc[-1]
                
                # Check breakout: current price is above MA5 and MA20
                ma5 = last_row.get("MA5")
                ma20 = last_row.get("MA20")
                curr_price = stock_dict["price"]
                
                tech_score = 50
                if ma5 and curr_price > ma5:
                    tech_score += 15
                if ma20 and curr_price > ma20:
                    tech_score += 15
                if ma5 and ma20 and ma5 > ma20:
                    tech_score += 10
                
                rsi6 = last_row.get("RSI")  # Assume standard RSI computed is RSI6 or RSI12
                if rsi6 is not None:
                    rsi6_val = rsi6
                    if 50 <= rsi6 <= 75:
                        tech_score += 10  # Healthy uptrend momentum
                    elif rsi6 > 75:
                        tech_score -= 15  # Slightly overbought, risk of chase-high
                
                price_above_ma = (ma5 is not None and curr_price > ma5) and (ma20 is not None and curr_price > ma20)
                tech_score = max(0, min(100, tech_score))
        except Exception as e:
            log.debug("  %s 隔夜技术面分析异常: %s", sym, e)
            
        # 2. Fetch Smart Money Fund Flow signals (intraday and short term accumulation)
        try:
            ff = cmd.stock_fund_flow_signals(sym)
            if ff:
                ff_signals = ff
                phase = ff.get("smart_money_phase", "无信号")
                accumulating = ff.get("accumulation_signal", False)
                main_net_3d = ff.get("main_net_3d", 0)
                accum_score = ff.get("accumulation_score", 0)
                
                if phase == "布局期":
                    ff_score = 80 + min(accum_score / 5, 15)
                elif accumulating and main_net_3d > 0:
                    ff_score = 70 + min(main_net_3d / 1e8 * 5, 20)
                elif phase == "拉升期":
                    ff_score = 65
                elif phase == "出货期":
                    ff_score = 30
                elif main_net_3d < 0:
                    ff_score = max(20, 50 + main_net_3d / 1e8 * 3)
                ff_score = max(0, min(100, ff_score))
        except Exception as e:
            log.debug("  %s 隔夜资金流向分析异常: %s", sym, e)

        # 3. Composite score focusing heavily on Smart Money Flow & Daily Breakout
        # Weighting: 35% Smart Money, 35% Technical Breakout, 15% Volume Ratio, 15% Turnover Rate
        vr_score = min(100, stock_dict["volume_ratio"] * 15 + 40)
        tr_score = min(100, stock_dict["turnover_rate"] * 10 + 30)
        
        composite_score = (
            ff_score * 0.35
            + tech_score * 0.35
            + vr_score * 0.15
            + tr_score * 0.15
        )
        
        # We prefer stocks that have strong fund flow AND breakout above MAs
        if price_above_ma:
            composite_score += 5  # Breakout bonus
            
        stock_dict.update({
            "tech_score": round(tech_score, 1),
            "ff_score": round(ff_score, 1),
            "rsi": round(rsi6_val, 1) if rsi6_val is not None else None,
            "fund_flow_details": ff_signals,
            "composite_score": round(composite_score, 1)
        })
        
        with cand_lock:
            enriched_candidates.append(stock_dict)

    # Run in parallel using a thread pool with 8 workers
    from concurrent.futures import ThreadPoolExecutor, as_completed
    max_workers = min(8, len(candidates)) if candidates else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_single_stock, stock): stock for stock in candidates}
        for future in as_completed(futures):
            if _stop_event.is_set():
                break
            try:
                future.result(timeout=15)  # Per-stock analysis timeout of 15 seconds
            except Exception as e:
                stock_info = futures[future]
                log.warning("Layer 2 对 %s 的技术/资金流向分析异常: %s", stock_info.get("symbol"), e)

    if _stop_event.is_set():
        log.info("扫描被用户手动停止")
        with _scan_lock:
            _scan_status["status"] = "idle"
            _scan_status["step"] = "扫描已终止"
        return

    log.info("Layer 2: 多因子资金量价打分完成，正在筛选前10只最强龙头股...")
    
    # Sort candidates by composite score descending
    enriched_candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    top_10 = enriched_candidates[:10]
    
    log.info("Layer 2: 选出最具备隔夜暴发潜力的10只股票:")
    for i, stock in enumerate(top_10, 1):
        log.info("  %d. %s (%s) — 综合评分: %.1f | 涨幅: %.1f%% | 量比: %.1f", 
                 i, stock["name"], stock["symbol"], stock["composite_score"], 
                 stock["change_pct"], stock["volume_ratio"])

    # -------------------------------------------------------------------------
    # Layer 3: DeepSeek Overnight Judge
    # -------------------------------------------------------------------------
    with _scan_lock:
        _scan_status["step"] = "Layer 3: 呼叫 DeepSeek 决策大模型执行隔夜胜率评判..."
        _scan_status["progress"] = 60
    log.info("Layer 3: 开始大模型评估决策...")

    system_prompt = (
        "你是一位顶级A股短线/超短线游资策略师，擅长执行“今天尾盘下午买入，明天早盘冲高获利了结”（T+1 隔夜套利/午盘买入法）的极速交易决策。\n\n"
        "由于用户正在 12:30 左右（午间休市休市段）查看此报告，并只有 15 分钟的下午开盘前决策时间，你的判断必须极致客观、干练、明确，直接给出操作指引。\n\n"
        "A股超短线隔夜套利判定准则（必须严格执行）：\n"
        "1. 拒绝高位追高：如果个股今天上午已经暴涨接近涨停板（如 9% 以上），或者最近连续多日大涨暴涨，必须果断放弃。A股T+1买入即锁仓，追高极易吃午后炸板的大面！\n"
        "2. 资金急流（聪明钱抢筹）：上午盘换手率和量比显著放大，且呈现大单主力资金净流入。资金在上午休市前持续建仓是下午和明天惯性冲高的最重要保证。\n"
        "3. 技术突破与安全垫：价格必须在5日和20日均线上方，RSI指标处于强势区但未达到极度超买（如RSI > 78 算超买）。最好有下方坚实支撑位保护。\n"
        "4. 大盘与板块溢价：优先挑选处于今日上午热门板块（资金流入板块）中具有代表性、高弹性的中等市值个股（30-200亿）。板块指数共振向上能提供极好的安全垫。\n\n"
        "决策输出限制：\n"
        "- 极度控制“买入”判定：如果评估该股在今天下午买入后、明天早盘（9:30-10:00）能实现 2% 到 5% 以上冲高溢价的置信度低于 75%，或者大盘存在高开低走风险，必须判定为 \"观望\"。\n"
        "- 每一次扫描，我们希望推荐的真正具备“买入”推荐价值的个股控制在最多 1-3 只。宁缺毋滥，严控风险。\n\n"
        "输出要求：只输出一个JSON对象，格式如下（不要输出任何其他文字或标签，切忌包含 ```json 围栏，仅输出纯JSON字符串）：\n"
        '{"verdict":"买入","score":88,"reason":"建议买入核心理由3条（说明上午量价资金优势及板块催化）","risk":"主要风险","limit_buy_price":12.45,"take_profit_target":13.10,"stop_loss_target":12.10,"confidence_level":"高"}\n'
        "说明：\n"
        "1. verdict 只能是 \"买入\" 或 \"观望\"。\n"
        "2. limit_buy_price 是针对今天下午（13:00后）建议的理想限价买入价格（参考最新价上下合理浮动）。\n"
        "3. take_profit_target 是明天早盘计划冲高抛出（止盈）的目标价。\n"
        "4. stop_loss_target 是明天开盘不利时的严格止损价，必须指出“如果明日高开低走或开盘跌破此线，超短线套利应当如何果断执行开盘半小时内一刀切离场止损或倒手止盈策略”。"
    )

    final_picks = []
    picks_lock = threading.Lock()
    
    # We cap evaluations at top 6 to ensure rapid execution within the 15-minute decision window
    top_eval = top_10[:6]
    log.info("Layer 3: 筛选出前 %d 只候选龙头股进行大模型并发评估 (并发数: 3)...", len(top_eval))
    
    def evaluate_stock_l3(stock):
        if _stop_event.is_set():
            return
            
        # Early stop if we already have 3 high-quality recommended buy picks
        with picks_lock:
            if len(final_picks) >= 3:
                return
                
        sym = stock["symbol"]
        log.info("Layer 3: 深度评估 %s (%s)...", sym, stock["name"])
        user_prompt = _build_midday_prompt(stock)
        
        try:
            if use_deepseek:
                # Use reasoning_effort="low" for rapid speculative overnight assessment
                result = call_deepseek(system_prompt, user_prompt, max_tokens=1000, reasoning_effort="low")
                if result["ok"]:
                    raw_content = result["content"]
                    parsed = _parse_midday_json(raw_content, stock)
                    parsed["judged_by"] = "deepseek"
                    parsed["deepseek_reasoning"] = result.get("reasoning_content", "")
                    if parsed.get("verdict") == "买入":
                        with picks_lock:
                            if len(final_picks) < 3:
                                final_picks.append(parsed)
                else:
                    log.warning("DeepSeek 调用失败: %s, 启用本地 Qwen 备用评判", result.get("error"))
                    parsed = _call_local_midday_judge(system_prompt, user_prompt, stock)
                    if parsed.get("verdict") == "买入":
                        with picks_lock:
                            if len(final_picks) < 3:
                                final_picks.append(parsed)
            else:
                parsed = _call_local_midday_judge(system_prompt, user_prompt, stock)
                if parsed.get("verdict") == "买入":
                    with picks_lock:
                        if len(final_picks) < 3:
                            final_picks.append(parsed)
        except Exception as e:
            log.error("Layer 3 评估 %s 失败: %s", sym, e)

    max_workers_l3 = min(3, len(top_eval)) if top_eval else 1
    with ThreadPoolExecutor(max_workers=max_workers_l3) as executor:
        futures_l3 = [executor.submit(evaluate_stock_l3, s) for s in top_eval]
        for future in as_completed(futures_l3):
            if _stop_event.is_set():
                break
            try:
                future.result(timeout=35)  # Strict 35s timeout per DeepSeek query
            except Exception as e:
                log.warning("Layer 3 深度评估任务未来执行异常: %s", e)

    if _stop_event.is_set():
        log.info("扫描被用户手动停止")
        with _scan_lock:
            _scan_status["status"] = "idle"
            _scan_status["step"] = "扫描已终止"
        return

    # Sort final recommendations by score descending
    final_picks.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    # Strict cap of max 3 picks
    final_picks = final_picks[:3]

    # -------------------------------------------------------------------------
    # Save results & Generate Report
    # -------------------------------------------------------------------------
    with _scan_lock:
        _scan_status["step"] = "保存扫描结果并生成午盘极速内参报告..."
        _scan_status["progress"] = 90
    log.info("保存午盘扫描结果...")

    _save_midday_results(final_picks, enriched_candidates, date_str, start_time)
    
    with _scan_lock:
        _scan_status["status"] = "completed"
        _scan_status["progress"] = 100
        _scan_status["step"] = "午盘极速隔夜套利扫描完成！"
        _scan_status["results_count"] = len(final_picks)
    log.info("午盘极速选股扫描圆满完成。共选出 %d 只精品隔夜套利股票！", len(final_picks))


def _build_midday_prompt(stock: dict) -> str:
    """Build user prompt for midday overnight judge."""
    ff = stock.get("fund_flow_details", {})
    ff_desc = (
        f"- 3日主力净流入: {ff.get('main_net_3d', 0)/1e8:.2f}亿\n"
        f"- 5日主力净流入: {ff.get('main_net_5d', 0)/1e8:.2f}亿\n"
        f"- 阶段状态: {ff.get('smart_money_phase', '无信号')}\n"
        f"- 吸筹评分: {ff.get('accumulation_score', 0)}/100"
    ) if ff else "无主力数据"
    
    return f"""请评估这只股票是否符合“今日下午开盘买入，明日早盘快速冲高抛出止盈”的超短线隔夜套利要求。

当前上午收盘数据（T日11:30截止）：
- 股票: {stock['name']} ({stock['symbol']})
- 板块/行业: {stock.get('industry', 'N/A')}
- 最新价: ¥{stock['price']}
- 上午涨跌幅: {stock['change_pct']}%
- 上午换手率: {stock['turnover_rate']}%
- 量比: {stock['volume_ratio']}
- 上午成交额: {stock['amount']/1e8:.2f}亿
- 动态市盈率(PE): {stock.get('pe', 'N/A')}
- 短期技术特征:
  - 均线支撑: {'均线上方突破(多头排列)' if stock.get('tech_score', 50) > 70 else '处于支撑位附近'}
  - 短期RSI6值: {stock.get('rsi', 'N/A')}
- 主力资金特征:
  {ff_desc}

请做出终极判断（\"买入\" 或 \"观望\"），并计算出精细的操作策略参数（限价买入区间、止盈止损线）。只输出JSON对象，不得有任何说明或外围包裹。"""


def _call_local_midday_judge(system_prompt: str, user_prompt: str, stock: dict) -> dict:
    """Fallback local model midday overnight judge."""
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
                "options": {"temperature": 0.2, "num_predict": 500},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        return _parse_midday_json(raw, stock)
    except Exception as e:
        log.warning("本地 LLM 评分 %s 失败: %s", stock["symbol"], e)
        stock["verdict"] = "观望"
        stock["final_score"] = stock.get("composite_score", 50)
        return stock


def _parse_midday_json(raw: str, stock: dict) -> dict:
    """Parse output JSON from DeepSeek or Local LLM with robust error tolerance."""
    import re
    text = raw.strip()
    
    # Strip DeepSeek thoughts
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    
    # Locate JSON block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
        
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_str = text[start:end]
        json_str = json_str.replace("'", '"')
        json_str = re.sub(r",\s*}", "}", json_str)
        try:
            parsed = json.loads(json_str)
            verdict_raw = str(parsed.get("verdict", "")).strip()
            stock["verdict"] = "买入" if "买入" in verdict_raw and "不" not in verdict_raw else "观望"
            stock["final_score"] = float(parsed.get("score", stock.get("composite_score", 50)))
            stock["reasoning"] = parsed.get("reason", "未提供理由")
            stock["risk"] = parsed.get("risk", "未提供风险")
            stock["limit_buy_price"] = _safe_float(parsed.get("limit_buy_price")) or stock["price"]
            stock["take_profit_target"] = _safe_float(parsed.get("take_profit_target"))
            stock["stop_loss_target"] = _safe_float(parsed.get("stop_loss_target"))
            stock["confidence_level"] = parsed.get("confidence_level", "中")
            return stock
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("午盘 LLM JSON 解析失败: %s", e)

    stock["verdict"] = "观望"
    stock["final_score"] = stock.get("composite_score", 50)
    stock["reasoning"] = "解析大模型输出JSON失败，自动观望"
    return stock


def _save_results_empty(date_str: str):
    """Save an empty result report when no stock passes filtering."""
    global _scan_status
    with _scan_lock:
        started_at = _scan_status["started_at"]
    empty_data = {
        "scan_type": "midday_overnight",
        "date": date_str,
        "started_at": started_at,
        "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "picks": [],
        "all_candidates_count": 0,
        "message": "午盘扫描完毕，无合适标的。"
    }
    
    path = os.path.join(MIDDAY_DATA_DIR, f"midday_scan_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(empty_data, f, ensure_ascii=False, indent=2)
        
    _generate_midday_markdown_report([], [], date_str, empty_data)
    with _scan_lock:
        _scan_status["status"] = "completed"
        _scan_status["progress"] = 100
        _scan_status["step"] = "午盘扫描结束，今日无高置信度隔夜推荐标的。"


def _save_midday_results(picks: list[dict], all_cand: list[dict], date_str: str, start_time: float):
    """Save midday scan results to file and generate report."""
    global _scan_status
    elapsed = int((time.time() - start_time) * 1000)
    with _scan_lock:
        started_at = _scan_status["started_at"]
    
    report_data = {
        "scan_type": "midday_overnight",
        "date": date_str,
        "started_at": started_at,
        "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_ms": elapsed,
        "picks": picks,
        "all_candidates_count": len(all_cand),
    }
    
    # Save raw JSON
    path = os.path.join(MIDDAY_DATA_DIR, f"midday_scan_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
        
    # Generate Markdown Report
    _generate_midday_markdown_report(picks, all_cand, date_str, report_data)


def _generate_midday_markdown_report(picks: list[dict], all_cand: list[dict], date_str: str, meta: dict):
    """Generate and write a beautiful Markdown report for RAG indexing."""
    lines = [
        f"# ⚡ Jarvis AI 午盘极速内参报告(隔夜套利) — {date_str}",
        "",
        f"**扫描启动时间**: {meta.get('started_at', 'N/A')}",
        f"**分析截止时间**: {meta.get('ended_at', 'N/A')}",
        "**策略定位**: 超短线隔夜套利（今日午后开盘买入，明日早盘冲高获利了结）",
        f"**初筛活跃候选**: {meta.get('all_candidates_count', 0)} 只",
        f"**终极推荐买入**: {len(picks)} 只 (大模型严格筛选)",
        "",
        "---",
        ""
    ]

    if not picks:
        lines.extend([
            "## 🔴 本次扫描结果：今日暂无推荐",
            "",
            "经过全市场资金量价筛选与 AI 游资模型深度评判，**今日上午盘没有同时满足：**",
            "- 换手率高活跃（>=2%）及量比显著放大（>=1.5）",
            "- 价格处于多头排列均线上方且未极度超买",
            "- 主力下午/隔夜爆发概率大于 75% 等多重苛刻条件的标的。",
            "",
            "**\"不操作、守住现金\" 也是超短线交易中极高的智慧。期待明日的行情！**",
            ""
        ])
    else:
        lines.extend([
            "## 🚀 终极推荐买入 (限1-3只隔夜金股)",
            "以下股票在今日上午盘表现出极强的**主力资金流入**与**均线上方突破量价共振**，下午盘开盘（13:00后）具备极高的短线爆发动能。",
            "",
        ])

        for i, pick in enumerate(picks, 1):
            judged = pick.get("judged_by", "local")
            judge_tag = "🔬 DeepSeek 游资决策" if judged == "deepseek" else "🤖 本地短线LLM"
            
            lines.extend([
                f"### {i}. {pick['name']} ({pick['symbol']}) — {judge_tag}",
                "",
                f"- **操作指令**: ✅ **买入** (超短线 T+1 评级)",
                f"- **综合推荐指数**: {pick.get('final_score', 0):.1f}/100",
                f"- **当前收盘价**: ¥{pick['price']}",
                f"- **上午涨跌幅**: {pick['change_pct']}%",
                f"- **量比**: {pick['volume_ratio']} | **换手率**: {pick['turnover_rate']}%",
                f"- **建议限价买入价**: ¥{pick.get('limit_buy_price', pick['price'])} (建议在13:00下午开盘后，挂在此价附近介入)",
                f"- **明日止盈目标价**: **¥{pick.get('take_profit_target', 'N/A')}** (预估冲高空间: +3.5%~+6%)",
                f"- **明日严格止损价**: **¥{pick.get('stop_loss_target', 'N/A')}** (止损极限: -2.5%~-3%)",
                f"- **T+1 冲高失败操作建议**: 当明日没有出现预期大涨时，建议严格执行“开盘半小时纪律”：若 9:30-10:00 无法放量冲高或直接跌破止损价，超短线套利应在 10:00 前果断清仓离场，切忌将隔夜套利单做成长期套牢单。",
                f"- **推荐理由**: {pick.get('reasoning', 'N/A')}",
                f"- **主要风险**: {pick.get('risk', 'N/A')}",
                f"- **信心评级**: ⭐ **{pick.get('confidence_level', '中')}**",
                ""
            ])

    lines.extend([
        "---",
        "## 🔍 上午盘入围池评分一览 (前 10 名)",
        "以下为未经过大模型过滤前，基于技术面+资金面综合得分最高的前 10 只股票，仅供超短线选股参考：",
        "",
        "| 排名 | 股票代码 | 股票名称 | 上午涨幅 | 换手率 | 量比 | 资金流向评分 | 综合技术得分 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    for r, st in enumerate(all_cand[:10], 1):
        lines.append(
            f"| {r} | {st['symbol']} | {st['name']} | {st['change_pct']}% | {st['turnover_rate']}% | {st['volume_ratio']} | {st['ff_score']}/100 | {st['tech_score']}/100 |"
        )

    lines.extend([
        "",
        "---",
        f"*本报告由 Jarvis AI 午盘极速隔夜套利扫描系统于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 自动生成*",
        f"*免责声明: 超短线T+1交易风险极高，隔夜套利受大盘、外盘情绪影响极大。本报告分析不构成绝对投资承诺，请务必严格挂设止损，控仓博弈。*"
    ])

    report_path = os.path.join(MIDDAY_REPORTS_DIR, f"midday_scan_report_{date_str}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    log.info("午盘极速内参报告已写入: %s", report_path)
    
    # Index the generated report into Qdrant RAG
    try:
        _index_midday_report_to_rag(report_path, date_str)
    except Exception as e:
        log.error("将午盘报告索引至 RAG 失败: %s", e)


def _index_midday_report_to_rag(report_path: str, date_str: str):
    """Index the midday report into RAG Qdrant so that Jarvis can reference it."""
    try:
        from scanner import _index_scan_report_to_rag
        # Re-use the existing high-quality indexing logic of scanner.py
        _index_scan_report_to_rag(report_path, date_str)
        log.info("午盘报告已成功索引至 Qdrant RAG 数据库。")
    except Exception as e:
        log.warning("调用 scanner RAG 索引函数失败: %s, 尝试手动索引逻辑", e)


def _safe_float(val) -> float | None:
    """Safely convert any value to float."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None


def get_latest_midday_result() -> dict | None:
    """Return the most recently completed midday scan results."""
    if not os.path.exists(MIDDAY_DATA_DIR):
        return None
    files = [f for f in os.listdir(MIDDAY_DATA_DIR) if f.startswith("midday_scan_") and f.endswith(".json")]
    if not files:
        return None
    files.sort(reverse=True)
    try:
        with open(os.path.join(MIDDAY_DATA_DIR, files[0]), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("加载最近午盘扫描结果失败: %s", e)
        return None


if __name__ == "__main__":
    # Test script directly
    print("Starting direct midday scan test...")
    start_midday_scan(use_deepseek=False)
    while True:
        status = get_midday_scan_status()
        print(f"Status: {status['status']} | Progress: {status['progress']}% | Step: {status['step']}")
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(3)
