# Implementation Guide: Jarvis Stock Analysis & Prediction Module

## Overview

The stock module provides a **Chinese A-share (A股) individual stock prediction and analysis workflow**: market data ingestion, technical and fundamental engines, LLM-based news sentiment, **XGBoost** walk-forward classifiers and regressors, market sentiment signals (Fear & Greed, VIX), black swan detection from world news, a full-market 3-layer AI scanner, and consolidated Chinese narrative reports via Ollama.

**Primary code location:** `scripts/stock/` (17 modules)
**HTTP integration:** Flask routes in `scripts/rag/agent.py`
**Detailed docs:** See [README.md](./README.md) for the full document index.

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
        │   └─ prediction_tracker (verification)
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
                         fetch_market_data, requests (Ollama), config
```

---

## Anti-Overfitting Strategy (ML Models)

Both XGBoost models implement these safeguards:

| Measure | Classifier | Price Regressor |
|---------|-----------|-----------------|
| **Early Stopping** | 15 rounds (constructor param) | 15 rounds (constructor param) |
| **Walk-Forward Rounds** | 10 (50 test days) | 10 (50 test days) |
| **Tree Depth** | 3 | 4 |
| **Regularization** | α=0.5, λ=2.0, subsample=0.7, colsample=0.6 | Same |
| **Feature Cap** | — | 40 features max (variance + correlation ranking) |
| **Fundamental Leakage Fix** | Last row only | Last row only |
| **Sentiment Features** | — | Last row only (Fear & Greed, VIX) |
| **Final Model** | Uses best_iteration from WF | Uses best_iteration from WF |

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

## Known Limitations

- **API does not auto-fetch** OHLCV before analyze; missing `daily.csv` causes errors
- **Realtime** uses full-market scan per quote — can be slow
- **Sina fallback** is unadjusted (akshare uses 前复权 by default)
- **Sentiment** depends on prior news fetch; empty news returns stub result
- **ML** walk-forward is on recent windows — not a guarantee of live trading performance
- **VIX** may be unavailable (Yahoo 403); Fear & Greed uses crypto-derived proxy
- **Black swan** is keyword-based; cannot detect novel event types not in pattern dictionary
- **XGBoost ≥ 2.0 required** — `early_stopping_rounds` is a constructor parameter

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
