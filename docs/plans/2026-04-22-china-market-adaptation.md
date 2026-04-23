---
tags:
  - plan
  - stock
  - china-market
  - completed
category: plan
status: completed
last-updated: 2026-04-22
implemented: 2026-04-22
---

# A股适配 — 资金驱动选股 + 短线择时 + 完整回测

> **For the implementing agent:** Follow this plan phase-by-phase. Each phase is independently useful and can be shipped before starting the next. Verify each step works before moving on.

**Goal:** Redesign the Jarvis stock prediction system to be effective in the Chinese A-share market, where institutional quantitative trading dominates, T+1 settlement restricts day trading, and fundamental analysis alone is insufficient because it is universally visible and already priced in.

**Core Thesis:** In A-shares, follow the "smart money's accumulation phase" — not the rally phase. The key signal is *divergence* between fund flows and price action: money flowing in while price stays flat = accumulation (buy opportunity); money flowing in while price surges = potential distribution (avoid).

**User Requirements:**
- Usage: 中线选股 (2-4 weeks) + 短线择时 (1-5 days entry point)
- Data: Free only (akshare + free Sina/Tencent APIs)
- Backtest: Full simulation with T+1, fees, slippage, limit-up/down constraints
- Holding period: Mixed — screen with medium-term view, time entries with short-term view
- Verification: Win rate, profit factor, max drawdown, Sharpe, equity curve vs CSI 300

---

## Key Concepts — 中国A股 vs 西方市场

| Dimension | Western Markets | Chinese A-Shares | Implication for Our System |
|-----------|-----------------|------------------|---------------------------|
| Settlement | T+0 (day trade OK) | **T+1** (sell earliest next day) | Must model overnight risk; buy signal = commit for ≥1 day |
| Price limits | None (most markets) | **±10% main, ±20% ChiNext/STAR, ±30% 北交所** | Limit-up = can't buy; limit-down = can't sell; must simulate |
| Participant mix | Institutional-heavy | **~60% retail volume** but institutions set direction | Retail herding creates exploitable patterns (e.g. chase highs, panic sells) |
| Shorting | Easy | **Restricted** (margin short is expensive, limited stocks) | Market has upward bias; bear signals mostly mean "don't buy" not "short" |
| Northbound capital | N/A | **外资 via 沪深港通** — single most watched flow signal | North money is "smart money" proxy; daily data available free |
| 龙虎榜 | N/A | **Top buyer/seller disclosure** for volatile stocks | Shows institutional vs retail participation; free via akshare |
| 板块轮动 | Sector rotation exists | **Extreme sector rotation** — hot sectors change weekly | Sector fund flow is more important than individual stock fundamentals |
| Manipulation | Regulated | **庄家 (market maker) patterns** still exist in small caps | Need to detect and avoid pump-and-dump setups |

---

## Phase 1: China Market Data Layer

> **New file:** `scripts/stock/china_market_data.py`

### 1.1 Data Sources (all free via akshare)

| Data | akshare Function | Frequency | Cache | Purpose |
|------|-----------------|-----------|-------|---------|
| 北向资金历史 | `stock_hsgt_hist_em(symbol="北向资金")` | Daily | `{CACHE}/.northbound/history.csv` | Market-level smart money direction |
| 个股资金流向 | `stock_individual_fund_flow(stock, market)` | Daily (100 days) | `{DATA}/{symbol}/fund_flow.csv` | Per-stock main force behavior |
| 板块资金流向 | `stock_sector_fund_flow_rank(indicator, sector_type)` | Daily | `{CACHE}/.sector_flow/{date}.json` | Sector rotation detection |
| 龙虎榜-机构席位 | `stock_sina_lhb_jgmx()` | Daily | `{CACHE}/.lhb/{date}.json` | Institutional buying patterns |
| 龙虎榜-机构追踪 | `stock_sina_lhb_jgzz(recent_day="5")` | Daily | `{CACHE}/.lhb/track_{n}d.json` | Persistent institutional interest |
| 融资融券汇总 | `stock_margin_sse(start, end)` | Daily | `{CACHE}/.margin/sse.csv` | Leverage sentiment |
| 涨停池 | `stock_zt_pool_em(date)` | Daily | `{CACHE}/.limit/{date}_zt.json` | Market temperature |
| 跌停池 | `stock_dt_pool_em(date)` | Daily | `{CACHE}/.limit/{date}_dt.json` | Panic level |
| 大盘资金流 | `stock_market_fund_flow()` | Daily | `{CACHE}/.market_flow/history.csv` | Market-wide main force direction |

