---
tags:
  - plan
  - stock
  - completed
category: plan
status: completed
last-updated: 2026-04-12
---


# Chinese A-Share Stock Prediction — Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next. This is a **large, multi-phase feature** — each phase is independently useful and can be shipped before starting the next.

**Goal:** Add Chinese A-share individual stock prediction capabilities to Jarvis, combining data fetching, technical analysis, fundamental analysis, sentiment analysis, and AI model prediction into an actionable daily workflow.

**Architecture:** A new `scripts/stock/` module with data fetchers, analysis engines, and an AI prediction pipeline. The agent UI gets a new toolbar category "Stock" with buttons for data refresh, analysis views, and prediction reports. Data is stored as JSON/CSV under `C:/reports/stock/` with Qdrant indexing for RAG-based Q&A about market context.

**Tech Stack:** Python (akshare for A-share data, pandas/numpy for analysis, pandas-ta for technical indicators, scikit-learn/XGBoost for ML models), Ollama for LLM-based reasoning, Edge TTS for audio market briefings, ReportLab for PDF reports.

---

## Glossary — Key Concepts Explained

> This section explains every major concept used in this plan. Read this first if you're new to stock analysis and ML prediction.

### Stock Market Basics

| Term | What it means | Why we need it |
|------|---------------|----------------|
| **A-Share (A股)** | Chinese stocks traded on Shanghai (上交所) and Shenzhen (深交所) exchanges, denominated in RMB. This is the main Chinese stock market. | Our prediction target — we're analyzing these stocks. |
| **OHLCV** | Open, High, Low, Close, Volume — the 5 basic data points recorded for each trading day. **Open** = first trade price, **High** = highest price, **Low** = lowest, **Close** = last trade price, **Volume** = total shares traded. | The raw data everything else is built on. Like the "source code" of stock analysis. |
| **Stock Symbol (股票代码)** | A 6-digit code identifying each stock. `6xxxxx` = Shanghai (e.g. 600519 = 贵州茅台), `0xxxxx` = Shenzhen main board, `3xxxxx` = 创业板 (ChiNext, growth stocks), `688xxx` = 科创板 (STAR Market, tech stocks). | We use these codes to fetch data from APIs. |
| **T+1 Settlement** | In China, if you buy a stock today, you can only sell it tomorrow (T+1). Unlike US stocks which allow same-day trading. | Affects prediction strategy — we predict at minimum 1 day ahead. |
| **涨停/跌停 (Limit Up/Down)** | A stock can only move ±10% per day on the main board (±20% on 创业板/科创板). If it hits the limit, trading effectively stops in that direction. | Important for risk modeling — extreme moves are capped. |
| **Trading Hours** | 9:30–11:30 AM and 1:00–3:00 PM (Beijing time), Monday–Friday. | Determines when real-time data is available and when predictions are actionable. |

### Technical Analysis — Reading Price Charts

> **What is technical analysis?** It's the study of past price and volume patterns to predict future price movements. Think of it as "reading the chart" — analysts believe that price patterns repeat because human psychology (fear, greed) repeats.

| Term | What it means | Analogy | Why we use it |
|------|---------------|---------|---------------|
| **Moving Average (均线, MA)** | The average closing price over the last N days. MA5 = average of last 5 days, MA20 = last 20 days, MA250 ≈ 1 year. When plotted on a chart, it creates a smooth line that shows the trend direction. | Like a "smoothed" version of the price — removes daily noise to show the real direction, like a rolling average of your daily step count shows your fitness trend. | The most basic trend indicator. If price is above MA20, the short-term trend is "up". |
| **Golden Cross (金叉)** | When a short-term MA (e.g. MA5) crosses ABOVE a long-term MA (e.g. MA20). | Like when a sprinter overtakes a marathon runner — the short-term momentum is now stronger than the long-term trend. | Classic "buy signal" — suggests upward momentum is building. |
| **Death Cross (死叉)** | Opposite of golden cross — short-term MA crosses BELOW long-term MA. | The sprinter falls behind the marathon runner — momentum is fading. | Classic "sell signal" — suggests downward momentum. |
| **MACD** | Moving Average Convergence Divergence. Measures the difference between two moving averages (12-day and 26-day). Has three parts: MACD line, Signal line, and Histogram (the bar chart). | Like measuring the "acceleration" of a car — not just speed (price) but whether it's speeding up or slowing down. | Shows momentum changes. When MACD crosses above signal line = bullish; below = bearish. |
| **RSI (相对强弱指数)** | Relative Strength Index. A number from 0 to 100 that measures how "overbought" or "oversold" a stock is. Calculated from recent gains vs losses over 14 days. | Like a "tiredness meter" — if RSI > 70, the stock has been running too hard (overbought, might rest/drop). If RSI < 30, it's been beaten down too much (oversold, might bounce). | Helps identify when a stock might reverse direction. |
| **KDJ (随机指标)** | A momentum indicator popular in Chinese markets. K, D, J are three lines (0-100). Similar to RSI but more sensitive to price changes. J line > 100 = overbought, J < 0 = oversold. | Like RSI but with a "turbo" mode — reacts faster to changes, which Chinese traders prefer for short-term trading. | Very commonly used by Chinese retail investors. We include it because our target audience trades A-shares. |
| **Bollinger Bands (布林带)** | Three lines: middle = MA20, upper = MA20 + 2×standard deviation, lower = MA20 − 2×standard deviation. The bands widen when volatility is high and narrow when it's low. | Like a "normal range" band — price usually stays within the bands. When it touches the upper band, it might be too high; lower band, too low. When bands squeeze tight, a big move is coming. | Measures volatility and identifies potential breakout points. |
| **OBV (能量潮)** | On-Balance Volume. Adds volume on "up" days and subtracts volume on "down" days, creating a running total. | Like tracking whether the "crowd" is buying or selling. If OBV is rising while price is flat, smart money might be accumulating — price could follow up. | Volume confirms price moves. A price rise without volume support is weak. |
| **Support/Resistance (支撑/阻力)** | Price levels where a stock tends to stop falling (support) or stop rising (resistance). Based on historical price points where many trades happened. | Like "floors" and "ceilings" — the stock bounces off these levels because many traders have buy/sell orders there. | Key for setting price targets and stop-loss levels. |
| **ATR (平均真实波幅)** | Average True Range. Measures how much a stock typically moves per day (in price terms). | Like measuring the "personality" of a stock — some stocks move ±1% daily (calm), others move ±5% (wild). | Used for risk management — helps size positions and set stop-losses. |
| **Candlestick Patterns (K线形态)** | Specific shapes formed by 1-3 daily candles that suggest future direction. Examples: **Hammer** (long lower shadow = buyers fighting back), **Engulfing** (big candle swallows previous = strong reversal), **Doji** (open ≈ close = indecision). | Like "body language" of the market — specific poses that experienced traders recognize as signals. | Short-term reversal signals. Not reliable alone but useful combined with other indicators. |

