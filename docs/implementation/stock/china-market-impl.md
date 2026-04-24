---
tags:
  - stock
  - implementation
  - china-market
category: implementation
status: current
last-updated: 2026-04-22
---

# China A-Share Market Adaptation — Implementation

## Overview

Three new modules implement A-share specific data acquisition, timing models, and backtesting:

| Module | Purpose | Lines |
|--------|---------|-------|
| `china_market_data.py` | 8 data sources for fund flow, northbound capital, national team ETF, etc | ~850 |
| `model_timing.py` | Dual XGBoost buy/exit signal classifiers | ~350 |
| `backtest_engine.py` | Full simulation with T+1, fees, limit constraints | ~400 |

## china_market_data.py — Data Layer

### Data Sources (all via akshare, free)

| Source | Function | Cache TTL | Key Columns |
|--------|----------|-----------|-------------|
| 北向资金 | `fetch_northbound()` | 8h | 日期, 当日成交净买额 |
| 个股资金流向 | `fetch_stock_fund_flow(symbol)` | 8h | 主力净流入-净额, 超大单净流入-净额 |
| 板块资金流向 | `fetch_sector_flow()` | 6h | 板块名称, 主力净流入 |
| 龙虎榜 | `fetch_lhb_institutional()` | 12h | 代码, 机构买入/卖出 |
| 融资融券 | `fetch_margin_data()` | 12h | 融资余额, 融资买入额 |
| 涨跌停池 | `fetch_limit_pool()` | 12h | 涨停/跌停数量 |
| 大盘资金流 | `fetch_market_fund_flow()` | 8h | 主力净流入 |
| **国家队ETF(上交所)** | `fetch_etf_shares_sse()` | 12h | 基金代码, 基金份额 |
| **国家队ETF(深交所)** | `fetch_etf_shares_szse()` | 12h | 证券代码, 流通份额 |
| **机构持股** | `fetch_institution_holdings()` | 72h | 季度机构(含汇金/社保)持仓 |

### Signal Processors

| Function | Returns | Use Case |
|----------|---------|----------|
| `northbound_momentum()` | net_today, net_5d/20d, momentum, consecutive | Feature: 北向资金动量 |
| `stock_fund_flow_signals(sym)` | main_net_3d/10d, smart_money_phase, accumulation_score | Feature: 聪明钱布局检测 |
| `detect_smart_money_accumulation(sym, df, ...)` | phase/score/detail/divergence | 聪明钱布局期 vs 拉升期 vs 出货期 |
| `sector_rotation_score(name)` | rank_today, rank_5d, is_hot | Scanner Layer 1 |
| `margin_sentiment()` | balance_change_pct, trend | Feature: 杠杆情绪 |
| `market_temperature()` | zt_count, dt_count, ratio, mood | Market mood |
| **`national_team_monitor()`** | etf_snapshot (16只), totals, anomalies | 国家队建仓/撤退信号 |
| **`national_team_trend(days)`** | total_change_pct, trend label | 长期国家队动向 |
| **`national_team_period_stats()`** | 1w/1m/3m changes for total + per-ETF | 多时间窗口监控指标 |
| **`national_team_backfill_history(days)`** | Backfill weekly snapshots from SSE | 历史数据自动回填 |

### National Team ETF Monitoring (国家队)

Tracks 16 core ETFs (9 broad-based + 7 sector) across SSE and SZSE:

**Broad-based (宽基):** 510300/510050/510500/510880/512100/588000/159919/159915/159922
**Sector (行业):** 513050/512010/512880/515030/512480/512660/515790

Features:
- Daily share snapshot with automatic date fallback (tries today, then past 5 trading days)
- Historical snapshot accumulation (up to 365 days) for trend analysis
- **Automatic 90-day history backfill** from SSE on each fetch — samples every 5 trading days, skips dates already in history, normalizes all dates to `YYYY-MM-DD` format
- **Multi-period indicators (1周/1月/3月):** Total broad/sector share changes and per-ETF changes across 3 time windows, with ±3 day tolerance for matching historical snapshots
- Anomaly detection: flags any ETF with >3% share change vs previous snapshot
- Aggregate signals: 大幅增持/温和增持/平稳/温和减持/大幅减持
- Trend analysis: 大规模建仓/持续增持/小幅增持/小幅减持/持续减持/大规模撤退