### 1.2 API Design

```python
class ChinaMarketData:
    """Unified fetcher + cache for China-specific market data."""

    def fetch_northbound(self, days: int = 120) -> pd.DataFrame
    def fetch_stock_fund_flow(self, symbol: str) -> pd.DataFrame
    def fetch_sector_flow(self, sector_type: str = "行业资金流", period: str = "今日") -> pd.DataFrame
    def fetch_lhb_institutional(self, recent_days: int = 5) -> pd.DataFrame
    def fetch_margin_data(self, days: int = 60) -> pd.DataFrame
    def fetch_limit_pool(self, date: str, direction: str = "涨停") -> pd.DataFrame
    def fetch_market_fund_flow(self, days: int = 60) -> pd.DataFrame

    # Derived signals
    def northbound_momentum(self, window: int = 5) -> dict       # N-day net buy trend
    def market_temperature(self, date: str) -> dict               # 涨停/跌停 count ratio
    def sector_rotation_score(self, sector: str) -> float         # Sector heat
    def stock_institutional_activity(self, symbol: str) -> dict   # LHB + fund flow combined
```

### 1.3 Caching Strategy

- All data cached to disk with date-stamped filenames
- `fetch_*` methods check cache freshness (same trading day = skip fetch)
- Market-level data (northbound, sector, LHB) fetched once per run
- Per-stock data fetched on demand (during scanner or analysis)

### 1.4 Tasks

| # | Task | Verification |
|---|------|-------------|
| 1.1 | Create `china_market_data.py` with `ChinaMarketData` class | `python china_market_data.py --test` fetches all 9 data types |
| 1.2 | Implement caching with date-based freshness check | Second run reads from cache, no network calls |
| 1.3 | Implement derived signal methods | Unit test: `northbound_momentum()` returns dict with `trend`, `strength`, `consecutive_days` |
| 1.4 | Add `market_temperature()` — 涨停/跌停 ratio as market mood | Returns `{ "zt_count": N, "dt_count": M, "ratio": float, "mood": "hot|normal|cold|panic" }` |

---

## Phase 2: New Feature Engineering

> **Modified file:** `scripts/stock/features.py`
> **New features added alongside existing ones — backward compatible**

### 2.1 New Feature Groups

**资金行为特征 (Fund Flow Features)** — `_add_fund_flow_features(df, symbol)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `ff_main_net_3d` | 3-day sum of main force net inflow | Short-term institutional direction |
| `ff_main_net_10d` | 10-day sum | Medium-term institutional direction |
| `ff_main_pct_3d` | 3-day main force net / total volume | Normalized intensity (not absolute amount) |
| `ff_price_diverge_5d` | 5-day fund inflow rank - 5-day price return rank | **Core: money in but price flat = accumulation** |
| `ff_price_diverge_10d` | 10-day version | Medium-term accumulation signal |
| `ff_super_large_ratio` | Super-large order net / total net | Are institutions (not retail) driving the flow? |

**北向资金特征 (Northbound Features)** — `_add_northbound_features(df)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `nb_net_1d` | Today's northbound net buy (亿元) | Daily smart money direction |
| `nb_net_5d` | 5-day sum | Weekly trend |
| `nb_momentum` | 5-day MA / 20-day MA of northbound net | Acceleration of northbound buying |
| `nb_consecutive` | Consecutive days of net buy (negative if net sell) | Persistence of signal |

**板块轮动特征 (Sector Rotation Features)** — `_add_sector_features(df, symbol)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `sect_rank_today` | Stock's sector fund flow rank (percentile 0-1) | Is this stock's sector "hot"? |
| `sect_rank_5d` | 5-day average sector rank | Persistent sector heat |
| `sect_momentum` | Sector rank improvement over 5 days | Sector heating up = rotation target |

**T+1 约束特征 (Limit & Structure Features)** — `_add_t1_features(df)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `near_limit_up` | `(close - prev_close) / prev_close > 0.09` (main board) | Near limit-up = can't buy (or risky T+1 trap) |
| `near_limit_down` | Change < -0.09 | Near limit-down = can't sell |
| `gap_up_pct` | `(open - prev_close) / prev_close` | Gap-up = overnight sentiment; large gap = risk |
| `overnight_risk` | `(high - close) / close` of previous day | How much intraday gains were given back (T+1 holders lost) |
| `zt_count_sector` | Number of limit-up stocks in same sector today | Sector frenzy level |