### Fundamental Analysis — Evaluating the Business

> **What is fundamental analysis?** It's evaluating a company's actual business health — revenue, profit, debt, growth — to determine if the stock price is fair, cheap, or expensive. Think of it as "reading the company's report card."

| Term | What it means | Analogy | Why we use it |
|------|---------------|---------|---------------|
| **PE Ratio (市盈率)** | Price / Earnings per Share. If a stock costs ¥100 and earns ¥5 per share annually, PE = 20. Means you're paying 20 years of earnings for the stock. | Like the "payback period" — how many years of profit it takes to earn back your investment. Lower PE = cheaper (usually). | The most common valuation metric. PE of 10 is cheap, 50 is expensive (but depends on industry and growth). |
| **PB Ratio (市净率)** | Price / Book Value per Share. Book value = total assets minus total liabilities, divided by shares. PB = 1 means you're paying exactly what the company's net assets are worth. | Like buying a house — PB < 1 means you're paying less than the "material cost" of the company. | Useful for asset-heavy industries (banks, real estate). PB < 1 can signal undervaluation. |
| **ROE (净资产收益率)** | Return on Equity. Net profit / shareholder equity. Measures how efficiently the company uses investor money to generate profit. ROE of 20% means every ¥100 of equity generates ¥20 profit. | Like the "interest rate" on your investment in the company. Higher = management is better at making money with your money. | Warren Buffett's favorite metric. Consistently high ROE (>15%) suggests a quality business. |
| **Revenue (营收)** | Total money the company received from selling products/services. | The "top line" — how much money came in the door. | Shows business scale and market demand. |
| **Net Profit (净利润)** | Revenue minus ALL costs (materials, salaries, taxes, interest, etc.). The actual money the company keeps. | The "bottom line" — what's left after paying everyone. | The ultimate measure of profitability. |
| **YoY Growth (同比增长)** | Year-over-Year growth. This quarter vs same quarter last year. Removes seasonal effects. | Like comparing your salary this April vs last April — fair comparison because both are the same season. | Growth rate matters more than absolute numbers. 30% YoY growth is exciting; -10% is concerning. |
| **Debt Ratio (资产负债率)** | Total liabilities / Total assets. Shows how much of the company is funded by debt vs equity. | Like your personal debt-to-asset ratio. 30% is healthy, 80% is risky — too much debt means vulnerability to interest rate changes or revenue drops. | High debt = high risk. If revenue drops, the company still has to pay interest. |
| **Free Cash Flow (自由现金流)** | Operating cash flow minus capital expenditures. The actual cash the company generates after maintaining/expanding its business. | Like your "disposable income" after paying rent and bills — the money you can actually save or invest. | More reliable than net profit (which can be manipulated with accounting tricks). Positive FCF = healthy business. |
| **PEG Ratio** | PE / Earnings Growth Rate. Adjusts PE for growth. PEG = 1 means fairly valued for its growth; PEG < 1 = undervalued; PEG > 1 = overvalued. | Like comparing price-to-earnings but accounting for speed of growth. A PE of 50 is expensive for a slow grower but cheap for a company growing 60% annually. | Better than PE alone for growth stocks. |
| **Dividend Yield (股息率)** | Annual dividend / Stock price. Shows the "interest" you earn just from holding the stock. | Like a savings account interest rate — 3% yield means you get ¥3 per year for every ¥100 invested, regardless of price changes. | Important for income-focused investors. High yield + stable business = good defensive holding. |

### Sentiment Analysis — Reading the Market's Mood

> **What is sentiment analysis?** Using AI (our Ollama LLM) to read news articles and determine whether the overall tone is positive (bullish), negative (bearish), or neutral about a stock. It's like having a robot read thousands of news articles and tell you "people are excited/worried about this stock."

| Term | What it means | Why we use it |
|------|---------------|----------------|
| **Bullish (看涨/多头)** | Positive outlook — expecting price to go up. | When news sentiment is bullish, it often precedes price increases (but not always). |
| **Bearish (看跌/空头)** | Negative outlook — expecting price to go down. | Bearish sentiment can signal upcoming drops. |
| **Sentiment Score** | A number from -1.0 (very bearish) to +1.0 (very bullish). We aggregate scores from multiple news articles into a daily score. | Quantifies the "mood" so we can track it over time and feed it into ML models. |
| **Sentiment Shift** | A sudden change in sentiment direction (e.g. from +0.5 to -0.3 in one day). | Often signals important events — earnings surprise, policy change, scandal. These shifts can precede big price moves. |

### AI/ML Prediction — The "Brain" of the System

> **What is ML prediction?** We use machine learning (specifically XGBoost) to find patterns in historical data that humans might miss. The model learns from thousands of past examples: "when these indicators looked like THIS, the stock went UP 70% of the time." Then it applies those patterns to today's data.