### Smart Money Accumulation Detection (聪明钱布局检测)

`detect_smart_money_accumulation()` identifies the phase of institutional/smart money activity:

**Phase classification:**

| Phase | Condition | Meaning |
|-------|-----------|---------|
| 布局期 | fund_strength ≥ 50 AND price_chg_5d < 2% | Funds flowing in while price stays flat — **best buy signal** |
| 拉升期 | fund_strength ≥ 40 AND price_chg_5d > 5% | Funds + price both rising — **chase risk, T+1 danger** |
| 出货期 | fund_strength < 20 AND price_chg_5d > 3% | Price up but funds leaving — **distribution, avoid** |
| 观察期 | Moderate fund_strength, mixed price | Signals not yet clear — **watch** |
| 无信号 | fund_strength < 20 | No meaningful flow — **no signal** |

**Scoring logic:**
- `fund_strength` (0-90): weighted sum of 5-day/3-day net inflow positivity, consecutive positive days (≥3, ≥4), main-force percentage
- `price_quiet` (0-50): flat price earns more points (|change| < 1% → +40, < 2% → +30, slight dip → +10)
- `accumulation_score` = 50% × fund_strength + 50% × price_quiet (capped at 100)
- `fund_price_divergence`: fund_strength minus normalized price gain — higher = stronger divergence = stronger accumulation signal

**Integration points:**
- Scanner Layer 2: "布局期" stocks get highest `ff_score` (80+)
- Scanner Layer 3 LLM prompt: phase and detail shown to LLM for ranking
- Comprehensive Report: phase shown with color-coded icon and detail
- A股分析 full analysis: dedicated "资金流向 & 聪明钱分析" section in report

### Caching Strategy

All data cached under `STOCK_CACHE_DIR/.{source}/` with TTL-based freshness check (`_cache_fresh()`).
Stale cache used as fallback when API fails.

## features.py — New Feature Groups (Phase 2)

17 new China-specific features added to the existing 37:

### Fund Flow Features (ff_*)
- `ff_main_net_3d` / `ff_main_net_10d`: Rolling 3/10-day main-force net inflow (date-aligned with OHLCV)
- `ff_main_pct_3d`: Rolling 3-day percentage
- `ff_price_diverge_5d`: Fund inflow rank minus price return rank (divergence = accumulation signal)
- `ff_super_large_ratio`: Super-large order ratio (institutional vs retail)

### Northbound Features (nb_*)
- `nb_net_1d` / `nb_net_5d`: Daily and 5-day northbound net buy
- `nb_momentum`: Short MA / Long MA of northbound flow (>1 = accelerating inflow)
- `nb_consecutive`: Consecutive days of net buy/sell

### T+1 Constraint Features
- `near_limit_up` / `near_limit_down`: Binary flags for near-limit-up/down
- `gap_up_pct`: Overnight gap percentage
- `overnight_risk`: Previous day's high-close spread

### Chase-High Penalty Features
- `penalty_consec_up`: Consecutive up-day streak
- `penalty_dist_ma20_pct`: Distance from MA20 (overextended = dangerous)
- `penalty_rsi_with_outflow`: RSI>70 AND fund outflow (classic trap)
- `penalty_volume_diverge`: Price up but volume declining (weak rally)

### Feature Selection Threshold

China-specific features (`ff_*`, `nb_*`, `mood_*`) use 15% non-null threshold instead of 50%,
because fund flow data only covers ~100 recent trading days out of 500.

## model_timing.py — Dual Signal Model (Phase 4)

### Architecture

Two independent XGBoost binary classifiers:

**Buy Signal Model**
- Target: max(high[t+1..t+3]) / open[t+1] - 1 > 3%
- Meaning: "Will there be a 3%+ gain opportunity in the next 3 trading days?"
- Positive sample rate: ~15% for volatile stocks, ~5% for blue chips

**Exit Signal Model**
- Target: max drawdown from close[t] over [t+1..t+5] > 5%
- Meaning: "Will the stock drop 5%+ from here in the next 5 days?"
- Positive sample rate: ~10%

### Combined Signal Logic

| Buy Model | Exit Model | Final Signal |
|-----------|------------|-------------|
| 1 (buy) | 0 (safe) | **买入** |
| 1 (buy) | 1 (risky) | **观望偏多** |
| 0 (no buy) | 0 (safe) | **观望** |
| 0 (no buy) | 1 (risky) | **回避** |

