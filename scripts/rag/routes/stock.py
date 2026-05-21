"""Stock analysis API — Flask blueprint (extracted from agent.py)."""

import importlib.util as _ilu
import json
import logging
import os
import sys
import traceback
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

# ---------------------------------------------------------------------------
# Stock Analysis API
# ---------------------------------------------------------------------------
_stock_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "stock")
)
_rag_config = sys.modules.get("config")

_stock_cfg_spec = _ilu.spec_from_file_location(
    "stock_config", os.path.join(_stock_path, "config.py")
)
_stock_config = _ilu.module_from_spec(_stock_cfg_spec)
_stock_cfg_spec.loader.exec_module(_stock_config)


_STOCK_MODULES = [
    "config", "fetch_market_data", "technical_analysis", "report_technical",
    "fundamental_analysis", "sentiment", "features", "model_xgboost",
    "model_price_predictor", "prediction_tracker", "llm_reasoning",
    "watchlist", "scanner", "long_term_scanner", "hot_sectors", "market_sentiment",
    "black_swan_detector", "china_market_data", "model_timing",
    "backtest_engine", "midday_scanner",
]

log = logging.getLogger(__name__)

stock_bp = Blueprint("stock", __name__)


def _with_stock_imports(fn):
    """Decorator that swaps sys.modules['config'] to stock config for the call.

    Also flushes cached stock modules so they re-import with the correct
    config — prevents 'cannot import STOCK_DATA_DIR from config' when
    a stock module was first imported with the parent scripts/config.py.
    """
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        prev_config = sys.modules.get("config")
        prev_mods = {m: sys.modules.pop(m) for m in _STOCK_MODULES if m in sys.modules}

        sys.modules["config"] = _stock_config
        if _stock_path not in sys.path:
            sys.path.insert(0, _stock_path)
        try:
            return fn(*args, **kwargs)
        finally:
            for m in _STOCK_MODULES:
                if m in sys.modules and m != "config":
                    del sys.modules[m]
            if prev_config is not None:
                sys.modules["config"] = prev_config
            elif "config" in sys.modules:
                del sys.modules["config"]
    return wrapper