| Term | What it means | Analogy | Why we use it |
|------|---------------|---------|---------------|
| **Feature (特征)** | A single input variable to the ML model. Examples: today's RSI value, PE ratio, sentiment score, volume change. We combine ~30-50 features into a "feature vector" for each prediction. | Like the "ingredients" in a recipe — each feature is one ingredient, and the model learns the right recipe (combination) for predicting stock direction. | The model needs structured input data. Better features = better predictions. |
| **Feature Engineering** | The process of creating useful features from raw data. E.g., instead of raw price, we calculate "5-day return" or "distance from MA20." | Like a chef preparing ingredients — you don't throw a whole chicken into the pot; you cut, season, and prepare it first. | The most important step in ML. Good features matter more than fancy algorithms. |
| **XGBoost** | eXtreme Gradient Boosting. A powerful ML algorithm that builds many small "decision trees" and combines them. Each tree corrects the mistakes of the previous ones. State-of-the-art for tabular data (like our stock features). | Like a team of consultants — each one is mediocre alone, but together they correct each other's blind spots and produce excellent advice. | Best algorithm for structured/tabular data. Fast, accurate, handles missing data well. Used by many winning Kaggle competition solutions. |
| **Walk-Forward Validation** | Training the model on data up to date X, then testing on date X+1 to X+5. Then moving forward: train up to X+1, test X+2 to X+6. Simulates real-world usage where you only have past data. | Like a driving test where you practice on old roads, then test on new roads you've never seen. If you just tested on roads you practiced on, you'd get a false sense of confidence. | Prevents "cheating" — ensures the model can actually predict the future, not just memorize the past. |
| **Overfitting (过拟合)** | When the model memorizes historical patterns too precisely and fails on new data. Like a student who memorizes exam answers but can't solve new problems. | Like memorizing the answers to last year's exam — you'll ace it if the same questions appear, but fail if they're different. | The biggest risk in stock prediction. We use walk-forward validation and feature selection to prevent it. |
| **Confidence Calibration** | Adjusting the model's confidence scores so that "80% confident" actually means it's right 80% of the time. Raw model outputs are often overconfident. | Like a weather forecast — if it says "80% chance of rain" and it actually rains 80% of those times, it's well-calibrated. | We need honest confidence scores to make good trading decisions. |
| **Feature Importance** | Which features the model relies on most for predictions. XGBoost can rank features by how much they contribute to accuracy. | Like asking the team of consultants "which factor mattered most in your recommendation?" | Helps us understand WHY the model predicts what it does, and which data sources are most valuable. |
| **LLM Reasoning Layer** | After XGBoost makes a numerical prediction, we feed all the analysis (technical, fundamental, sentiment, ML prediction) to our Ollama LLM and ask it to write a human-readable explanation with actionable advice. | Like having a senior analyst review all the data and write a report in plain language — "Based on strong earnings, bullish sentiment, and the golden cross signal, I recommend buying with a target of ¥XX." | Makes the output understandable and actionable. Raw numbers aren't useful without interpretation. |

### Data Sources & Tools

| Tool | What it is | Why we chose it |
|------|------------|-----------------|
| **akshare** | Open-source Python library for Chinese financial data. Provides real-time quotes, historical prices, financial statements, news, sector data — all for free, no API key needed. | Best free data source for A-shares. Actively maintained, covers everything we need. |
| **pandas-ta** | Python library that calculates 130+ technical indicators from price/volume data. Pure Python, no C compilation needed. | Saves us from implementing indicators manually. Drop-in: `df.ta.macd()`, `df.ta.rsi()`. |
| **XGBoost** | Industry-standard gradient boosting library. Fast training, handles missing data, built-in feature importance. | Best choice for tabular prediction tasks. Used by quant funds and Kaggle winners. |
| **scikit-learn** | Python ML toolkit for preprocessing, model evaluation, and utilities. | Standard companion to XGBoost for data splitting, scaling, metrics. |

---

## Phase 0: Foundation & Data Infrastructure

### Task 0.1: Project Structure & Dependencies

**Files:**
- Create: `scripts/stock/__init__.py`
- Create: `scripts/stock/config.py`
- Create: `scripts/stock/fetch_market_data.py`
- Modify: `scripts/config.py` (add stock paths)

**Step 1: Create stock config**

```python
# scripts/stock/config.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import JARVIS_ROOT

STOCK_REPORTS_ROOT = os.environ.get("STOCK_REPORTS_ROOT", "C:/reports/stock")
STOCK_DATA_DIR = os.path.join(STOCK_REPORTS_ROOT, "data")
STOCK_MODELS_DIR = os.path.join(STOCK_REPORTS_ROOT, "models")
STOCK_CACHE_DIR = os.path.join(STOCK_REPORTS_ROOT, ".cache")

WATCHLIST_FILE = os.path.join(STOCK_REPORTS_ROOT, "watchlist.json")
PORTFOLIO_FILE = os.path.join(STOCK_REPORTS_ROOT, "portfolio.json")

for d in [STOCK_DATA_DIR, STOCK_MODELS_DIR, STOCK_CACHE_DIR]:
    os.makedirs(d, exist_ok=True)
```

**Step 2: Install core dependencies**

Run: `pip install akshare pandas-ta xgboost scikit-learn`

- `akshare` — open-source A-share data API (real-time quotes, historical OHLCV, financial statements, news)
- `pandas-ta` — technical indicators (no C dependency unlike ta-lib)
- `xgboost` / `scikit-learn` — ML models for prediction

**Step 3: Verify akshare works**

Run: `python -c "import akshare as ak; df = ak.stock_zh_a_spot_em(); print(df.head())"`
Expected: DataFrame with current A-share stock data

---

### Task 0.2: Stock Data Fetcher

**Files:**
- Create: `scripts/stock/fetch_market_data.py`

**Purpose:** Fetch historical OHLCV data, real-time quotes, and financial data for watchlist stocks.

**How it works:** akshare connects to Chinese financial data providers (东方财富, 同花顺, etc.) and returns pandas DataFrames. We call their APIs, clean the data, and save it as CSV/JSON files organized by stock symbol.

**Key functions:**
- `fetch_daily_ohlcv(symbol, start_date, end_date)` — downloads the daily price history (Open, High, Low, Close, Volume) for a stock. This is the foundation for all technical analysis. Example: fetching 2 years of 贵州茅台 data gives us ~500 rows of daily prices.
- `fetch_realtime_quote(symbol)` — gets the current live price, today's change%, volume, etc. Used for the watchlist display.
- `fetch_financial_summary(symbol)` — pulls key financial ratios (PE, PB, ROE, revenue, profit) from the latest quarterly/annual reports. Used for fundamental analysis.
- `fetch_sector_flow(symbol)` — shows how much money is flowing into/out of the stock's industry sector. Useful for understanding if the whole sector is hot or cold.
- `update_watchlist_data()` — runs all the above for every stock in your watchlist. Called daily by the pipeline.