**市场情绪特征 (Market Sentiment Features)** — `_add_market_mood_features(df)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `mood_zt_dt_ratio` | 涨停 count / (涨停 + 跌停 count) | Market temperature (1.0 = euphoric, 0.0 = panic) |
| `mood_margin_chg_5d` | 5-day change in total margin balance | Leverage sentiment |
| `mood_north_strength` | Northbound 5-day net / 20-day avg volume | Smart money conviction relative to market |

**追高惩罚特征 (Chase-High Penalty Features)** — `_add_chase_penalty_features(df)`

| Feature Name | Calculation | Rationale |
|-------------|-------------|-----------|
| `penalty_consec_up` | Count of consecutive up days (negative = down) | ≥3 consecutive up = chase risk |
| `penalty_dist_ma20_pct` | `(close - ma20) / ma20 * 100` | >10% above MA20 = overextended |
| `penalty_rsi_with_outflow` | `rsi_14 > 70 AND ff_main_net_3d < 0` | Overbought + money leaving = top signal |
| `penalty_volume_diverge` | Price up + volume declining over 3 days | Rising on declining volume = weak rally |

### 2.2 Feature Selection Update

Current `_get_feature_columns()` auto-selects by 50% non-null + exclusion list. New additions:
- New feature prefixes (`ff_`, `nb_`, `sect_`, `mood_`, `penalty_`) all pass the existing filter
- Fund flow features only available for recent ~100 trading days → may reduce walk-forward window
- Northbound features available from 2014 onward
- For scanner (no per-stock fund flow yet), only use market-level features

### 2.3 Tasks

| # | Task | Verification |
|---|------|-------------|
| 2.1 | Add `_add_fund_flow_features()` using `ChinaMarketData` | DataFrame gains 6 `ff_*` columns with <30% null |
| 2.2 | Add `_add_northbound_features()` | DataFrame gains 4 `nb_*` columns |
| 2.3 | Add `_add_sector_features()` | DataFrame gains 3 `sect_*` columns |
| 2.4 | Add `_add_t1_features()` | DataFrame gains 5 T+1-related columns |
| 2.5 | Add `_add_market_mood_features()` | DataFrame gains 3 `mood_*` columns |
| 2.6 | Add `_add_chase_penalty_features()` | DataFrame gains 4 `penalty_*` columns |
| 2.7 | Ensure backward compatibility — old features unchanged, new ones additive | Existing `build_features()` still works without china_market_data |

---

## Phase 3: Scanner Redesign — 资金驱动选股

> **Modified file:** `scripts/stock/scanner.py`

### 3.1 New Layer 1: Quantitative Screening (replaces PE/turnover filter)

**Current:** PE 0-80, turnover ≥ 0.5%, amount ≥ 30M, simple score.
**New:** Fund-flow-driven screening.

```
Pass Criteria (ALL must pass):
├── NOT ST / *ST
├── NOT 停牌 or 涨跌停封板
├── 成交额 ≥ 50,000,000 (liquidity floor, raised from 30M)
├── AT LEAST ONE "smart money" signal:
│   ├── 北向资金 3日净买入 > 0 (market-level, applied to all stocks in northbound universe)
│   ├── OR 所在板块 fund flow rank top 30% (sector is hot)
│   ├── OR 龙虎榜近5日出现机构净买入 (institutional interest confirmed)
│   └── OR 主力资金 3日连续净流入 (per-stock fund flow)
└── NOT in "chase-high" zone:
    ├── 涨跌幅 today < 7% (not already surging)
    └── 连涨天数 < 4 (not in a streak)

Score_L1 = smart_money_signal_count * 20
         + sector_heat_score * 0.3
         + liquidity_score (log(amount) normalized) * 0.2
