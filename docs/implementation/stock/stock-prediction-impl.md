# Implementation Guide: Jarvis Stock Analysis & Prediction Module

## Overview

The stock module provides a **Chinese A-share (A股) individual stock prediction and analysis workflow**: market data ingestion, technical and fundamental engines, LLM-based news sentiment, **XGBoost** walk-forward classifiers and regressors, market sentiment signals (Fear & Greed, VIX), black swan detection from world news, a full-market **3-layer AI scanner with buyability filtering**, and consolidated Chinese narrative reports via Ollama.

**Primary code location:** `scripts/stock/` (17 modules)
**HTTP integration:** Flask routes in `scripts/rag/agent.py`
**Detailed docs:** See [README.md](./README.md) for the full document index.

### Recent Changes (2026-04-21)
- **Aggregate verification statistics** added to training report — cross-symbol direction accuracy, MAPE, MAE, 7d/30d windows, per-symbol breakdown
- **Verification scoped to watchlist** — removed stocks no longer appear in "昨日预测验证"
- **`get_aggregate_stats(symbols)`** added to `prediction_tracker.py`
- **Training report UI** includes new "历史验证统计" section with summary cards and collapsible per-symbol detail

### Changes (2026-04-19)
- **Scanner redesigned** from "top-5 by momentum" to **buyability-focused** (may return 0 stocks)
- **Training window** extended from 250 to **500 days** (both classifier and regressor)
- **Walk-forward rounds** increased from 10 to **15**
- **Confidence/uncertainty metrics** added to price prediction output
- **Fundamental scoring** integrated into scanner Layer 2
- **"Add to Watchlist" button** in scan result UI cards

---

## Architecture (Data Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           User (Browser / API client)                       │
└─────────────────────────────────────────────────────────────────────────────┘
        │  POST /api/stock/analyze  { symbol, mode }
        │  GET/POST /api/stock/watchlist ...
        │  POST /api/stock/train/daily
        │  POST /api/stock/scan/start
        │  GET /api/stock/sentiment, /api/stock/blackswan
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  agent.py  ──►  sys.path → scripts/stock/  (dynamic imports per mode)      │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ├─ mode technical / full ──► technical_analysis → report_technical
        ├─ mode fundamental / full ──► fundamental_analysis
        ├─ mode sentiment / full ──► sentiment (Ollama per article)
        ├─ mode xgboost / full ──► model_xgboost (classification)
        ├─ mode full only ──► llm_reasoning (Ollama synthesis)
        │
        ├─ train/daily ──► model_price_predictor (regression)
        │   └─ prediction_tracker (verification + aggregate_stats)
        │   └─ market_sentiment + black_swan_detector (appended to results)
        │
        └─ scan/start ──► scanner (3-layer) + hot_sectors
                └─ Layer 3: Ollama JSON scoring
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  On disk: C:/reports/stock/  │  External: akshare, Sina, EastMoney, Ollama │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Dependency Graph

```
config.py  ◄── used by all stock modules (paths, Ollama, MODEL_USAGE)

fetch_market_data.py ──► akshare, requests (Sina + EastMoney fallbacks)
watchlist.py ──────────► config, fetch_market_data
hot_sectors.py ─────────► akshare, config

technical_analysis.py ──► pandas, pandas_ta, config
report_technical.py ────► technical_analysis, config
fundamental_analysis.py ► akshare (同花顺), config
sentiment.py ──────────► requests (Ollama), config

features.py ───────────► technical_analysis (load_ohlcv, compute_indicators), config
model_xgboost.py ──────► features, xgboost, sklearn, config
model_price_predictor.py ► features, technical_analysis, market_sentiment, xgboost, config
prediction_tracker.py ──► technical_analysis (load_ohlcv), config

market_sentiment.py ───► requests (alternative.me, CNN, Yahoo), config
black_swan_detector.py ► config (reads world-news-data.json from Daily Fetch)

llm_reasoning.py ──────► technical_analysis, fundamental_analysis,
                         sentiment, requests (Ollama), config

scanner.py ────────────► hot_sectors, technical_analysis, sentiment,
                         fundamental_analysis, fetch_market_data,
                         requests (Ollama), config
```