**Data storage:** `C:/reports/stock/data/{symbol}/daily.csv`, `financials.json`, `realtime.json`

**akshare key APIs:**
- `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date)` — OHLCV history
- `ak.stock_zh_a_spot_em()` — real-time quotes for all A-shares
- `ak.stock_financial_abstract_ths(symbol)` — financial summary from 同花顺
- `ak.stock_individual_info_em(symbol)` — company profile (industry, market cap, etc.)
- `ak.stock_news_em(symbol)` — stock-specific news headlines

---

### Task 0.3: Watchlist Management

**Files:**
- Create: `scripts/stock/watchlist.py`

**Purpose:** Manage a personal watchlist of stocks to track. Like a "favorites" list — you add stocks you're interested in, and Jarvis monitors them daily.

**Data format (`watchlist.json`):**
```json
{
  "stocks": [
    {
      "symbol": "600519",
      "name": "贵州茅台",
      "sector": "白酒",
      "added": "2026-04-12",
      "notes": "Long-term hold candidate"
    }
  ],
  "sectors": ["AI/半导体", "新能源", "医疗器械", "白酒"],
  "update_frequency": "daily"
}
```

**UI:** Agent toolbar "Stock" category → "My Watchlist" button opens a modal to add/remove stocks, view current prices.

---

## Phase 1: Technical Analysis Engine

> **Goal of this phase:** Given a stock's price history, calculate all the standard technical indicators and generate a human-readable report that says things like "Short-term trend is bullish, RSI is overbought at 75, MACD just had a golden cross, support at ¥1800."

### Task 1.1: Technical Indicators

**Files:**
- Create: `scripts/stock/technical_analysis.py`

**Purpose:** Calculate standard technical indicators from OHLCV data. These are the same indicators that millions of Chinese retail investors look at on 东方财富 or 同花顺 apps.

**Indicators to implement (via pandas-ta):**

| Indicator | Parameters | What it tells us |
|-----------|-----------|-----------------|
| MA (均线) | MA5, MA10, MA20, MA60, MA120, MA250 | Trend direction at different time scales. MA5 = very short term (1 week), MA250 = long term (1 year). Price above MA = bullish at that scale. |
| MACD | (12, 26, 9) | Momentum and trend changes. MACD line crossing above signal line = bullish momentum building. The histogram shows the strength of the momentum. |
| RSI | 14-day | Overbought (>70) or oversold (<30). Helps identify when a move has gone too far and might reverse. |
| KDJ | (9, 3, 3) | Similar to RSI but more popular in China. J > 100 = overbought, J < 0 = oversold. More sensitive than RSI. |
| Bollinger Bands | (20, 2) | Volatility and price extremes. Price touching upper band = potentially overbought. Bands squeezing = big move coming. |
| OBV | — | Volume trend. Rising OBV with flat price = accumulation (smart money buying). Falling OBV with flat price = distribution (smart money selling). |
| Volume MA | 5-day, 20-day | Average trading volume. Today's volume vs average tells us if there's unusual activity. |
| Pivot Points | — | Support and resistance levels calculated from yesterday's high, low, close. Common reference points for traders. |
| ATR | 14-day | Average daily price range. Tells us how volatile the stock is. Used for position sizing and stop-loss placement. |

**Output:** JSON with all indicator values + signal summary (bullish/bearish/neutral per indicator).

```json
{
  "symbol": "600519",
  "date": "2026-04-11",
  "price": { "close": 1850.00, "change_pct": 1.2 },
  "signals": {
    "ma_trend": "bullish",
    "macd": "bullish_crossover",
    "rsi": "neutral",
    "kdj": "overbought",
    "bollinger": "upper_band_touch",
    "volume": "above_average"
  },
  "overall": "moderately_bullish",
  "indicators": { ... }
}
```

---

### Task 1.2: Pattern Recognition

**Files:**
- Create: `scripts/stock/patterns.py`

**Purpose:** Detect common chart patterns and candlestick patterns. These are visual patterns that experienced traders recognize — we automate the detection.

**Patterns to detect:**

| Pattern | What it looks like | What it means |
|---------|-------------------|---------------|
| **Hammer (锤子线)** | Small body at top, long lower shadow (wick). Appears after a downtrend. | Buyers fought back from the low — potential reversal upward. |
| **Engulfing (吞没形态)** | Today's candle completely "swallows" yesterday's. Bullish engulfing: red yesterday, big green today. | Strong reversal signal. The new direction overwhelmed the old. |
| **Doji (十字星)** | Open ≈ Close, creating a cross shape. | Indecision — neither buyers nor sellers won. Often appears at turning points. |
| **Morning Star (早晨之星)** | 3-candle pattern: big red → small body (gap down) → big green. | Classic bottom reversal. The market found a floor and bounced. |
| **Golden Cross (金叉)** | MA5 crosses above MA20 (or MA10 above MA60). | Short-term momentum is now stronger than the longer trend — bullish signal. |
| **Death Cross (死叉)** | MA5 crosses below MA20. | Short-term momentum is weaker — bearish signal. |
| **Volume Breakout** | Volume suddenly 2-3x above average, with a price move in the same direction. | Confirms the price move is "real" — lots of traders agree with the direction. |
| **Support/Resistance Break** | Price breaks above resistance or below support with volume. | Major signal — the stock is entering new territory. Often leads to continued movement. |

---

### Task 1.3: Technical Analysis Report

**Files:**
- Create: `scripts/stock/report_technical.py`

**Purpose:** Generate a human-readable technical analysis report for a stock. Combines all indicators and patterns into a narrative that even a beginner can understand.

**Output format:** Markdown report with:
- Current price, today's change, and volume vs average
- Trend assessment: short-term (1-5 days), medium-term (1-4 weeks), long-term (1-6 months)
- Key indicator signals with plain-language explanations
- Support/resistance levels (where the stock might bounce or stall)
- Pattern alerts (any candlestick or chart patterns detected today)
- Risk level (1-5): 1 = very low risk/stable, 5 = very high risk/volatile

---

## Phase 2: Fundamental Analysis

> **Goal of this phase:** Evaluate whether a company's stock price is justified by its actual business performance. A stock can be technically "bullish" but fundamentally overpriced — or technically "bearish" but a great value. We want both perspectives.