@stock_bp.route("/api/stock/analyze", methods=["POST"])
@_with_stock_imports
def api_stock_analyze():
    """Run stock analysis (technical, fundamental, sentiment, or full)."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()
    mode = body.get("mode", "full")

    if not symbol or not symbol.isdigit():
        return jsonify({"error": "请输入有效的股票代码 (纯数字)"}), 400

    try:
        result = {}

        if mode in ("technical", "full"):
            from report_technical import generate_report as gen_tech, save_report
            from technical_analysis import analyze as tech_analyze
            analysis = tech_analyze(symbol)
            save_report(symbol, analysis)
            result["technical_report"] = gen_tech(symbol, analysis)

        if mode in ("fundamental", "full"):
            from fundamental_analysis import fetch_fundamentals, generate_fundamental_report
            fetch_fundamentals(symbol)
            result["fundamental_report"] = generate_fundamental_report(symbol)

        if mode in ("sentiment", "full"):
            from sentiment import analyze_stock_sentiment, generate_sentiment_report
            analyze_stock_sentiment(symbol)
            result["sentiment_report"] = generate_sentiment_report(symbol)

        if mode in ("xgboost", "full"):
            from model_xgboost import train_and_predict, generate_xgb_report
            xgb_result = train_and_predict(symbol)
            result["xgb_report"] = generate_xgb_report(symbol, xgb_result)

        if mode in ("fund_flow", "full"):
            try:
                from china_market_data import stock_fund_flow_signals
                ff = stock_fund_flow_signals(symbol)
                phase = ff.get("smart_money_phase", "无信号")
                score = ff.get("accumulation_score", 0)
                detail = ff.get("detail", "")
                lines = [
                    "# 资金流向 & 聪明钱分析",
                    f"**聪明钱阶段: {phase}** (布局得分: {score}/100)",
                    "",
                ]
                if detail:
                    lines.append(f"> {detail}")
                    lines.append("")
                lines.append(f"| 指标 | 值 |")
                lines.append(f"|---|---|")
                lines.append(f"| 3日主力净流入 | {ff.get('main_net_3d', 'N/A')} |")
                lines.append(f"| 10日主力净流入 | {ff.get('main_net_10d', 'N/A')} |")
                lines.append(f"| 3日主力净占比 | {ff.get('main_pct_3d', 'N/A')}% |")
                lines.append(f"| 超大单占比 | {ff.get('super_large_ratio', 'N/A')} |")
                lines.append(f"| 价格-资金背离 | {ff.get('fund_price_divergence', 'N/A')} |")
                lines.append("")
                phase_guide = {
                    "布局期": "资金持续流入但价格未涨,主力正在悄悄吸筹 → **可以考虑建仓**",
                    "拉升期": "资金流入且价格已涨,追高风险大 → **谨慎追高,T+1风险**",
                    "出货期": "资金流出但价格仍涨,主力可能在出货 → **不建议买入**",
                    "观察期": "有资金流入迹象但未达布局标准 → **继续观察**",
                    "无信号": "资金流向不明确 → **暂无明确方向**",
                }
                lines.append(f"**建议:** {phase_guide.get(phase, '')}")
                result["fund_flow_report"] = "\n".join(lines)
            except Exception as e:
                log.debug("资金流向分析 %s 失败: %s", symbol, e)

        if mode == "full":
            from llm_reasoning import generate_prediction
            result["prediction_report"] = generate_prediction(symbol, stream=False)

        return jsonify(result)

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"分析失败: {exc}"}), 500


@stock_bp.route("/api/stock/analyze/deepseek", methods=["POST"])
@_with_stock_imports
def api_stock_analyze_deepseek():
    """Run DeepSeek API analysis for a stock (final LLM step only)."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()

    if not symbol or not symbol.isdigit():
        return jsonify({"error": "请输入有效的股票代码 (纯数字)"}), 400

    try:
        from llm_reasoning import generate_prediction_deepseek
        result = generate_prediction_deepseek(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": f"DeepSeek 分析失败: {exc}"}), 500


@stock_bp.route("/api/stock/watchlist", methods=["GET"])
@_with_stock_imports
def api_stock_watchlist_get():
    """Get the watchlist with latest prices."""
    try:
        from watchlist import get_watchlist_with_prices
        stocks = get_watchlist_with_prices()
        return jsonify({"stocks": stocks})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/watchlist", methods=["POST"])
@_with_stock_imports
def api_stock_watchlist_add():
    """Add a stock to the watchlist."""
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol", "").strip()
    name = body.get("name", "").strip()
    sector = body.get("sector", "").strip()
    if not symbol:
        return jsonify({"error": "缺少股票代码"}), 400
    try:
        from watchlist import add_stock
        result = add_stock(symbol, name, sector)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/watchlist/<symbol>", methods=["DELETE"])
@_with_stock_imports
def api_stock_watchlist_remove(symbol):
    """Remove a stock from the watchlist."""
    try:
        from watchlist import remove_stock
        result = remove_stock(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/watchlist/refresh", methods=["POST"])
@_with_stock_imports
def api_stock_watchlist_refresh():
    """Refresh all watchlist data."""
    try:
        from watchlist import refresh_all_data
        refresh_all_data()
        return jsonify({"ok": True})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/start", methods=["POST"])
@_with_stock_imports
def api_stock_scan_start():
    """Start AI stock scanner."""
    try:
        body = request.get_json(silent=True) or {}
        use_ds = body.get("use_deepseek", False)
        from scanner import start_scan
        result = start_scan(use_deepseek=use_ds)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/status", methods=["GET"])
@_with_stock_imports
def api_stock_scan_status():
    """Get scan progress and partial results."""
    try:
        from scanner import get_scan_status
        return jsonify(get_scan_status())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/stop", methods=["POST"])
@_with_stock_imports
def api_stock_scan_stop():
    """Stop running scan."""
    try:
        from scanner import stop_scan
        return jsonify(stop_scan())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/result", methods=["GET"])
@_with_stock_imports
def api_stock_scan_result():
    """Get latest scan result."""
    try:
        from scanner import get_latest_result
        result = get_latest_result()
        if result:
            return jsonify(result)
        return jsonify({"error": "暂无扫描结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/history", methods=["GET"])
@_with_stock_imports
def api_stock_scan_history():
    """Get scan history with performance tracking."""
    try:
        from scanner import get_history
        return jsonify({"history": get_history()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/dates", methods=["GET"])
@_with_stock_imports
def api_stock_scan_dates():
    """List available scan dates."""
    try:
        from scanner import list_scan_dates
        return jsonify({"dates": list_scan_dates()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/scan/result/<date_str>", methods=["GET"])
@_with_stock_imports
def api_stock_scan_result_by_date(date_str):
    """Get scan result for a specific date."""
    try:
        from scanner import get_result_by_date
        result = get_result_by_date(date_str)
        if result:
            return jsonify(result)
        return jsonify({"error": "该日期无扫描结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Stock PDF Export ---

@stock_bp.route("/api/stock/export-pdf", methods=["POST"])
@_with_stock_imports
def api_stock_export_pdf():
    """Generate a PDF report for any stock feature."""
    try:
        body = request.get_json(silent=True) or {}
        report_type = body.get("type", "")
        data = body.get("data", {})
        if not report_type or not data:
            return jsonify({"error": "Missing 'type' or 'data'"}), 400

        from stock_pdf import generate_stock_pdf, ALLOWED_TYPES
        if report_type not in ALLOWED_TYPES:
            return jsonify({"error": f"Unknown type '{report_type}'. Allowed: {sorted(ALLOWED_TYPES)}"}), 400

        pdf_path = generate_stock_pdf(report_type, data)
        filename = os.path.basename(pdf_path)
        date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        pdf_url = f"/api/stock/pdf-file/{date_str}/{filename}"
        return jsonify({"pdf_url": pdf_url, "path": pdf_path})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/pdf-file/<date_str>/<filename>", methods=["GET"])
def api_stock_pdf_file(date_str, filename):
    """Serve a generated stock PDF file."""
    try:
        stock_reports = os.environ.get("STOCK_REPORTS_ROOT", r"C:\reports\stock")
        pdf_dir = os.path.join(stock_reports, "pdf")
        fpath = os.path.join(pdf_dir, filename)
        if not os.path.isfile(fpath):
            return jsonify({"error": "PDF not found"}), 404
        return send_file(fpath, mimetype="application/pdf", download_name=filename)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Long-Term Scanner ---

@stock_bp.route("/api/stock/long-term/start", methods=["POST"])
@_with_stock_imports
def api_stock_lt_start():
    """Start long-term stock scanner."""
    try:
        body = request.get_json(silent=True) or {}
        use_ds = body.get("use_deepseek", False)
        from long_term_scanner import start_lt_scan
        result = start_lt_scan(use_deepseek=use_ds)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/status", methods=["GET"])
@_with_stock_imports
def api_stock_lt_status():
    """Get long-term scan progress."""
    try:
        from long_term_scanner import get_lt_status
        return jsonify(get_lt_status())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/stop", methods=["POST"])
@_with_stock_imports
def api_stock_lt_stop():
    """Stop long-term scan."""
    try:
        from long_term_scanner import stop_lt_scan
        return jsonify(stop_lt_scan())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/result", methods=["GET"])
@_with_stock_imports
def api_stock_lt_result():
    """Get latest long-term scan result."""
    try:
        from long_term_scanner import get_lt_latest_result
        result = get_lt_latest_result()
        if result:
            return jsonify(result)
        return jsonify({"error": "暂无长期推荐结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/history", methods=["GET"])
@_with_stock_imports
def api_stock_lt_history():
    """Get long-term scan history."""
    try:
        from long_term_scanner import get_lt_history
        return jsonify({"history": get_lt_history()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/dates", methods=["GET"])
@_with_stock_imports
def api_stock_lt_dates():
    """List available long-term scan dates."""
    try:
        from long_term_scanner import list_lt_scan_dates
        return jsonify({"dates": list_lt_scan_dates()})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/long-term/result/<date_str>", methods=["GET"])
@_with_stock_imports
def api_stock_lt_result_by_date(date_str):
    """Get long-term scan result for a specific date."""
    try:
        from long_term_scanner import get_lt_result_by_date
        result = get_lt_result_by_date(date_str)
        if result:
            return jsonify(result)
        return jsonify({"error": "该日期无长期推荐结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Mid-day Overnight Speculative Scanner ---

@stock_bp.route("/api/stock/midday/start", methods=["POST"])
@_with_stock_imports
def api_stock_midday_start():
    """Start Mid-day Overnight scanner."""
    try:
        body = request.get_json(silent=True) or {}
        use_ds = bool(body.get("use_deepseek", True))
        from midday_scanner import start_midday_scan
        result = start_midday_scan(use_deepseek=use_ds)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/midday/status", methods=["GET"])
@_with_stock_imports
def api_stock_midday_status():
    """Get Mid-day scan progress and status."""
    try:
        from midday_scanner import get_midday_scan_status
        return jsonify(get_midday_scan_status())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/midday/stop", methods=["POST"])
@_with_stock_imports
def api_stock_midday_stop():
    """Stop running Mid-day scan."""
    try:
        from midday_scanner import stop_midday_scan
        return jsonify(stop_midday_scan())
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/midday/result", methods=["GET"])
@_with_stock_imports
def api_stock_midday_result():
    """Get latest Mid-day scan result."""
    try:
        from midday_scanner import get_latest_midday_result
        result = get_latest_midday_result()
        if result:
            return jsonify(result)
        return jsonify({"error": "暂无午盘扫描结果"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Daily Training & Price Prediction ---

_train_thread = None
_train_lock = __import__("threading").Lock()


@stock_bp.route("/api/stock/train/daily", methods=["POST"])
@_with_stock_imports
def api_stock_train_daily():
    """Train price prediction models for all watchlist stocks."""
    global _train_thread
    import threading

    req_data = request.get_json(silent=True) or {}
    use_deepseek = req_data.get("use_deepseek", False)

    with _train_lock:
        if _train_thread is not None and _train_thread.is_alive():
            return jsonify({"ok": False, "error": "训练正在进行中"})

    def _run_training():
        import importlib.util as _ilu_inner
        _stock_dir = _stock_path
        if _stock_dir not in sys.path:
            sys.path.insert(0, _stock_dir)
        _cfg_path = os.path.join(_stock_dir, "config.py")
        _spec = _ilu_inner.spec_from_file_location("config", _cfg_path)
        _cfg = _ilu_inner.module_from_spec(_spec)
        _spec.loader.exec_module(_cfg)
        sys.modules["config"] = _cfg

        for mod_name in ["watchlist", "model_price_predictor", "prediction_tracker",
                         "fetch_market_data", "technical_analysis", "features"]:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        from watchlist import list_stocks
        from model_price_predictor import train_price_prediction, generate_price_prediction_deepseek
        from prediction_tracker import record_prediction, backfill_actuals, get_latest_verification, get_accuracy_stats, get_aggregate_stats
        from fetch_market_data import update_stock_data

        stocks = list_stocks()
        progress_path = os.path.join(_cfg.STOCK_REPORTS_ROOT, "train_progress.json")
        progress = {
            "status": "running",
            "total": len(stocks),
            "completed": 0,
            "current": "",
            "results": [],
            "verifications": [],
            "started_at": __import__("datetime").datetime.now().isoformat(),
            "use_deepseek": use_deepseek,
        }

        def _save_prog():
            with open(progress_path, "w", encoding="utf-8") as fp:
                json.dump(progress, fp, ensure_ascii=False, indent=2, default=str)

        _save_prog()

        for i, stock in enumerate(stocks):
            sym = stock.get("symbol", "")
            if not sym:
                continue
            progress["current"] = f"{stock.get('name', sym)} ({sym})"
            _save_prog()

            try:
                update_stock_data(sym)
                n_filled = backfill_actuals(sym)

                verification = get_latest_verification(sym)
                if verification:
                    verification["symbol"] = sym
                    verification["name"] = stock.get("name", "")
                    progress["verifications"].append(verification)

                result = train_price_prediction(sym)
                if "error" not in result:
                    if use_deepseek:
                        try:
                            generate_price_prediction_deepseek(sym, result)
                        except Exception as dse:
                            log.error("DeepSeek calibration failed for %s: %s", sym, dse)

                    record_prediction(sym, result)
                    stats = get_accuracy_stats(sym)
                    progress["results"].append({
                        "symbol": sym,
                        "name": stock.get("name", ""),
                        "predictions": result.get("predictions"),
                        "change_pct": result.get("change_pct"),
                        "current_close": result.get("current_close"),
                        "health": stats.get("health"),
                        "deepseek": result.get("deepseek"),
                    })
                else:
                    progress["results"].append({
                        "symbol": sym, "error": result["error"]
                    })
            except Exception as e:
                progress["results"].append({"symbol": sym, "error": str(e)})

            progress["completed"] = i + 1
            _save_prog()

        try:
            watchlist_symbols = [s.get("symbol") for s in stocks if s.get("symbol")]
            progress["aggregate_stats"] = get_aggregate_stats(watchlist_symbols)
        except Exception:
            pass

        try:
            from market_sentiment import fetch_all_sentiment
            progress["sentiment"] = fetch_all_sentiment()
        except Exception:
            pass

        try:
            from black_swan_detector import scan_world_news
            progress["black_swan"] = scan_world_news()
        except Exception:
            pass

        progress["status"] = "done"
        progress["finished_at"] = __import__("datetime").datetime.now().isoformat()
        _save_prog()

    with _train_lock:
        _train_thread = __import__("threading").Thread(target=_run_training, daemon=True)
        _train_thread.start()

    return jsonify({"ok": True, "message": "训练已启动"})


@stock_bp.route("/api/stock/train/status", methods=["GET"])
@_with_stock_imports
def api_stock_train_status():
    """Get daily training progress."""
    try:
        from config import STOCK_REPORTS_ROOT
        path = os.path.join(STOCK_REPORTS_ROOT, "train_progress.json")
        if not os.path.isfile(path):
            return jsonify({"status": "idle"})
        with open(path, encoding="utf-8") as f:
            progress = json.load(f)
        progress["running"] = _train_thread is not None and _train_thread.is_alive()
        return jsonify(progress)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/predict/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_predict(symbol):
    """Get price prediction and tracking stats for a symbol."""
    try:
        from model_price_predictor import load_price_prediction
        from prediction_tracker import get_accuracy_stats
        pred = load_price_prediction(symbol)
        stats = get_accuracy_stats(symbol)
        return jsonify({"prediction": pred, "accuracy": stats})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/sentiment", methods=["GET"])
@_with_stock_imports
def api_stock_sentiment():
    """Fetch or return cached market sentiment (Fear/Greed + VIX)."""
    try:
        from market_sentiment import fetch_all_sentiment, load_cached_sentiment
        force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
        if force:
            data = fetch_all_sentiment()
        else:
            data = load_cached_sentiment()
            if not data:
                data = fetch_all_sentiment()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/blackswan", methods=["GET"])
@_with_stock_imports
def api_stock_blackswan():
    """Scan world news for black swan events affecting industries."""
    try:
        from black_swan_detector import scan_world_news, load_cached_alerts
        force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
        date_str = request.args.get("date")
        if force or not load_cached_alerts():
            data = scan_world_news(date_str)
        else:
            data = load_cached_alerts()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/risk/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_risk(symbol):
    """Check if a stock is at risk from detected black swan events."""
    try:
        from black_swan_detector import check_stock_risk
        from watchlist import get_watchlist
        wl = get_watchlist()
        sector = ""
        for s in wl:
            if s["symbol"] == symbol:
                sector = s.get("sector", "")
                break
        risk = check_stock_risk(symbol, sector)
        return jsonify(risk or {"symbol": symbol, "alerts": [], "max_severity": None})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# --- Timing Model & Backtest ---

_timing_thread = None
_timing_lock = __import__("threading").Lock()


@stock_bp.route("/api/stock/timing/train", methods=["POST"])
@_with_stock_imports
def api_stock_timing_train():
    """Train timing models for all watchlist stocks."""
    global _timing_thread
    import threading

    with _timing_lock:
        if _timing_thread is not None and _timing_thread.is_alive():
            return jsonify({"ok": False, "error": "择时训练正在进行中"})

    def _run_timing_training():
        import importlib.util as _ilu_inner
        _stock_dir = _stock_path
        if _stock_dir not in sys.path:
            sys.path.insert(0, _stock_dir)
        _cfg_path = os.path.join(_stock_dir, "config.py")
        _spec = _ilu_inner.spec_from_file_location("config", _cfg_path)
        _cfg = _ilu_inner.module_from_spec(_spec)
        _spec.loader.exec_module(_cfg)
        sys.modules["config"] = _cfg

        for mod_name in ["watchlist", "model_timing", "features",
                         "technical_analysis", "china_market_data",
                         "fetch_market_data"]:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

        from watchlist import list_stocks
        from model_timing import train_timing_model

        stocks = list_stocks()
        progress_path = os.path.join(_cfg.STOCK_REPORTS_ROOT, "timing_progress.json")
        progress = {
            "status": "running",
            "total": len(stocks),
            "completed": 0,
            "current": "",
            "results": [],
            "started_at": __import__("datetime").datetime.now().isoformat(),
        }

        def _save_prog():
            with open(progress_path, "w", encoding="utf-8") as fp:
                json.dump(progress, fp, ensure_ascii=False, indent=2, default=str)

        _save_prog()

        for i, stock in enumerate(stocks):
            sym = stock.get("symbol", "")
            if not sym:
                continue
            progress["current"] = f"{stock.get('name', sym)} ({sym})"
            _save_prog()

            try:
                result = train_timing_model(sym)
                progress["results"].append({
                    "symbol": sym,
                    "name": stock.get("name", ""),
                    "status": result.get("status", "error"),
                    "buy_metrics": result.get("buy_metrics"),
                    "exit_metrics": result.get("exit_metrics"),
                })
            except Exception as e:
                progress["results"].append({"symbol": sym, "error": str(e)})

            progress["completed"] = i + 1
            _save_prog()

        progress["status"] = "done"
        progress["finished_at"] = __import__("datetime").datetime.now().isoformat()
        _save_prog()

    with _timing_lock:
        _timing_thread = __import__("threading").Thread(target=_run_timing_training, daemon=True)
        _timing_thread.start()

    return jsonify({"ok": True, "message": "择时训练已启动"})


@stock_bp.route("/api/stock/timing/status", methods=["GET"])
@_with_stock_imports
def api_stock_timing_status():
    """Get timing training progress."""
    try:
        from config import STOCK_REPORTS_ROOT
        path = os.path.join(STOCK_REPORTS_ROOT, "timing_progress.json")
        if not os.path.isfile(path):
            return jsonify({"status": "idle"})
        with open(path, encoding="utf-8") as f:
            progress = json.load(f)
        progress["running"] = _timing_thread is not None and _timing_thread.is_alive()
        return jsonify(progress)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/timing/predict/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_timing_predict(symbol):
    """Get timing signal for a single stock."""
    try:
        from model_timing import predict_timing
        result = predict_timing(symbol)
        return jsonify(result)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/timing/predict-all", methods=["GET"])
@_with_stock_imports
def api_stock_timing_predict_all():
    """Get timing signals for all watchlist stocks."""
    try:
        from model_timing import predict_batch
        from watchlist import list_stocks
        stocks = list_stocks()
        symbols = [s["symbol"] for s in stocks if s.get("symbol")]
        results = predict_batch(symbols)
        for r in results:
            for s in stocks:
                if s["symbol"] == r["symbol"]:
                    r["name"] = s.get("name", "")
                    break
        return jsonify({"predictions": results})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/backtest/<symbol>", methods=["POST"])
@_with_stock_imports
def api_stock_backtest(symbol):
    """Run backtest for a symbol."""
    try:
        from backtest_engine import run_backtest
        body = request.get_json(silent=True) or {}
        strategy = body.get("strategy", "timing")
        capital = float(body.get("capital", 500000))
        result = run_backtest(symbol, strategy=strategy, initial_capital=capital)
        from dataclasses import asdict
        return jsonify(asdict(result))
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/backtest/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_backtest_get(symbol):
    """Get latest backtest result for a symbol."""
    try:
        from backtest_engine import load_latest_backtest
        strategy = request.args.get("strategy", "timing")
        result = load_latest_backtest(symbol, strategy)
        if result:
            return jsonify(result)
        return jsonify({"error": "无回测结果, 请先运行回测"}), 404
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/china-data", methods=["GET"])
@_with_stock_imports
def api_stock_china_data():
    """Fetch all China market data (northbound, margin, limit pool, etc)."""
    try:
        from china_market_data import fetch_all_china_data
        data = fetch_all_china_data()
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/china-data/fund-flow/<symbol>", methods=["GET"])
@_with_stock_imports
def api_stock_fund_flow(symbol):
    """Get individual stock fund flow signals."""
    try:
        from china_market_data import stock_fund_flow_signals
        data = stock_fund_flow_signals(symbol)
        return jsonify(data)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@stock_bp.route("/api/stock/national-team", methods=["GET"])
@_with_stock_imports
def api_stock_national_team():
    """Monitor national team ETF share changes."""
    try:
        from china_market_data import (national_team_monitor, national_team_trend,
                                       national_team_period_stats, national_team_backfill_history,
                                       national_team_fund_signals)
        snapshot = national_team_monitor()
        backfill = national_team_backfill_history(days=90)
        trend = national_team_trend()
        period_stats = national_team_period_stats()
        fund_signals = national_team_fund_signals()
        return jsonify({"snapshot": snapshot, "trend": trend,
                        "period_stats": period_stats, "backfill": backfill,
                        "fund_signals": fund_signals})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500
