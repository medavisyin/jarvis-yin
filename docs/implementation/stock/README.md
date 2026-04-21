---
tags:
  - hub
  - stock
  - implementation
category: hub
status: current
last-updated: 2026-04-21
---


# Stock Module — Implementation Docs

Comprehensive documentation for the Jarvis Chinese A-share stock analysis and prediction stack.

**Code location:** `c:\jarvis\scripts\stock\` (17 Python modules)
**HTTP API:** `scripts/rag/agent.py` (stock routes)
**On-disk layout:** `C:/reports/stock/`
**Related plan:** `docs/plans/2026-04-12-stock-prediction.md`

## Document Index

| Document | Description |
|----------|-------------|
| [stock-prediction-impl.md](./stock-prediction-impl.md) | End-to-end architecture overview, module dependency graph, data flow summary |
| [config-impl.md](./config-impl.md) | Configuration, paths, Ollama models, environment variables, disk layout |
| [data-layer-impl.md](./data-layer-impl.md) | `fetch_market_data`, `watchlist`, `hot_sectors` — data acquisition, caching, enrichment |
| [analysis-engines-impl.md](./analysis-engines-impl.md) | `technical_analysis`, `report_technical`, `fundamental_analysis`, `sentiment` — four analysis engines |
| [ml-pipeline-impl.md](./ml-pipeline-impl.md) | `features`, `model_xgboost`, `model_price_predictor`, `prediction_tracker` — ML pipeline with anti-overfitting measures |
| [market-signals-impl.md](./market-signals-impl.md) | `market_sentiment`, `black_swan_detector` — Fear & Greed, VIX, world news risk scanning |
| [scanner-impl.md](./scanner-impl.md) | `scanner` + `hot_sectors` — 3-layer full-market AI recommendation engine |
| [llm-synthesis-impl.md](./llm-synthesis-impl.md) | `llm_reasoning` — Ollama-powered Chinese narrative report generation |
| [api-routes-impl.md](./api-routes-impl.md) | All Flask API endpoints, thread safety, error handling |

## Module Map (17 files)

```
scripts/stock/
├── __init__.py                 # Package init
├── config.py                   # Central configuration
├── fetch_market_data.py        # Market data acquisition (akshare + fallbacks)
├── watchlist.py                # Watchlist CRUD + enrichment
├── hot_sectors.py              # Hot concept board fetcher
├── technical_analysis.py       # Technical indicators + signals
├── report_technical.py         # Technical Markdown report
├── fundamental_analysis.py     # Fundamental scoring + report
├── sentiment.py                # LLM news sentiment analysis
├── features.py                 # ML feature engineering
├── model_xgboost.py            # XGBoost 3-class classifier (涨/平/跌)
├── model_price_predictor.py    # XGBoost regressors (close/high/low)
├── prediction_tracker.py       # Prediction logging + verification
├── market_sentiment.py         # Fear & Greed + VIX fetcher
├── black_swan_detector.py      # World news black swan detector
├── llm_reasoning.py            # LLM synthesis report
└── scanner.py                  # 3-layer market scanner
```