```

**Cap:** Top 150 by score_L1 (increased from 100 to allow more fund-flow candidates).

### 3.2 New Layer 2: Multi-Factor Scoring

**Current:** Fundamental 35% + Technical 25% + Sentiment 15% + L1 15% + Valuation 10%.
**New:** Fund-flow-dominant with chase-high penalty.

```
Score Components:
├── 资金行为因子 (40%)
│   ├── 吸筹信号 (15%): Fund inflow 3d > 0 AND price change 3d < 2%
│   │   → Scoring: continuous_inflow_days * 10 + abs(inflow_amount_rank) * 5
│   ├── 主力净流入强度 (10%): ff_main_pct_3d percentile rank
│   │   → BUT penalized if price already up > 5% in same period
│   ├── 筹码/龙虎榜质量 (10%): LHB institutional net buy (non-涨停 day = higher score)
│   │   → Scoring: inst_buy > inst_sell scores 80-100; inst on limit-up day scores only 30-50
│   └── 北向资金 (5%): Stock in northbound top buy list (binary bonus)
│
├── 动量因子 (25%)
│   ├── 相对强弱 (10%): 20-day return rank within sector (percentile)
│   ├── 趋势结构 (10%): MA5 > MA10 > MA20 (均线多头排列) scores 80-100
│   │   → MA5 < MA20 but close > MA60 (长线支撑) scores 40-60
│   └── 放量突破 (5%): Volume > 1.5x vol_ma20 AND close > recent 20d high
│       → Score 80 if fresh breakout; 30 if already 3+ days above
│
├── 技术因子 (20%)
│   ├── 波动率收窄 + 即将突破 (8%): bb_width < 20-day avg AND close near bb_upper
│   ├── MACD 底背离 (7%): Price lower low BUT MACD higher low (reversal signal)
│   └── 回踩支撑 (5%): Price near MA20 support + volume shrinking (healthy pullback)
│
├── 基本面安全垫 (15%) — 只做排除，不做选择
│   ├── ROE > 5% scores 60-100 (scaled); ROE < 0 scores 0
│   ├── 利润 YoY > 0 = +20 bonus
│   └── PE reasonable (5-50) = +10 bonus; PE > 100 or < 0 = -20 penalty
│
└── 追高惩罚 (negative deductions)
    ├── 连涨 ≥ 3天 且 放量 → -15
    ├── 偏离 MA20 > 10% → -10
    ├── RSI > 70 且 资金流出 → -20
    └── 龙虎榜 "游资席位" (non-institutional) → -5

Final Score_L2 = weighted_sum + penalty (clamped 0-100)
```

### 3.3 Layer 3: LLM (adjusted prompt)

Change the LLM prompt to emphasize:
- Fund flow context (provide fund flow summary, not just PE/fundamental)
- Sector rotation context (is this sector heating up or cooling?)
- T+1 risk assessment (overnight gap risk, limit-up trap)
- Explicit instruction: penalize stocks that have already rallied significantly

Prompt template key additions:
```
你是一个A股量化分析师。请基于以下数据判断该股是否值得在 T+1 约束下买入：

资金面：
- 主力资金3日净流入: {ff_3d} 万元（{ff_trend}）
- 北向资金: {nb_status}
- 龙虎榜: {lhb_summary}
- 板块资金排名: {sector_rank}