### Task 2.1: Financial Data Collector

**Files:**
- Create: `scripts/stock/fetch_fundamentals.py`

**Purpose:** Fetch and organize fundamental data from financial reports. Chinese listed companies publish quarterly reports (Q1, Q2/半年报, Q3, Q4/年报) with standardized financial data.

**Data points we collect:**

| Category | Metrics | What they tell us |
|----------|---------|-------------------|
| **Income Statement (利润表)** | Revenue (营收), Net Profit (净利润), YoY Growth (同比增长) | Is the business growing? Is it profitable? How fast? |
| **Balance Sheet (资产负债表)** | Total Assets, Debt Ratio (资产负债率), Current Ratio (流动比率) | Is the company financially healthy? Can it pay its debts? |
| **Cash Flow (现金流量表)** | Operating Cash Flow, Free Cash Flow | Is the company generating real cash (not just accounting profit)? |
| **Valuation (估值)** | PE, PB, PS (Price/Sales), PEG, Dividend Yield | Is the stock cheap or expensive relative to its earnings/assets/growth? |
| **Industry Comparison** | Rank within sector for PE, ROE, growth | How does this stock compare to its peers? |

**akshare APIs:**
- `ak.stock_financial_analysis_indicator(symbol)` — financial ratios over time
- `ak.stock_profit_forecast_ths(symbol)` — what professional analysts predict for future earnings
- `ak.stock_rank_forecast_cninfo(symbol)` — analyst buy/hold/sell ratings

---

### Task 2.2: Fundamental Scoring

**Files:**
- Create: `scripts/stock/fundamental_score.py`

**Purpose:** Score stocks on fundamental quality (0-100). This creates a single number that summarizes "how good is this company's business?" so we can easily compare stocks.

**Scoring dimensions (weighted):**

| Dimension | Weight | What we measure | Score logic |
|-----------|--------|-----------------|-------------|
| **Profitability** | 25% | ROE, net profit margin | ROE > 20% = high score. Consistent profitability over 3+ years = bonus. |
| **Growth** | 25% | Revenue YoY, Profit YoY | 30%+ growth = high score. Accelerating growth = bonus. Declining = penalty. |
| **Valuation** | 20% | PE vs sector average, PEG | PE below sector median = good value. PEG < 1 = undervalued for growth. |
| **Financial Health** | 15% | Debt ratio, current ratio, FCF | Low debt (<50%), positive FCF, current ratio > 1.5 = healthy. |
| **Analyst Consensus** | 15% | Buy/hold/sell ratings, price targets | Majority "buy" with upside to target = bullish. |

**Example output:**
```
贵州茅台 (600519) — Fundamental Score: 82/100
  Profitability: 95/100 (ROE 30%, margin 52%)
  Growth: 65/100 (Revenue +12% YoY, slowing)
  Valuation: 70/100 (PE 28, sector avg 35, PEG 2.3)
  Financial Health: 90/100 (Debt 20%, FCF strong)
  Analyst Consensus: 85/100 (80% buy, target +15%)
```

---

## Phase 3: Sentiment & News Analysis

> **Goal of this phase:** Read the news and figure out whether the market "mood" around a stock is positive or negative. News moves stock prices — earnings beats, policy changes, scandals, industry trends all affect sentiment. We use our Ollama LLM to read and classify hundreds of articles automatically.

### Task 3.1: News Fetcher

**Files:**
- Create: `scripts/stock/fetch_news.py`

**Purpose:** Fetch stock-specific and sector news from multiple Chinese financial news sources.

**Sources:**
| Source | What it provides | How we access it |
|--------|-----------------|------------------|
| **akshare news API** | Stock-specific news from 东方财富 | `ak.stock_news_em(symbol)` |
| **East Money (东方财富)** | Market commentary, analyst reports | akshare or web scraping |
| **Sina Finance (新浪财经)** | Broad financial news | Optional web scraping |
| **Snowball (雪球)** | Retail investor discussions and analysis | Optional web scraping |
| **Sector/policy news** | Government policy, industry regulations | akshare sector news APIs |

**Storage:** `C:/reports/stock/data/{symbol}/news/YYYY-MM-DD.json`

Each news item stored as:
```json
{
  "title": "贵州茅台一季度净利润增长15%",
  "source": "东方财富",
  "date": "2026-04-11",
  "url": "https://...",
  "content": "...",
  "sentiment": null
}
```

---

### Task 3.2: Sentiment Analysis

**Files:**
- Create: `scripts/stock/sentiment.py`

**Purpose:** Use Ollama LLM to analyze news sentiment for stocks. The LLM reads each article and rates it on a scale from -1.0 (very bearish) to +1.0 (very bullish).

**How it works:**
1. Collect all news articles for a stock from the past 1-3 days
2. Send each article to Ollama with a prompt: "You are a Chinese stock market analyst. Read this article and rate its sentiment for [stock name] from -1.0 (very bearish) to +1.0 (very bullish). Explain in one sentence."
3. Aggregate individual scores into a daily sentiment score (weighted average, more recent = higher weight)
4. Track the sentiment trend over time (is sentiment improving or deteriorating?)
5. Detect sentiment shifts — if the score changes by more than 0.5 in one day, flag it as a potential signal

**Ollama prompt design:**
```
System: You are a Chinese stock market analyst specializing in A-shares.
        Classify news sentiment for the given stock.
        Output JSON: {"score": float, "reason": "one sentence"}

User: Stock: 贵州茅台 (600519)
      Article: [article text]
      Rate sentiment from -1.0 (very bearish) to +1.0 (very bullish).
```

**Output:** Daily sentiment report per stock:
```json
{
  "symbol": "600519",
  "date": "2026-04-11",
  "daily_score": 0.35,
  "trend_5d": "improving",
  "article_count": 12,
  "shift_alert": false,
  "top_positive": "一季度净利润超预期增长15%",
  "top_negative": "白酒行业面临消费降级压力"
}
```

---

### Task 3.3: RAG Integration for Market Context

**Files:**
- Modify: `scripts/stock/config.py` (add Qdrant collection)
- Create: `scripts/stock/index_market_data.py`