---

## Scanner: Buyability-Focused Design (2026-04-19 Rework)

The AI scanner was redesigned from a **momentum-biased "top-5 always"** system to a **buyability-filtered** system. Key changes:

| Layer | Old Design | New Design |
|-------|-----------|------------|
| **L1 Filter** | Favored today's gainers (change×2 weight) | Balanced: PE weight ↑, momentum weight ↓ |
| **L1 PE cap** | < 100 | **< 80** |
| **L2 Scoring** | Tech 40% + sentiment 30% + L1 30% | **Fund 35%** + tech 25% + sentiment 15% + L1 15% + **valuation 10%** |
| **L2 Fundamentals** | Not checked | `fetch_fundamentals` + `score_fundamentals` per stock |
| **L2 Overbought** | Not checked | **RSI > 75 → auto-reject** before Layer 3 |
| **L3 LLM Prompt** | "Score this stock" | **"Is this stock worth buying NOW?"** with strict criteria |
| **L3 Output** | Always top 5 | **0 to 5** — only stocks with verdict="买入" AND score≥60 |
| **L3 CAP** | 20 | **30** (more candidates evaluated) |
| **Report (0 result)** | N/A | Explicit "no recommendation" message |
| **UI** | Score + metrics | + **"⭐ Add to Watchlist" button** per stock |

**Design rationale:** The old scanner recommended high-momentum stocks, but when users ran full analysis on each one, the LLM (with access to fundamentals) consistently said "don't buy". The root cause was the scanner optimizing for "what's hot today" instead of "what's worth buying". The rework aligns both systems.

---

## Anti-Overfitting Strategy (ML Models)

Both XGBoost models implement these safeguards:

| Measure | Classifier | Price Regressor |
|---------|-----------|-----------------|
| **Training Window** | **500 days** (~2 years) | **500 days** (~2 years) |
| **Early Stopping** | 15 rounds (constructor param) | 15 rounds (constructor param) |
| **Walk-Forward Rounds** | **15** (75 test days) | **15** (75 test days) |
| **Tree Depth** | 3 | 4 |
| **Regularization** | α=0.5, λ=2.0, subsample=0.7, colsample=0.6 | Same |
| **Feature Cap** | — | 40 features max (variance + correlation ranking) |
| **Fundamental Leakage Fix** | Last row only | Last row only |
| **Sentiment Features** | — | Last row only (Fear & Greed, VIX) |
| **Final Model** | Uses best_iteration from WF | Uses best_iteration from WF |
| **Prediction Target** | 3-class label | **% return** (not absolute price) |
| **Price Limit Clamping** | — | ±10% main / ±20% ChiNext,STAR / ±30% BSE |
| **Confidence Output** | — | level / signal_strength / noise assessment |

See [ml-pipeline-impl.md](./ml-pipeline-impl.md) for full details.

---

## Market Risk Signals

Two modules provide market-wide risk context:

### Fear & Greed + VIX (`market_sentiment.py`)
- Fear & Greed Index: alternative.me API (0-100) + CNN fallback
- VIX: Yahoo Finance (dual endpoint)
- Integrated as ML features (`sent_fear_greed`, `sent_vix`)
- UI: sentiment gauge card in training report

### Black Swan Detector (`black_swan_detector.py`)
- Scans Daily Fetch world news (6 sources: 中国新闻, BBC, Reuters, AP, DW, Guardian)
- 7 risk categories: war, sanctions, pandemic, financial crisis, natural disaster, regulation, tech ban
- Maps to affected A-share industries
- Per-stock risk check via sector matching

See [market-signals-impl.md](./market-signals-impl.md) for full details.

---

## API Endpoints Summary

| Category | Endpoints | Description |
|----------|-----------|-------------|
| Analysis | `POST /api/stock/analyze` | Run analysis modes |
| Watchlist | `GET/POST/DELETE /api/stock/watchlist` | CRUD + refresh |
| Scanner | `POST scan/start`, `GET scan/status/result/dates` | 3-layer AI scan |
| Training | `POST train/daily`, `GET train/status` | Price prediction training |
| Prediction | `GET predict/<symbol>` | Per-stock prediction + accuracy |
| Sentiment | `GET sentiment` | Fear & Greed + VIX |
| Black Swan | `GET blackswan`, `GET risk/<symbol>` | World news risk scan |