注意事项：
- 如果股票已连涨3天以上或偏离均线过远，请降低评分
- 如果主力资金流入但价格未涨（可能在吸筹），请提高评分
- T+1意味着买入后至少持有到明天，请评估隔夜风险
```

### 3.4 Tasks

| # | Task | Verification |
|---|------|-------------|
| 3.1 | Rewrite Layer 1 screening with fund-flow criteria | Scan returns stocks with smart_money_signal, not just PE filter |
| 3.2 | Rewrite Layer 2 scoring (40% fund + 25% momentum + 20% tech + 15% fundamental - penalties) | Score_L2 distribution: mean ~50, not clustering at extremes |
| 3.3 | Add chase-high penalty deductions | Stocks with 3+ consecutive up days get measurably lower scores |
| 3.4 | Update Layer 3 LLM prompt with fund flow context | LLM response mentions 资金面 and T+1 risk |
| 3.5 | Fix existing RSI bug: scanner checks `"RSI" in df.columns` but indicator creates `rsi_14` | RSI > 75 penalty actually triggers |

---

## Phase 4: Timing Model — 双模型择时

> **New file:** `scripts/stock/model_timing.py`

### 4.1 Model A: Buy Signal (Binary Classification)

**Target Definition:**
```python
# "Opportunity" = price rises ≥ 3% within next 3 trading days (measured from next open, T+1 constraint)
future_max_high = df['high'].rolling(3).max().shift(-3)  # max high in next 3 days
target_buy = ((future_max_high - df['open'].shift(-1)) / df['open'].shift(-1) * 100 >= 3.0).astype(int)
# Using next-day OPEN (not today's close) because T+1 means you buy at next open
```

**Feature Emphasis (reuses features from Phase 2):**
- Primary: `ff_price_diverge_5d`, `ff_main_pct_3d`, `penalty_*` features
- Secondary: `nb_momentum`, `sect_rank_today`, `mood_zt_dt_ratio`
- Technical: `dist_ma20`, `bb_width`, `rsi_14`, `ret_3d` (recent pullback)

**Model:** XGBClassifier, walk-forward validation (same scheme as existing, but 3-day test window).

**Ideal trigger pattern (what the model should learn):**
```
✅ 趋势基础: close > MA20 (中线向上)
✅ 回踩确认: 近3日回踩 MA5/MA10, 未破 MA20
✅ 资金未撤: 回踩期间 ff_main_net_3d > -30% of prior inflow
✅ 缩量企稳: volume_ratio < 0.7 during pullback, recovering
✅ 板块支持: sect_rank_today > 0.5 (sector in top half)
```

### 4.2 Model B: Exit Signal (Stop-Loss / Take-Profit)

**Target Definition:**
```python
# "Need exit" = max drawdown from entry exceeds 5% within next 5 days
future_min_low = df['low'].rolling(5).min().shift(-1)  # min low in next 5 days (starting T+1)
entry_price = df['open'].shift(-1)  # T+1 open as entry
target_exit = ((entry_price - future_min_low) / entry_price * 100 >= 5.0).astype(int)
# 1 = dangerous (will draw down >5%), 0 = safe to hold
```

**Feature Emphasis:**
- Volatility: `atr_pct`, `daily_range_pct`, `volatility_20d`
- Reversal signals: `penalty_rsi_with_outflow`, `penalty_volume_diverge`
- Market mood: `mood_zt_dt_ratio`, `mood_margin_chg_5d`
- Gap risk: `gap_up_pct` history, `overnight_risk`

### 4.3 Combined Signal Logic

```python
def generate_timing_signal(symbol: str) -> dict:
    buy_prob = model_buy.predict_proba(X_latest)[0][1]    # probability of 3%+ gain
    exit_prob = model_exit.predict_proba(X_latest)[0][1]  # probability of 5%+ drawdown

    if buy_prob > 0.6 and exit_prob < 0.3:
        signal = "买入"
        confidence = "high" if buy_prob > 0.7 else "medium"
    elif buy_prob > 0.5 and exit_prob < 0.4:
        signal = "观望偏多"        # lean bullish but not confident
    elif exit_prob > 0.6:
        signal = "回避"            # high drawdown risk
    else:
        signal = "观望"            # no clear signal

    return {
        "signal": signal,
        "buy_probability": buy_prob,
        "exit_probability": exit_prob,
        "confidence": confidence,
        "suggested_entry": support_price,     # from technical_analysis
        "suggested_stop_loss": stop_price,    # ATR-based or support-based
        "suggested_take_profit": target_price # resistance-based
    }
```

### 4.4 Tasks

| # | Task | Verification |
|---|------|-------------|
| 4.1 | Implement `TimingModelBuy` with binary target (3% in 3 days from T+1 open) | Walk-forward accuracy > random (>50%) |
| 4.2 | Implement `TimingModelExit` with binary target (5% drawdown) | Exit model catches >60% of major drops |
| 4.3 | Implement `generate_timing_signal()` combining both models | Returns structured signal dict |
| 4.4 | Save models under `{MODELS}/{symbol}/timing_buy.xgb` and `timing_exit.xgb` | Models persist and reload |

---

## Phase 5: Backtest Engine

> **New file:** `scripts/stock/backtest_engine.py`

### 5.1 A-Share Constraints

```python
@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    commission_rate: float = 0.00025     # 万2.5 (买+卖各收)
    stamp_tax_rate: float = 0.0005       # 印花税 万5 (卖出单边)
    slippage_rate: float = 0.001         # 0.1% 滑点
    max_position_pct: float = 0.20       # 单只最多 20% 仓位
    max_positions: int = 5               # 最多持有 5 只
    min_trade_amount: float = 100        # 最小交易单位 1手=100股