**Purpose:** Index stock news, analysis reports, and market commentary into Qdrant (the same vector database Jarvis already uses for AI news). This enables asking Jarvis natural-language questions about stocks in the main chat.

**How it works:** Same as existing RAG indexing — we chunk the text, generate embeddings, and store in Qdrant with metadata (symbol, date, item_type). The agent's existing RAG search then finds relevant stock context when you ask questions.

**Item types:** `stock_news`, `stock_analysis`, `market_commentary`, `financial_report`

**Example queries this enables:**
- "What's the latest news about 贵州茅台?"
- "How is the semiconductor sector performing this week?"
- "What did analysts say about 宁德时代's earnings?"
- "Are there any policy changes affecting 新能源 stocks?"

---

## Phase 4: AI Prediction Models

> **Goal of this phase:** Build a machine learning model that combines ALL the data from Phases 1-3 (technical indicators, fundamental scores, sentiment) to predict whether a stock will go up or down in the next 5 trading days. Then use the LLM to explain the prediction in plain language.

### Task 4.1: Feature Engineering

**Files:**
- Create: `scripts/stock/features.py`

**Purpose:** Transform raw data into structured "features" (input variables) that the ML model can learn from. This is the most important step — the quality of features determines prediction accuracy more than the choice of algorithm.

**Feature categories (~40 features total):**

| Category | Features | Why they matter |
|----------|----------|-----------------|
| **Price** | 1-day return, 5-day return, 20-day return, distance from MA20, distance from MA60, 52-week high/low ratio | Captures momentum and trend at different time scales |
| **Volume** | Volume ratio (today/20-day avg), OBV 5-day change, volume trend direction | Volume confirms or denies price moves |
| **Technical** | RSI, MACD histogram, Bollinger %B (where price is within the bands), KDJ J-value, ATR ratio | Summarizes all technical indicator signals into numbers |
| **Fundamental** | PE percentile (vs history), PB percentile, ROE, profit growth YoY, debt ratio | Business quality and valuation context |
| **Sentiment** | Daily sentiment score, 5-day sentiment trend, news article count, sentiment volatility | Market mood and information flow |
| **Market** | Shanghai index 5-day return, sector 5-day return, market breadth (% of stocks up) | Overall market context — most stocks follow the market |
| **Calendar** | Day of week (Mon=1..Fri=5), month, days to/from holiday | Seasonal patterns (e.g., "January effect", pre-holiday selling) |

**How feature engineering works (example):**
```
Raw data: Stock closed at ¥1850, MA20 = ¥1800, RSI = 72, 
          sentiment score = 0.35, Shanghai index up 1.2% this week

Feature vector: [
  distance_from_ma20 = +2.78%,    # (1850-1800)/1800
  rsi_14 = 72,                     # overbought territory
  sentiment_daily = 0.35,          # mildly bullish
  market_5d_return = 1.2%,         # market is up
  volume_ratio = 1.5,              # 50% above average
  ...
]
```

---

### Task 4.2: XGBoost Prediction Model

**Files:**
- Create: `scripts/stock/model_xgboost.py`

**Purpose:** Train an XGBoost model to predict 5-day forward price direction.

**What XGBoost does (simplified):**
1. It looks at thousands of historical examples: "On days when RSI was 72, sentiment was 0.35, and the market was up 1.2%, what happened 5 days later?"
2. It builds hundreds of simple "if-then" rules (decision trees) and combines them
3. Each new tree focuses on correcting the mistakes of the previous trees
4. The final prediction is the combined vote of all trees

**Target variable:** 5-day forward return direction
- **UP**: stock goes up more than +2% in next 5 trading days
- **DOWN**: stock goes down more than -2% in next 5 trading days
- **FLAT**: stock stays within ±2%

**Training approach — Walk-Forward Validation:**
```
Training window: 250 days (1 year of trading data)
Test window: 5 days

Round 1: Train on days 1-250,    predict days 251-255
Round 2: Train on days 2-251,    predict days 252-256
Round 3: Train on days 3-252,    predict days 253-257
... and so on

This simulates real-world usage: we only ever train on PAST data
and predict the FUTURE. No cheating.
```

**Retraining schedule:** Weekly (every Monday before market open). Uses the latest data to keep the model current.

**Output per prediction:**
```json
{
  "symbol": "600519",
  "prediction_date": "2026-04-11",
  "target_date": "2026-04-18",
  "direction": "UP",
  "confidence": 0.72,
  "probabilities": { "UP": 0.72, "FLAT": 0.18, "DOWN": 0.10 },
  "top_features": [
    { "name": "macd_histogram", "importance": 0.15, "value": 12.3 },
    { "name": "sentiment_5d_trend", "importance": 0.12, "value": 0.4 },
    { "name": "volume_ratio", "importance": 0.10, "value": 1.8 }
  ]
}
```

---

### Task 4.3: LLM Reasoning Layer

**Files:**
- Create: `scripts/stock/llm_reasoning.py`

**Purpose:** Use Ollama to synthesize ALL analysis into a human-readable prediction report with clear reasoning. The XGBoost model gives us numbers; the LLM turns them into actionable advice.

**Input to LLM (everything from Phases 1-4):**
- Technical analysis summary (trend, signals, patterns)
- Fundamental score and key metrics (PE, ROE, growth)
- Sentiment analysis results (daily score, trend, key news)
- XGBoost prediction + confidence + top contributing features
- Recent news headlines (top 5 positive, top 5 negative)

**LLM prompt:**
```
System: You are a senior Chinese stock market analyst writing a prediction
        report for a retail investor who is learning about stocks.
        Be clear, honest about uncertainty, and explain your reasoning.
        Write in Chinese with English technical terms.

User: [All analysis data]
      
      Write a prediction report with:
      1. 方向判断 (Direction): 看涨/看跌/震荡
      2. 信心水平 (Confidence): 高/中/低
      3. 时间范围 (Horizon): 1周 / 2周
      4. 核心理由 (Key Reasons): 3-5 bullet points
      5. 风险因素 (Risk Factors): what could go wrong
      6. 建议操作 (Suggested Action): 买入/持有/减仓/观望
      7. 关键价位 (Key Levels): support, resistance, stop-loss
```