### Training

- Walk-Forward: 12 rounds, 400-day train window, 5-day test window
- Class imbalance handled via `scale_pos_weight`
- Regularization: `reg_alpha=1.0`, `reg_lambda=2.0`, `min_child_weight=5`
- Models saved to `STOCK_MODELS_DIR/{symbol}/timing/`

### Test Results (600519 贵州茅台)

| Model | Accuracy | Precision | Recall | F1 |
|-------|----------|-----------|--------|-----|
| Buy | 81.7% | 16.7% | 11.1% | 12.5% |
| Exit | 93.3% | 4.2% | 4.2% | 4.2% |

Low F1 expected for blue-chip (stable) stocks. More volatile stocks will show higher signal rates.

## backtest_engine.py — A-Share Backtest (Phase 5)

### Constraints Simulated

| Constraint | Implementation |
|------------|---------------|
| T+1 | `Position.can_sell` flag, set True on day after buy |
| Limit-up block | Cannot buy if change > +9.5% |
| Limit-down block | Cannot sell if change < -9.5% |
| Commission | Buy: 万2.5, Sell: 万2.5 + 千1 stamp tax |
| Slippage | 0.1% applied to execution price |
| Min commission | ¥5 per trade |
| Position sizing | 80% max total exposure |

### Execution Model

Signals from day T are executed at day T+1's **open** price (realistic: you see the signal after close, trade next morning).

### Output Metrics

- Total/annual return
- Sharpe ratio (annualized)
- Max drawdown
- Win rate, profit factor
- Trade log with P&L per trade
- Full equity curve (daily)

### Test Results (600519, 500K capital)

| Strategy | Trades | Return | Sharpe | Max DD |
|----------|--------|--------|--------|--------|
| Timing | 20 | **+13.16%** | 0.53 | - |
| Simple MA | 18 | -28.03% | -1.63 | - |

## scanner.py — Redesigned (Phase 3)

### Changes

**Layer 1**: Added chase-high penalty (-5 for change>6%), pullback bonus (+3 for -5%<change<0%).
Removed stocks at limit-up (涨停 = cannot buy).

**Layer 2**: Fund flow scoring added as 30% weight (was 0%):
- New weights: Fund Flow 30%, Fundamental 25%, Technical 20%, Sentiment 10%, L1 Score 10%, Valuation 5%
- Old weights: Fundamental 35%, Technical 25%, Sentiment 15%, L1 Score 15%, Valuation 10%

**Layer 3 LLM Prompt**: Rewritten to emphasize:
- "聪明钱"吸筹模式 (smart money accumulation)
- T+1 risk awareness
- Anti-chase-high stance
- Fund flow + price divergence as primary signal

## API Endpoints Added (Phase 6)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/stock/timing/train` | Train timing models for all watchlist stocks |
| GET | `/api/stock/timing/status` | Get timing training progress |
| GET | `/api/stock/timing/predict/<symbol>` | Get timing signal for one stock |
| GET | `/api/stock/timing/predict-all` | Get timing signals for all watchlist stocks |
| POST | `/api/stock/backtest/<symbol>` | Run backtest (body: strategy, capital) |
| GET | `/api/stock/backtest/<symbol>` | Get latest backtest result |
| GET | `/api/stock/china-data` | Fetch all China market data summary (incl. national team) |
| GET | `/api/stock/china-data/fund-flow/<symbol>` | Get individual stock fund flow |
| GET | `/api/stock/national-team` | National team ETF share snapshot + trend |

## File Tree (updated: 20 modules)

```
scripts/stock/
├── __init__.py
├── config.py
├── china_market_data.py         ← NEW (Phase 1)
├── fetch_market_data.py
├── watchlist.py
├── hot_sectors.py
├── technical_analysis.py
├── report_technical.py
├── fundamental_analysis.py
├── sentiment.py
├── features.py                  ← MODIFIED (Phase 2, +17 features)
├── model_xgboost.py
├── model_price_predictor.py
├── model_timing.py              ← NEW (Phase 4)
├── prediction_tracker.py
├── market_sentiment.py
├── black_swan_detector.py
├── llm_reasoning.py
├── scanner.py                   ← MODIFIED (Phase 3)
└── backtest_engine.py           ← NEW (Phase 5)
```
