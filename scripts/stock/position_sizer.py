"""
仓位建议引擎 + 相关性监控.

Phase 4.1 + 4.2: 组合仓位建议、60日相关性矩阵、高相关预警.
"""
import json
import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd

from config import PORTFOLIO_FILE, STOCK_DATA_DIR, STOCK_REPORTS_ROOT
from regime_detector import detect_market_regime, regime_position_multiplier

log = logging.getLogger(__name__)

MAX_SINGLE = 0.20
MAX_INDUSTRY = 0.30


def _load_portfolio() -> dict:
    if os.path.isfile(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"holdings": [], "total_capital": 500000, "cash": 500000}


def _save_portfolio(data: dict):
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def correlation_matrix(symbols: list[str], window: int = 60) -> dict:
    """60 日滚动收益率相关系数矩阵."""
    from technical_analysis import load_ohlcv

    rets = {}
    for sym in symbols:
        ohlcv = load_ohlcv(sym)
        if ohlcv is None or len(ohlcv) < window + 5:
            continue
        r = ohlcv["close"].pct_change().tail(window)
        rets[sym] = r.values[-window:]

    if len(rets) < 2:
        return {"symbols": list(rets.keys()), "matrix": {}, "warnings": ["数据不足"]}

    min_len = min(len(v) for v in rets.values())
    df = pd.DataFrame({k: v[-min_len:] for k, v in rets.items()})
    corr = df.corr().round(3)

    warnings = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            v = corr.loc[a, b]
            if v > 0.8:
                warnings.append(f"{a} 与 {b} 相关系数 {v:.2f} — 分散度不足")

    return {
        "symbols": cols,
        "matrix": corr.to_dict(),
        "warnings": warnings,
        "window_days": window,
    }


def _score_symbol(symbol: str) -> dict:
    """综合估值 + 不确定性 + 技术面对单标的打分 (0-100)."""
    score = 50.0
    meta = {}

    try:
        from valuation import compute_valuation
        val = compute_valuation(symbol)
        rating = val.get("rating", {})
        passed = rating.get("passed", 0)
        total = rating.get("total", 1) or 1
        score += (passed / total - 0.5) * 40
        meta["valuation_verdict"] = rating.get("verdict")
    except Exception:
        pass

    pred_path = os.path.join(STOCK_DATA_DIR, symbol, "price_prediction.json")
    if os.path.isfile(pred_path):
        try:
            with open(pred_path, encoding="utf-8") as f:
                pred = json.load(f)
            unc = pred.get("uncertainty", {}).get("level") or pred.get("confidence", {}).get("level")
            if unc in ("high", "very_low"):
                score -= 15
            elif unc in ("medium", "low-medium"):
                score -= 5
            meta["uncertainty"] = unc
        except Exception:
            pass

    try:
        from regime_detector import detect_symbol_regime
        reg = detect_symbol_regime(symbol)
        if reg.get("regime") == "downtrend":
            score -= 20
        elif reg.get("regime") in ("uptrend", "strong_bull"):
            score += 10
        meta["regime"] = reg.get("regime_zh")
    except Exception:
        pass

    return {"symbol": symbol, "score": max(0, min(100, score)), "meta": meta}


def suggest_portfolio(total_capital: float | None = None) -> dict:
    """
    基于自选股 + 估值/不确定性/regime 生成仓位建议.
    """
    from watchlist import list_stocks

    pf = _load_portfolio()
    capital = total_capital or pf.get("total_capital", 500000)
    stocks = list_stocks()
    symbols = [s["symbol"] for s in stocks if s.get("symbol")]

    if not symbols:
        return {"error": "自选股为空", "allocations": [], "cash_pct": 100}

    market = detect_market_regime()
    regime = market.get("regime", "unknown")
    pos_mult = regime_position_multiplier(regime)

    scored = []
    for s in stocks:
        sym = s["symbol"]
        sc = _score_symbol(sym)
        sc["name"] = s.get("name", sym)
        sc["industry"] = s.get("sector", "")
        scored.append(sc)

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = [x for x in scored if x["score"] >= 45][:8]
    if not top:
        top = scored[:3]

    raw_weights = [x["score"] for x in top]
    total_score = sum(raw_weights) or 1
    investable = pos_mult

    allocations = []
    industry_totals: dict[str, float] = {}

    for item, w in zip(top, raw_weights):
        pct = min(MAX_SINGLE, (w / total_score) * investable)
        ind = item.get("industry") or "其他"
        if industry_totals.get(ind, 0) + pct > MAX_INDUSTRY:
            pct = max(0, MAX_INDUSTRY - industry_totals.get(ind, 0))
        industry_totals[ind] = industry_totals.get(ind, 0) + pct
        allocations.append({
            "symbol": item["symbol"],
            "name": item["name"],
            "weight_pct": round(pct * 100, 1),
            "amount": round(capital * pct, 0),
            "score": round(item["score"], 1),
            "meta": item["meta"],
        })

    invested = sum(a["weight_pct"] for a in allocations)
    cash_pct = round(100 - invested, 1)

    corr = correlation_matrix(symbols)

    return {
        "total_capital": capital,
        "market_regime": regime,
        "market_regime_zh": market.get("regime_zh"),
        "regime_advice": market.get("advice"),
        "position_multiplier": pos_mult,
        "allocations": allocations,
        "cash_pct": cash_pct,
        "cash_amount": round(capital * cash_pct / 100, 0),
        "correlation": corr,
        "constraints": {
            "max_single_pct": MAX_SINGLE * 100,
            "max_industry_pct": MAX_INDUSTRY * 100,
        },
        "generated_at": datetime.now().isoformat(),
    }