**Example output:**
```
## 贵州茅台 (600519) — AI 预测报告 2026-04-11

### 方向判断：看涨 (Bullish)
### 信心水平：中等 (Medium) — 72% 模型置信度
### 时间范围：未来1-2周

### 核心理由
1. **MACD金叉确认**：MACD线刚刚上穿信号线，histogram转正，短期动能向上
2. **一季报超预期**：净利润同比+15%，超过市场预期的12%，基本面支撑
3. **市场情绪回暖**：近5天sentiment从0.1升至0.35，新闻面以正面为主
4. **大盘配合**：上证指数本周上涨1.2%，市场整体风险偏好改善
5. **成交量放大**：今日成交量为20日均量的1.5倍，资金在积极参与

### 风险因素
- RSI已达72，接近超买区域，短期可能有回调压力
- 白酒行业面临消费降级担忧，中长期不确定性存在
- 如果大盘转弱，个股难以独善其身

### 建议操作：轻仓买入 / 持有
- 已持有者：继续持有，上调止损至¥1780
- 未持有者：可在¥1820-1840区间轻仓买入
- 止损位：¥1780（MA20下方）
- 目标位：¥1920（前高阻力位）
```

---

## Phase 4.5: Stock Screener & Recommendation Engine

> **Goal of this phase:** Automatically scan the entire A-share market, filter candidates by technical + fundamental criteria, score and rank them, then generate AI-powered buy/sell recommendations. This is the core "stock recommendation" feature.

### Task 4.5.1: Market-Wide Data Scanner

**Files:**
- Create: `scripts/stock/market_scanner.py`

**Purpose:** Fetch summary data for all A-share stocks in batch, then apply filters to find candidates worth analyzing in depth.

**How it works:**
1. Use `ak.stock_zh_a_spot_em()` to get real-time snapshot of all ~5000 A-shares (price, PE, PB, volume, change%)
2. Apply configurable filters to narrow down to ~50-200 candidates
3. For each candidate, fetch detailed data (daily OHLCV, financials) if not cached

**Default filter presets (用户可自定义):**

| 筛选策略 | 条件 | 适合场景 |
|----------|------|---------|
| **价值型 (Value)** | PE < 20, PB < 3, ROE > 15%, 负债率 < 50% | 寻找被低估的优质公司 |
| **成长型 (Growth)** | 净利润增长 > 20%, 营收增长 > 15%, PE < 50 | 寻找高速增长的公司 |
| **技术突破 (Breakout)** | 突破20日均线, 成交量放大 > 1.5倍, MACD金叉 | 寻找短期上涨信号 |
| **超跌反弹 (Oversold)** | RSI < 30, 近20日跌幅 > 15%, 成交量萎缩 | 寻找可能反弹的股票 |
| **AI/科技板块** | 行业 in [半导体, AI, 软件, 云计算], 市值 > 50亿 | 你感兴趣的AI相关股票 |
| **医疗器械** | 行业 = 医疗器械, ROE > 10% | 你的工作领域相关 |

### Task 4.5.2: Composite Scoring Engine

**Files:**
- Create: `scripts/stock/stock_scorer.py`

**Purpose:** For each screened candidate, calculate a composite score (0-100) combining all analysis dimensions.

**Scoring formula:**

| 维度 | 权重 | 数据来源 |
|------|------|---------|
| 技术面得分 | 30% | Phase 1 技术指标信号 |
| 基本面得分 | 25% | Phase 2 财务评分 |
| 情绪面得分 | 15% | Phase 3 新闻情绪 |
| ML预测得分 | 20% | Phase 4 XGBoost 置信度 |
| 资金流向 | 10% | 主力资金净流入/流出 |

**Output:** Ranked list of top candidates with scores and key metrics.

### Task 4.5.3: AI Recommendation Report

**Files:**
- Create: `scripts/stock/recommendation.py`

**Purpose:** Use the HEAVY model (8b) to generate a daily stock recommendation report in Chinese.

**Report structure:**
```
# 每日 AI 选股推荐 — 2026-04-12

## 今日推荐 (Top 5)

### 1. 贵州茅台 (600519) — 综合评分: 85/100
- **推荐理由:** MACD金叉 + 一季报超预期 + 情绪回暖
- **技术面:** 短期看涨, MA5上穿MA20, RSI=65 (健康区间)
- **基本面:** ROE 30%, PE 28 (低于行业均值35)
- **风险提示:** 白酒行业消费降级压力
- **建议操作:** 轻仓买入, 目标价 ¥1920, 止损 ¥1780

### 2. ...

## 今日关注板块
- AI/半导体: 资金净流入 +15亿, 政策利好
- 新能源: 技术面走弱, 建议观望

## 风险提示
- 大盘整体...
```

**Trigger:** Can be run manually via toolbar button "AI 选股" or automatically as part of daily pipeline.

### Task 4.5.4: Screener Configuration UI

**Files:**
- Create: `scripts/stock/screener_config.json` (default presets)
- Modify: `scripts/rag/agent.py` (add screener modal)

**UI:** Agent toolbar "Stock" category → "AI 选股" button:
1. Select filter preset (价值型/成长型/技术突破/自定义)
2. Optionally adjust parameters
3. Click "开始筛选" → background job scans market
4. Results shown as ranked table with scores
5. Click any stock → detailed analysis modal
6. "生成推荐报告" → AI writes full recommendation report

---

## Phase 5: Agent UI Integration

> **Goal of this phase:** Add all the stock features to the Jarvis web UI, so you can manage your watchlist, view analysis, and get predictions through the same interface you use for AI news and team tools.

### Task 5.1: Stock Toolbar Buttons

**Files:**
- Modify: `scripts/rag/agent.py` (add Stock toolbar category + routes)

**New toolbar category "Stock":**
| Button | Action | What it does |
|--------|--------|-------------|
| My Watchlist | Opens watchlist modal | View all tracked stocks with current prices, add/remove stocks, quick status overview |
| AI 选股 | Opens screener modal | Filter market by strategy preset → score & rank → AI recommendation report |
| Market Refresh | Triggers background job | Fetches latest data (prices, news, financials) for all watchlist stocks |
| Stock Analysis | Opens analysis modal | Select a stock → see full technical + fundamental report with charts |
| AI Prediction | Opens prediction modal | Select a stock → get AI prediction with reasoning (SSE streaming) |
| Market Audio | Generates audio briefing | Creates a ~5 min audio summary of today's market and your watchlist |

