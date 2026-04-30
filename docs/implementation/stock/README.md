---
tags:
  - hub
  - stock
  - implementation
category: hub
status: current
last-updated: 2026-04-23
---


# Stock Module — Implementation Docs

Comprehensive documentation for the Jarvis Chinese A-share stock analysis and prediction stack.

**Code location:** `c:\jarvis\scripts\stock\` (20 Python modules)
**HTTP API:** `scripts/rag/agent.py` (stock routes)
**On-disk layout:** `C:/reports/stock/`
**Related plans (archived — completed):**
- `docs/plans/archive/2026-04-12-stock-prediction.md`
- `docs/plans/archive/2026-04-22-china-market-adaptation.md` ← A股适配计划

## Document Index

| Document | Description |
|----------|-------------|
| [stock-prediction-impl.md](./stock-prediction-impl.md) | End-to-end architecture overview, module dependency graph, data flow summary |
| [config-impl.md](./config-impl.md) | Configuration, paths, Ollama models, environment variables, disk layout |
| [data-layer-impl.md](./data-layer-impl.md) | `fetch_market_data`, `watchlist`, `hot_sectors` — data acquisition, caching, enrichment |
| [analysis-engines-impl.md](./analysis-engines-impl.md) | `technical_analysis`, `report_technical`, `fundamental_analysis`, `sentiment` — four analysis engines |
| [ml-pipeline-impl.md](./ml-pipeline-impl.md) | `features`, `model_xgboost`, `model_price_predictor`, `prediction_tracker` — ML pipeline with anti-overfitting measures |
| [market-signals-impl.md](./market-signals-impl.md) | `market_sentiment`, `black_swan_detector` — Fear & Greed, VIX, world news risk scanning |
| [scanner-impl.md](./scanner-impl.md) | `scanner` + `hot_sectors` — 3-layer fund-driven AI recommendation engine; optional **DeepSeek API (deepseek-v4-pro with thinking) for stock analysis via Global Settings** for TOP 5 follow-up |
| [llm-synthesis-impl.md](./llm-synthesis-impl.md) | `llm_reasoning` — Ollama- or optional DeepSeek-powered Chinese narrative report (`generate_prediction_deepseek`, `/api/stock/analyze/deepseek`) |
| [api-routes-impl.md](./api-routes-impl.md) | All Flask API endpoints, thread safety, error handling |
| **[china-market-impl.md](./china-market-impl.md)** | `china_market_data`, `model_timing`, `backtest_engine` — A股特色数据层、择时模型、回测引擎 |

## Module Map (20 files)

```
scripts/stock/
├── __init__.py                 # Package init
├── config.py                   # Central configuration (+ call_deepseek / get_deepseek_key)
├── china_market_data.py        # A股特色数据 (北向/资金流/龙虎榜/国家队ETF/融资融券)  ← NEW
├── fetch_market_data.py        # Market data acquisition (akshare + fallbacks)
├── watchlist.py                # Watchlist CRUD + enrichment
├── hot_sectors.py              # Hot concept board fetcher
├── technical_analysis.py       # Technical indicators + signals
├── report_technical.py         # Technical Markdown report
├── fundamental_analysis.py     # Fundamental scoring + report
├── sentiment.py                # LLM news sentiment analysis
├── features.py                 # ML feature engineering (55 features, 17 China-specific)
├── model_xgboost.py            # XGBoost 3-class classifier (涨/平/跌)
├── model_price_predictor.py    # XGBoost regressors (close/high/low)
├── model_timing.py             # Dual buy/exit timing classifiers  ← NEW
├── prediction_tracker.py       # Prediction logging + verification
├── market_sentiment.py         # Fear & Greed + VIX fetcher
├── black_swan_detector.py      # World news black swan detector
├── llm_reasoning.py            # LLM synthesis report (+ generate_prediction_deepseek)
├── scanner.py                  # 3-layer fund-driven market scanner; optional DeepSeek on TOP 5
└── backtest_engine.py          # A-share backtest engine (T+1, fees, limits)  ← NEW
```