```

### 5.2 T+1 and Limit Enforcement

```python
class AShareBacktester:
    def can_buy(self, symbol: str, date: str, price: float) -> bool:
        """Check if buying is possible."""
        # Cannot buy if: stock hit limit-up (涨停封板)
        if self._is_limit_up(symbol, date): return False
        # Cannot buy if: stock is suspended
        if self._is_suspended(symbol, date): return False
        # Cannot buy if: would exceed max_position_pct or max_positions
        if self._would_exceed_limits(symbol, price): return False
        return True

    def can_sell(self, symbol: str, date: str) -> bool:
        """Check if selling is possible."""
        # T+1: cannot sell if bought today
        if self._bought_today(symbol, date): return False
        # Cannot sell if: stock hit limit-down (跌停封板)
        if self._is_limit_down(symbol, date): return False
        return True

    def execute_trade(self, symbol, date, direction, price):
        """Execute with slippage and fees."""
        actual_price = price * (1 + self.config.slippage_rate) if direction == 'buy' \
                       else price * (1 - self.config.slippage_rate)
        # Round to lot size (100 shares)
        shares = (available_capital / actual_price // 100) * 100
        commission = max(actual_price * shares * self.config.commission_rate, 5.0)  # 最低5元
        stamp_tax = actual_price * shares * self.config.stamp_tax_rate if direction == 'sell' else 0
        ...
```

### 5.3 Strategy Interface

```python
class Strategy(ABC):
    @abstractmethod
    def on_bar(self, date: str, market_data: dict, portfolio: Portfolio) -> list[Order]:
        """Called for each trading day. Return list of buy/sell orders."""
        pass

class ScannerTimingStrategy(Strategy):
    """Combines Phase 3 scanner (selection) + Phase 4 timing (entry/exit)."""

    def on_bar(self, date, market_data, portfolio):
        orders = []
        # Check exit signals for existing positions
        for symbol in portfolio.positions:
            exit_signal = self.timing_model.predict_exit(symbol, date)
            if exit_signal > 0.6:
                orders.append(SellOrder(symbol, reason="exit_model"))

        # Check buy signals for scanner watchlist
        if portfolio.available_slots > 0:
            candidates = self.scanner.get_cached_results(date)
            for stock in candidates:
                buy_signal = self.timing_model.predict_buy(stock.symbol, date)
                if buy_signal > 0.6:
                    orders.append(BuyOrder(stock.symbol, reason="timing_buy"))
        return orders
```

### 5.4 Output Metrics

```python
@dataclass
class BacktestResult:
    # Performance
    total_return_pct: float           # 总收益率
    annual_return_pct: float          # 年化收益率
    benchmark_return_pct: float       # 基准（沪深300）收益率
    excess_return_pct: float          # 超额收益

    # Risk
    max_drawdown_pct: float           # 最大回撤
    max_drawdown_duration_days: int   # 最大回撤持续天数
    sharpe_ratio: float               # 夏普比率 (无风险利率 2.5%)
    sortino_ratio: float              # 索提诺比率
    calmar_ratio: float               # 卡尔马比率

    # Trade Statistics
    total_trades: int                 # 总交易次数
    win_rate_pct: float               # 胜率
    profit_factor: float              # 盈亏比 (总盈利/总亏损)
    avg_holding_days: float           # 平均持仓天数
    avg_win_pct: float                # 平均盈利幅度
    avg_loss_pct: float               # 平均亏损幅度

    # Time Series
    equity_curve: pd.Series           # 净值曲线
    benchmark_curve: pd.Series        # 基准净值曲线
    monthly_returns: pd.Series        # 月度收益
    trade_log: pd.DataFrame           # 每笔交易明细

    def to_report(self) -> str:
        """Generate Chinese markdown report."""
```

### 5.5 Tasks

| # | Task | Verification |
|---|------|-------------|
| 5.1 | Implement `BacktestConfig` and `AShareBacktester` core loop | Runs without error on 1 year of data for 1 stock |
| 5.2 | Implement T+1 enforcement | Selling on buy day raises/blocks; selling T+1 works |
| 5.3 | Implement limit-up/down blocking | Trades correctly blocked when price hits daily limit |
| 5.4 | Implement fee model (commission + stamp tax + slippage) | Fees match manual calculation for known trade |
| 5.5 | Implement `BacktestResult` with all metrics | Sharpe, max drawdown, equity curve all computed correctly |
| 5.6 | Implement `ScannerTimingStrategy` connecting scanner + timing model | Full backtest: scanner selects, timing enters, exit model exits |
| 5.7 | Add CSI 300 benchmark comparison | Equity curve plotted against CSI 300 |
| 5.8 | Generate trade log with per-trade P&L | CSV export: symbol, buy_date, buy_price, sell_date, sell_price, return%, holding_days |

---

## Phase 6: UI & API Integration

> **Modified file:** `scripts/rag/agent.py`

### 6.1 New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stock/scan/start` | POST | Start scanner (uses new Phase 3 logic) |
| `/api/stock/timing` | POST | Run timing model for a symbol/watchlist |
| `/api/stock/backtest` | POST | Run backtest with specified strategy + date range |
| `/api/stock/backtest/<job_id>` | GET | Poll backtest progress |
| `/api/stock/backtest/results` | GET | Get backtest results (metrics + equity curve data) |

### 6.2 UI Additions

- **回测** button in A股 toolbar → opens backtest config dialog (date range, initial capital, strategy)
- **择时信号** column added to watchlist table (买入 / 观望 / 回避)
- **净值曲线** chart (simple line chart using HTML canvas or lightweight JS lib)
- **交易明细** table with sortable columns

### 6.3 Tasks

| # | Task | Verification |
|---|------|-------------|
| 6.1 | Add backtest API endpoints | POST `/api/stock/backtest` starts job, GET polls |
| 6.2 | Add timing signal to watchlist display | Each watchlist stock shows 买入/观望/回避 |
| 6.3 | Add equity curve visualization | Line chart renders in browser |
| 6.4 | Add trade log table with export | Trade details table + CSV download |

---

## Phase 7: Documentation & Verification

| # | Task | Verification |
|---|------|-------------|
| 7.1 | Update `stock-usage-guide.md` with new features | New sections for 资金选股, 择时信号, 回测 |
| 7.2 | Update `stock-knowledge-guide.md` with new concepts | 北向资金, 龙虎榜, 板块轮动 explained for beginners |
| 7.3 | Create `implementation/stock/china-market-impl.md` | Covers `china_market_data.py` in detail |
| 7.4 | Create `implementation/stock/timing-model-impl.md` | Covers `model_timing.py` in detail |
| 7.5 | Create `implementation/stock/backtest-impl.md` | Covers `backtest_engine.py` in detail |
| 7.6 | Update `implementation/stock/README.md` | Add new files to module map |
| 7.7 | Update `docs-index.md`, `backend-overview.md`, `README.md` | Reflect all new APIs and features |

---

## Implementation Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
 (data)    (features) (scanner)  (timing)  (backtest)  (UI)     (docs)
   ↓          ↓          ↓         ↓          ↓         ↓
  1 day     1 day      1 day     1 day      2 days    1 day    0.5 day
```

Each phase is independently testable. Phase 1 data can be verified standalone. Phase 2 features can be checked with existing XGBoost model. Phase 3 scanner improvement can be tested before timing model exists. Phase 5 backtest can initially use simple moving-average strategy before timing model is connected.

---

## Risk Disclaimer

⚠️ **股市有风险，投资需谨慎。** 本系统仅为学习和研究工具，不构成任何投资建议。
- 任何模型在历史数据上的表现不代表未来收益
- 回测结果存在过拟合风险（尤其是参数优化后）
- A股市场受政策影响极大，模型无法预测政策变化
- 建议先在模拟盘验证至少 3 个月再考虑实盘