See [api-routes-impl.md](./api-routes-impl.md) for full details.

---

## Data Storage Layout

See [config-impl.md](./config-impl.md) for the complete disk layout under `C:/reports/stock/`.

---

## Honest Model Assessment

The current ML models should be understood as **research tools, not trading signals**:

| Model | Typical Performance | Assessment |
|-------|-------------------|------------|
| Direction Classifier | 45–55% accuracy | Barely above random (50% baseline). Useful as one signal among many. |
| Price Regressor | MAE ~1.5–2.5 pct points | Within daily noise range for most stocks. Directional hint only. |

**Why performance is limited:**
1. All features are derived from public OHLCV data — no informational edge
2. Even with 500-day window, financial time series remain highly noisy
3. No alternative data sources (order flow, fund holdings, social sentiment)
4. Single-model approach; no ensemble diversification
5. No execution model (slippage, fees, market impact not modeled)

**What would make it better** (see [learning/stock/ch7-quantitative-methods.md](../../learning/stock/ch7-quantitative-methods.md)):
- Tier 1: Ensemble methods, cross-sectional models, proper backtesting with costs
- Tier 2: Alternative data (NLP news, fund flow), factor models (Fama-French, Barra)
- Tier 3: Tick-level data, event-driven signals, portfolio optimization

For the full **phased engineering roadmap** with concrete module designs, verification targets, and environment coverage matrix, see [Ch. 9 — Enhancement Roadmap](../../learning/stock/ch9-enhancement-roadmap.md).

**Bottom line:** Use ML output as one input in a multi-dimensional analysis, alongside fundamental valuation, technical analysis, and risk management. See the [Stock Learning Track](../../learning/stock/) for a complete investor education.

---

## Known Limitations

- **API does not auto-fetch** OHLCV before analyze; missing `daily.csv` causes errors
- **Realtime** uses full-market scan per quote — can be slow
- **Sina fallback** is unadjusted (akshare uses 前复权 by default)
- **Sentiment** depends on prior news fetch; empty news returns stub result
- **ML** walk-forward is on recent windows — not a guarantee of live trading performance
- **VIX** may be unavailable (Yahoo 403); Fear & Greed uses crypto-derived proxy
- **Black swan** is keyword-based; cannot detect novel event types not in pattern dictionary
- **XGBoost ≥ 2.0 required** — `early_stopping_rounds` is a constructor parameter
- **Price regressor** predicts percentage returns (clamped to A-stock limits), not absolute prices — fixes mean-reversion bias on trending stocks
- **No valuation model** — no DCF, no peer comparison, no historical PE percentile ranking
- **No portfolio optimization** — each stock analyzed in isolation, no correlation/diversification modeling
- **Scanner may return 0 results** — by design: buyability filter rejects stocks that are overbought or lack fundamental support. This is a feature, not a bug.
- **akshare connection intermittent** — `RemoteDisconnected` errors occur under rate limiting or weekend low-load periods; fallback APIs handle most cases
- **Confidence metrics are relative** — "medium" confidence still means substantial uncertainty; all predictions should be treated as directional hints

---

## Dependencies

### Python Packages

| Package | Role |
|---------|------|
| akshare | A-share data (history, spot, profile, news, 同花顺) |
| pandas | DataFrames, I/O |
| pandas-ta | Technical indicators |
| xgboost (≥ 2.0) | Classifier + regressor |
| scikit-learn | LabelEncoder, utilities |
| requests | Ollama HTTP, fallback APIs |
| numpy | Numerical operations |

### Ollama Models

| Tier | Default Model | Used By |
|------|--------------|---------|
| FAST | qwen3:1.7b | Sentiment per article |
| NORMAL | qwen3.5:4b | Reserved |
| HEAVY | qwen3.5:4b | LLM synthesis, scanner Layer 3 |
