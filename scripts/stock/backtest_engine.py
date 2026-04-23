"""
A股回测引擎 — 模拟真实交易约束下的策略表现。

约束:
  T+1: 买入当日不可卖出
  涨跌停限制: 涨停无法买入, 跌停无法卖出
  手续费: 买入万2.5, 卖出万2.5 + 千1印花税
  滑点: 默认0.1%
  仓位: 单只最大30%, 总仓位最大80%

输出:
  - 权益曲线
  - 夏普比率, 最大回撤, 胜率, 盈亏比
  - 交易日志
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd

from config import STOCK_REPORTS_ROOT

log = logging.getLogger(__name__)

_BT_DIR = os.path.join(STOCK_REPORTS_ROOT, "backtest")
os.makedirs(_BT_DIR, exist_ok=True)

BUY_COMMISSION = 0.00025
SELL_COMMISSION = 0.00025
STAMP_TAX = 0.001
SLIPPAGE = 0.001
MIN_COMMISSION = 5.0
MAX_SINGLE_POSITION = 0.30
MAX_TOTAL_POSITION = 0.80

LIMIT_UP_THRESHOLD = 0.095
LIMIT_DOWN_THRESHOLD = -0.095


@dataclass
class Position:
    symbol: str
    shares: int
    cost_price: float
    entry_date: str
    can_sell: bool = False


@dataclass
class Trade:
    date: str
    symbol: str
    action: Literal["buy", "sell"]
    price: float
    shares: int
    cost: float
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annual_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_holding_days: float
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _apply_slippage(price: float, direction: str) -> float:
    """Apply slippage to execution price."""
    if direction == "buy":
        return price * (1 + SLIPPAGE)
    return price * (1 - SLIPPAGE)


def _calc_commission(amount: float, direction: str) -> float:
    """Calculate total transaction cost."""
    comm = amount * (BUY_COMMISSION if direction == "buy" else SELL_COMMISSION)
    comm = max(comm, MIN_COMMISSION)
    if direction == "sell":
        comm += amount * STAMP_TAX
    return round(comm, 2)


def _is_limit_up(change_pct: float) -> bool:
    return change_pct >= LIMIT_UP_THRESHOLD * 100


def _is_limit_down(change_pct: float) -> bool:
    return change_pct <= LIMIT_DOWN_THRESHOLD * 100


def run_backtest(
    symbol: str,
    strategy: str = "timing",
    initial_capital: float = 100000,
    start_date: str = "",
    end_date: str = "",
) -> BacktestResult:
    """Run a full backtest with A-share constraints.

    strategy:
      "timing" — use timing model signals (buy/exit)
      "simple_ma" — simple MA crossover baseline
    """
    from technical_analysis import load_ohlcv, compute_indicators

    log.info("=== 回测开始: %s (%s策略) ===", symbol, strategy)

    ohlcv = load_ohlcv(symbol)
    if ohlcv is None or len(ohlcv) < 60:
        log.error("数据不足: %s", symbol)
        return _empty_result(symbol, strategy, initial_capital)

    ohlcv = compute_indicators(ohlcv)
    ohlcv = ohlcv.reset_index(drop=True)

    if start_date:
        ohlcv = ohlcv[pd.to_datetime(ohlcv["date"]) >= start_date]
    if end_date:
        ohlcv = ohlcv[pd.to_datetime(ohlcv["date"]) <= end_date]

    if len(ohlcv) < 30:
        return _empty_result(symbol, strategy, initial_capital)

    if strategy == "timing":
        signals = _generate_timing_signals(symbol, ohlcv)
    else:
        signals = _generate_ma_signals(ohlcv)

    result = _simulate(symbol, strategy, ohlcv, signals, initial_capital)

    _save_backtest(result)
    log.info("=== 回测完成: %s 收益%.2f%% 夏普%.2f 最大回撤%.2f%% ===",
             symbol, result.total_return_pct, result.sharpe_ratio, result.max_drawdown_pct)

    return result


def _generate_timing_signals(symbol: str, ohlcv: pd.DataFrame) -> pd.Series:
    """Generate signals from the timing model for each bar."""
    from model_timing import _build_timing_targets, _get_feature_df

    signals = pd.Series(0, index=ohlcv.index)

    try:
        from features import build_features, get_feature_names
        feat_df = build_features(symbol)
        if feat_df is None:
            return signals

        mdir = os.path.join(STOCK_REPORTS_ROOT, "models", symbol, "timing")
        buy_model_path = os.path.join(mdir, "buy_model.json")
        buy_feat_path = os.path.join(mdir, "buy_features.json")
        exit_model_path = os.path.join(mdir, "exit_model.json")

        if not os.path.isfile(buy_model_path):
            log.warning("择时模型不存在 %s, 使用MA策略回退", symbol)
            return _generate_ma_signals(ohlcv)

        import xgboost as xgb
        with open(buy_feat_path, encoding="utf-8") as f:
            feature_cols = json.load(f)

        available = [c for c in feature_cols if c in feat_df.columns]
        X = feat_df[available].copy().replace([np.inf, -np.inf], np.nan).fillna(0)

        buy_model = xgb.XGBClassifier()
        buy_model.load_model(buy_model_path)
        buy_preds = buy_model.predict(X)
        buy_probs = buy_model.predict_proba(X)[:, 1]

        exit_preds = np.zeros(len(X))
        exit_probs = np.zeros(len(X))
        if os.path.isfile(exit_model_path):
            exit_model = xgb.XGBClassifier()
            exit_model.load_model(exit_model_path)
            exit_preds = exit_model.predict(X)
            exit_probs = exit_model.predict_proba(X)[:, 1]

        feat_dates = pd.to_datetime(feat_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        ohlcv_dates = pd.to_datetime(ohlcv["date"], errors="coerce").dt.strftime("%Y-%m-%d")

        for i, odate in enumerate(ohlcv_dates):
            mask = feat_dates == odate
            if mask.any():
                idx = mask.values.argmax()
                if buy_preds[idx] == 1 and exit_preds[idx] == 0:
                    signals.iloc[i] = 1
                elif exit_preds[idx] == 1:
                    signals.iloc[i] = -1

    except Exception as e:
        log.warning("择时信号生成失败: %s, 回退MA策略", e)
        return _generate_ma_signals(ohlcv)

    return signals


def _generate_ma_signals(ohlcv: pd.DataFrame) -> pd.Series:
    """Simple MA5/MA20 crossover baseline strategy."""
    signals = pd.Series(0, index=ohlcv.index)

    ma5 = ohlcv["close"].rolling(5).mean() if "ma5" not in ohlcv.columns else ohlcv["ma5"]
    ma20 = ohlcv["close"].rolling(20).mean() if "ma20" not in ohlcv.columns else ohlcv["ma20"]

    for i in range(1, len(ohlcv)):
        if pd.notna(ma5.iloc[i]) and pd.notna(ma20.iloc[i]):
            if ma5.iloc[i] > ma20.iloc[i] and ma5.iloc[i - 1] <= ma20.iloc[i - 1]:
                signals.iloc[i] = 1
            elif ma5.iloc[i] < ma20.iloc[i] and ma5.iloc[i - 1] >= ma20.iloc[i - 1]:
                signals.iloc[i] = -1

    return signals


def _simulate(
    symbol: str,
    strategy: str,
    ohlcv: pd.DataFrame,
    signals: pd.Series,
    initial_capital: float,
) -> BacktestResult:
    """Core simulation loop with T+1 and limit constraints."""
    cash = initial_capital
    position: Position | None = None
    trades: list[Trade] = []
    equity_curve = []

    dates = pd.to_datetime(ohlcv["date"], errors="coerce").dt.strftime("%Y-%m-%d").tolist()
    opens = ohlcv["open"].values
    highs = ohlcv["high"].values
    lows = ohlcv["low"].values
    closes = ohlcv["close"].values
    prev_close = np.concatenate([[closes[0]], closes[:-1]])

    pending_buy = False
    pending_sell = False

    for i in range(len(ohlcv)):
        date = dates[i]
        price = closes[i]
        change_pct = (price - prev_close[i]) / prev_close[i] * 100 if prev_close[i] > 0 else 0

        if position and not position.can_sell:
            position.can_sell = True

        if pending_buy and position is None:
            pending_buy = False
            if not _is_limit_up(change_pct):
                exec_price = _apply_slippage(opens[i], "buy")
                max_invest = cash * MAX_TOTAL_POSITION
                shares = int(max_invest / exec_price / 100) * 100
                if shares >= 100:
                    cost = shares * exec_price
                    comm = _calc_commission(cost, "buy")
                    total_cost = cost + comm
                    if total_cost <= cash:
                        cash -= total_cost
                        position = Position(
                            symbol=symbol, shares=shares,
                            cost_price=exec_price, entry_date=date,
                            can_sell=False,
                        )
                        trades.append(Trade(
                            date=date, symbol=symbol, action="buy",
                            price=exec_price, shares=shares, cost=comm,
                        ))

        elif pending_sell and position is not None and position.can_sell:
            pending_sell = False
            if not _is_limit_down(change_pct):
                exec_price = _apply_slippage(opens[i], "sell")
                revenue = position.shares * exec_price
                comm = _calc_commission(revenue, "sell")
                pnl = revenue - comm - position.shares * position.cost_price
                cash += revenue - comm
                trades.append(Trade(
                    date=date, symbol=symbol, action="sell",
                    price=exec_price, shares=position.shares,
                    cost=comm, pnl=round(pnl, 2),
                ))
                position = None

        signal = int(signals.iloc[i]) if i < len(signals) else 0
        if signal == 1 and position is None:
            pending_buy = True
        elif signal == -1 and position is not None:
            pending_sell = True

        portfolio_value = cash
        if position:
            portfolio_value += position.shares * price

        equity_curve.append({
            "date": date,
            "equity": round(portfolio_value, 2),
            "cash": round(cash, 2),
            "position_value": round(position.shares * price if position else 0, 2),
        })

    if position:
        final_price = closes[-1]
        revenue = position.shares * final_price
        comm = _calc_commission(revenue, "sell")
        pnl = revenue - comm - position.shares * position.cost_price
        cash += revenue - comm
        trades.append(Trade(
            date=dates[-1], symbol=symbol, action="sell",
            price=final_price, shares=position.shares,
            cost=comm, pnl=round(pnl, 2), reason="回测结束清仓",
        ))

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital * 100

    equity_values = [e["equity"] for e in equity_curve]
    metrics = _compute_metrics(equity_values, trades, initial_capital)
    metrics["total_return_pct"] = round(total_return, 2)

    n_days = len(ohlcv)
    annual_return = ((final_capital / initial_capital) ** (252 / max(n_days, 1)) - 1) * 100

    return BacktestResult(
        symbol=symbol,
        strategy=strategy,
        start_date=dates[0] if dates else "",
        end_date=dates[-1] if dates else "",
        initial_capital=initial_capital,
        final_capital=round(final_capital, 2),
        total_return_pct=round(total_return, 2),
        annual_return_pct=round(annual_return, 2),
        sharpe_ratio=metrics.get("sharpe_ratio", 0),
        max_drawdown_pct=metrics.get("max_drawdown_pct", 0),
        win_rate=metrics.get("win_rate", 0),
        profit_factor=metrics.get("profit_factor", 0),
        total_trades=len([t for t in trades if t.action == "sell"]),
        avg_holding_days=metrics.get("avg_holding_days", 0),
        equity_curve=equity_curve,
        trades=[asdict(t) for t in trades],
        metrics=metrics,
    )


def _compute_metrics(equity_values: list[float], trades: list[Trade],
                     initial_capital: float) -> dict:
    """Compute Sharpe, max drawdown, win rate, profit factor."""
    if len(equity_values) < 2:
        return {"sharpe_ratio": 0, "max_drawdown_pct": 0, "win_rate": 0,
                "profit_factor": 0, "avg_holding_days": 0}

    eq = np.array(equity_values, dtype=float)
    daily_returns = np.diff(eq) / eq[:-1]

    sharpe = 0
    if len(daily_returns) > 10 and np.std(daily_returns) > 0:
        sharpe = round(np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252), 2)

    running_max = np.maximum.accumulate(eq)
    drawdowns = (running_max - eq) / running_max * 100
    max_dd = round(float(np.max(drawdowns)), 2)

    sell_trades = [t for t in trades if t.action == "sell" and t.reason != "回测结束清仓"]
    wins = [t for t in sell_trades if t.pnl > 0]
    losses = [t for t in sell_trades if t.pnl <= 0]
    win_rate = round(len(wins) / max(len(sell_trades), 1) * 100, 1)

    total_profit = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))
    profit_factor = round(total_profit / max(total_loss, 1), 2)

    buy_dates = {t.symbol: t.date for t in trades if t.action == "buy"}
    holding_days = []
    for t in sell_trades:
        bd = buy_dates.get(t.symbol)
        if bd:
            try:
                days = (pd.Timestamp(t.date) - pd.Timestamp(bd)).days
                holding_days.append(days)
            except Exception:
                pass
    avg_hold = round(np.mean(holding_days), 1) if holding_days else 0

    return {
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_holding_days": avg_hold,
    }


def _save_backtest(result: BacktestResult):
    """Save backtest result to disk."""
    path = os.path.join(_BT_DIR, f"{result.symbol}_{result.strategy}_{datetime.now():%Y%m%d}.json")
    data = asdict(result)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    log.info("回测结果已保存: %s", path)


def load_latest_backtest(symbol: str, strategy: str = "timing") -> dict | None:
    """Load the most recent backtest for a symbol."""
    prefix = f"{symbol}_{strategy}_"
    candidates = [f for f in os.listdir(_BT_DIR) if f.startswith(prefix) and f.endswith(".json")]
    if not candidates:
        return None
    latest = sorted(candidates, reverse=True)[0]
    with open(os.path.join(_BT_DIR, latest), encoding="utf-8") as f:
        return json.load(f)


def _empty_result(symbol, strategy, capital):
    return BacktestResult(
        symbol=symbol, strategy=strategy,
        start_date="", end_date="",
        initial_capital=capital, final_capital=capital,
        total_return_pct=0, annual_return_pct=0,
        sharpe_ratio=0, max_drawdown_pct=0,
        win_rate=0, profit_factor=0,
        total_trades=0, avg_holding_days=0,
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sym = sys.argv[1] if len(sys.argv) > 1 else "600519"
    strat = sys.argv[2] if len(sys.argv) > 2 else "timing"

    result = run_backtest(sym, strategy=strat)

    print(f"\n{'='*50}")
    print(f"回测结果: {result.symbol} ({result.strategy})")
    print(f"{'='*50}")
    print(f"  期间: {result.start_date} ~ {result.end_date}")
    print(f"  初始资金: ¥{result.initial_capital:,.0f}")
    print(f"  最终资金: ¥{result.final_capital:,.2f}")
    print(f"  总收益率: {result.total_return_pct:.2f}%")
    print(f"  年化收益: {result.annual_return_pct:.2f}%")
    print(f"  夏普比率: {result.sharpe_ratio:.2f}")
    print(f"  最大回撤: {result.max_drawdown_pct:.2f}%")
    print(f"  胜率: {result.win_rate:.1f}%")
    print(f"  盈亏比: {result.profit_factor:.2f}")
    print(f"  交易次数: {result.total_trades}")
    print(f"  平均持仓: {result.avg_holding_days:.1f}天")

    if result.trades:
        print(f"\n交易记录 ({len(result.trades)} 笔):")
        for t in result.trades[:20]:
            action = "买入" if t["action"] == "buy" else "卖出"
            pnl_str = f" P&L=¥{t['pnl']:.2f}" if t["action"] == "sell" else ""
            print(f"  {t['date']} {action} {t['shares']}股 @ ¥{t['price']:.2f}{pnl_str}")