**New API endpoints:**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/stock/watchlist` | List all stocks in watchlist with current prices |
| POST | `/api/stock/watchlist` | Add or remove a stock from watchlist |
| POST | `/api/stock/refresh` | Start background data refresh job |
| GET | `/api/stock/refresh/<job_id>` | Poll refresh job status |
| GET | `/api/stock/analysis/<symbol>` | Get full analysis report (technical + fundamental) |
| POST | `/api/stock/predict/<symbol>` | Run AI prediction (SSE stream with reasoning) |
| POST | `/api/stock/audio-briefing` | Generate market audio briefing |
| GET | `/api/stock/audio-briefing/<job_id>` | Poll audio generation status |

---

### Task 5.2: Stock Analysis Modal

**Files:**
- Modify: `scripts/rag/agent.py` (HTML/JS for stock modal)

**UI flow:**
1. Click "Stock Analysis" → modal opens with your watchlist as a dropdown
2. Select a stock → modal shows a tabbed view:
   - **Technical** tab: trend summary, indicator signals, pattern alerts, risk level
   - **Fundamental** tab: financial score, key metrics, industry comparison
   - **News** tab: recent headlines with sentiment scores, sentiment trend chart
   - **AI Prediction** tab: click "Generate Prediction" → SSE streams the LLM reasoning report
3. "Generate Audio" button at the bottom → creates a spoken analysis for the selected stock

---

### Task 5.3: Daily Stock Pipeline

**Files:**
- Create: `scripts/stock/run_stock_pipeline.py`
- Modify: `bin/jarvis-start.bat` (optional: add stock data refresh)

**Pipeline steps (runs daily, ~5-10 minutes):**

| Step | What it does | Time estimate |
|------|-------------|---------------|
| 1. Update OHLCV | Download latest daily prices for all watchlist stocks | ~30s |
| 2. Calculate indicators | Run all technical indicators on updated data | ~10s |
| 3. Fetch news | Download latest news for each stock | ~60s |
| 4. Sentiment analysis | LLM classifies each news article | ~120s (depends on article count) |
| 5. Update fundamentals | Refresh financial data (weekly only, skip if recent) | ~30s |
| 6. XGBoost predictions | Run ML model for each stock | ~10s |
| 7. LLM reasoning | Generate prediction reports | ~120s |
| 8. Index into Qdrant | Add news and reports to RAG for Q&A | ~30s |
| 9. Audio briefing | (Optional) Generate spoken market summary | ~120s |

**Can be triggered manually via "Market Refresh" button or scheduled alongside the existing Daily Fetch.**

---

## Phase 6: Advanced Features (Future)

> These are stretch goals for after the core system is working well. Each is independently useful.

### Task 6.1: Portfolio Tracking
- Track your actual buy/sell transactions (date, price, quantity)
- Calculate real-time P&L (profit & loss) for each position
- Show total portfolio return vs benchmarks (沪深300 index, 中证500 index)
- Generate monthly/quarterly portfolio performance reports

### Task 6.2: Backtesting Framework
- **What is backtesting?** Simulating your trading strategy on historical data to see how it would have performed. E.g., "If I bought every time the model said 'UP' with >70% confidence and sold after 5 days, what would my return be over the past 2 years?"
- Test different strategies: buy on golden cross, sell on death cross; buy on high sentiment + low RSI; etc.
- Calculate key metrics: Sharpe ratio (risk-adjusted return), max drawdown (worst peak-to-trough loss), win rate
- This is crucial for validating that the model actually works before risking real money

### Task 6.3: Alert System
- **Price alerts:** Notify when a stock crosses above ¥X or below ¥Y
- **Technical signal alerts:** Golden cross detected, RSI entered oversold zone, volume breakout
- **News sentiment shift alerts:** Sudden change from bullish to bearish (or vice versa)
- **Prediction alerts:** Model confidence changed significantly
- Alerts appear in the Jarvis chat as notifications, or generate a brief audio alert

### Task 6.4: Sector Rotation Analysis
- **What is sector rotation?** Money flows between industry sectors based on economic cycles. E.g., in early recovery → cyclical stocks (banks, materials); in late expansion → defensive stocks (utilities, healthcare).
- Track capital flow across all A-share sectors daily
- Identify which sectors have momentum (money flowing in) vs which are losing steam
- Suggest sector allocation: "Increase exposure to 半导体, reduce 房地产"
- This is a higher-level view than individual stock analysis

---

## Knowledge Prerequisites

Before implementing, the developer should understand:

1. **A-share market basics:** Trading hours (9:30-15:00 Beijing time), T+1 settlement (buy today, earliest sell tomorrow), 10% daily price limit on main board (20% for 创业板/科创板), stock codes (6xxxxx = Shanghai, 0xxxxx/3xxxxx = Shenzhen)
2. **akshare library:** Open-source, no API key needed, but rate-limited (don't call too fast). Documentation: https://akshare.akfamily.xyz/
3. **Technical analysis:** Moving averages, MACD, RSI, KDJ are the standard indicators used by Chinese retail investors — these are what people look at on 东方财富 and 同花顺
4. **Chinese financial terms:** 市盈率(PE), 市净率(PB), 净资产收益率(ROE), 涨停(limit up), 跌停(limit down), 均线(MA), 金叉(golden cross), 死叉(death cross)
5. **Proxy considerations:** akshare accesses Chinese financial APIs (东方财富, 同花顺) — these are Chinese servers, so you may NOT need the SOCKS proxy (unlike international news fetchers that need it to bypass GFW)

## Risk Disclaimer

Stock prediction is inherently uncertain. This tool is for **educational and research purposes**. Key limitations:
- Past performance does not guarantee future results
- ML models can overfit to historical patterns that don't repeat
- Sentiment analysis has accuracy limits — LLMs can misinterpret sarcasm, context
- The market can be irrational longer than your model expects
- Chinese A-shares are heavily influenced by policy and retail sentiment, which are hard to model
- **Always do your own research before trading real money**

---

*Plan created: 2026-04-12. Review and adjust before implementation.*
