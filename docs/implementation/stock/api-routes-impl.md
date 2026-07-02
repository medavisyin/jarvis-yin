# Stock API Routes Implementation

## Overview

All stock API endpoints live on Flask blueprint `stock_bp` (`scripts/rag/routes/stock.py`), registered from `scripts/rag/agent.py`. The `@_with_stock_imports` decorator swaps in `scripts/stock/config.py` as `sys.path`/`sys.modules["config"]` for each handler. Since 2026-07-02 it is **non-destructive**: it no longer pops/deletes the cached stock sub-modules — it only swaps `sys.modules["config"]` and restores it in `finally`. This avoids racing the scan thread's `_safe_import` (which re-imports stock modules during a scan) on `sys.modules`/the import lock, which previously made status polls hang for minutes while a scan was running.

---

## Architecture & Design

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  ENTRY: HTTP client → Flask (agent.py) → register_blueprint(stock_bp)  │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  @_with_stock_imports (non-destructive since 2026-07-02)                │
│  · insert scripts/stock on sys.path                                      │
│  · sys.modules["config"] ← stock/config.py (restored in finally)         │
│  · no longer pops cached stock sub-modules                               │
└───────────────────────────────────┬──────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼───────────────────────────────┐
         ▼                          ▼                               ▼
┌────────────────────┐  ┌────────────────────────────────┐  ┌──────────────────────────┐
│  SYNC ROUTES       │  │  TRAIN POST /train/daily        │  │  SCAN / long-term scans  │
│  analyze, WL, …    │  │  _train_lock → daemon Thread │  │  scanner start_scan Thread│
│  predict, china…   │  │  import stock config in thread │  │  _scan_lock + _stop_evt  │
│  import stock libs │  │  per-symbol:                     │  │  status / result endpoints│
│  → computations    │  │    update_stock_data →         │  │  JSON + scan artifacts    │
│  → jsonify(...)    │  │    backfill_actuals →          │  └─────────────┬─────────────┘
└─────────┬──────────┘  │    verify → train → record     │                │
          │             │    aggregate_stats              │                │
          │             │    fetch_all_sentiment          │                │
          │             │    scan_world_news →            │                │
          │             │    train_progress.json          │                │
          │             └────────────────┬────────────────┘                │
          │                              │                               │
          └──────────────────────────────┴───────────────────────────────┘
                                        │
                                        ▼
                               HTTP JSON response
```

---

## Endpoint Reference

### Stock Analysis

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/analyze` | `{ symbol, mode }` | Report strings per mode |

**Modes:** `technical`, `fundamental`, `sentiment`, `xgboost`, `fund_flow`, `full`

The `fund_flow` mode (and `full`) returns a `fund_flow_report` field with smart money accumulation analysis including phase (布局期/拉升期/出货期), accumulation score, and actionable advice.

| `POST` | `/api/stock/analyze/deepseek` | `{ symbol }` | DeepSeek API prediction report |

The DeepSeek endpoint sends the same data as `generate_prediction` but uses the `deepseek-v4-pro` model via the OpenAI SDK (with thinking enabled). Returns `{ report, reasoning, model, usage }` (reasoning = chain-of-thought).

**Validation:** `symbol` must be non-empty and `symbol.isdigit()`.

---

### Watchlist Management

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `GET` | `/api/stock/watchlist` | — | `{ stocks: [...] }` with prices |
| `POST` | `/api/stock/watchlist` | `{ symbol, name?, sector? }` | Added entry |
| `DELETE` | `/api/stock/watchlist/<symbol>` | Path param | `true`/`false` |
| `POST` | `/api/stock/watchlist/refresh` | — | `{ ok: true }` |

---

### Market Scanner

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/scan/start` | — | `{ ok, status }` |
| `POST` | `/api/stock/scan/stop` | — | `{ ok }` |
| `GET` | `/api/stock/scan/status` | — | Progress JSON |
| `GET` | `/api/stock/scan/result` | — | Latest result |
| `GET` | `/api/stock/scan/result/<date>` | Path: YYYY-MM-DD | Date-specific result |
| `GET` | `/api/stock/scan/dates` | — | `{ dates: [...] }` |
| `GET` | `/api/stock/scan/history` | — | `{ history: [...] }` |

---

### Mid-day Speculative Scanner (T+1 Overnight)

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/midday/start` | `{ use_deepseek }` (boolean) | `{ ok, message }` |
| `POST` | `/api/stock/midday/stop` | — | `{ ok, message }` |
| `GET` | `/api/stock/midday/status` | — | Persistent thread-safe status JSON |
| `GET` | `/api/stock/midday/result` | — | Latest completed midday scan JSON |

---

### Price Prediction & Training

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/train/daily` | — | `{ ok, message }` |
| `GET` | `/api/stock/train/status` | — | Progress + results + verifications |
| `GET` | `/api/stock/predict/<symbol>` | Path: 6-digit symbol | `{ prediction, accuracy }` |

**Training thread flow:**
1. Mutex check (`_train_lock`)
2. For each watchlist stock: `update_stock_data` → `backfill_actuals` → `get_latest_verification` → `train_price_prediction` → `record_prediction` → `get_accuracy_stats`
3. Compute `get_aggregate_stats(watchlist_symbols)` — cross-symbol verification statistics (scoped to current watchlist only)
4. After all stocks: `fetch_all_sentiment()` + `scan_world_news()`
5. Write `train_progress.json` with status, results, verifications, aggregate_stats, sentiment, black_swan

**Status response includes:**
- `status`: `running` / `done` / `idle`
- `total`, `completed`, `current`
- `results[]`: per-stock predictions + health grades
- `verifications[]`: yesterday's prediction vs actual comparison (current watchlist only)
- `aggregate_stats`: cross-symbol historical verification stats (direction accuracy, MAPE, MAE, 7d/30d windows, per-symbol breakdown)
- `sentiment`: market sentiment data (Fear & Greed + VIX)
- `black_swan`: world news risk alerts

---

### Market Signals

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `GET` | `/api/stock/sentiment` | `?refresh=1` | Fear & Greed + VIX + mood |
| `GET` | `/api/stock/blackswan` | `?refresh=1`, `?date=` | Black swan alerts |
| `GET` | `/api/stock/risk/<symbol>` | Path param | Per-stock risk from alerts |

---

### China A-Share Data & National Team

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `GET` | `/api/stock/china-data` | — | All China market data summary (northbound, fund flow, margin, national team) |
| `GET` | `/api/stock/china-data/fund-flow/<symbol>` | Path: 6-digit symbol | Fund flow signals + smart money phase/score/detail |
| `GET` | `/api/stock/national-team` | — | `{ snapshot, trend, period_stats, backfill }` — 16 core ETF shares + anomaly + history + 1w/1m/3m indicators |

**National Team response shape:**
```json
{
  "snapshot": {
    "date": "2026-04-24",
    "etf_snapshot": [{ "code": "510300", "name": "300ETF", "shares_yi": 424.4, "change_pct": 0.0, ... }],
    "total_broad_shares_yi": 1704.7,
    "total_sector_shares_yi": 1614.8,
    "signals": { "broad_total_change": "平稳", "anomalies": [] }
  },
  "trend": { "trend": "小幅增持", "total_change_pct": 1.5, "data_points": 18, "history": [...] },
  "period_stats": {
    "periods": [
      { "key": "1w", "label": "1周", "broad_change_pct": 0.15, "sector_change_pct": -0.08, "ref_date": "2026-04-17" },
      { "key": "1m", "label": "1月", "broad_change_pct": 1.2, "sector_change_pct": 0.5, "ref_date": "2026-03-25" },
      { "key": "3m", "label": "3月", "broad_change_pct": 2.8, "sector_change_pct": 1.1, "ref_date": "2026-01-29" }
    ],
    "per_etf_periods": [
      { "code": "510300", "name": "300ETF", "type": "宽基", "current_yi": 424.4, "1w": 0.1, "1m": 1.5, "3m": 3.2 }
    ]
  },
  "backfill": { "backfilled": 0, "total_history": 18, "message": "历史数据已完整" }
}
```

**Automatic history backfill:** Each API call runs `national_team_backfill_history(days=90)`, fetching weekly SSE ETF share snapshots for the past 90 days. Already-existing dates are skipped. All dates normalized to `YYYY-MM-DD`.

**Side-effect:** Each call saves a Markdown knowledge file to `C:/reports/ai/knowledge/stock/national-team-YYYY-MM-DD.md` for RAG indexing.

---

### Timing Model & Backtest

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/timing/train` | `{ symbol }` | `{ ok, message }` |
| `GET` | `/api/stock/timing/status` | — | Training status |
| `GET` | `/api/stock/timing/predict/<symbol>` | Path param | Buy/exit signal + probabilities |
| `POST` | `/api/stock/backtest/<symbol>` | `{ strategy?, initial_capital? }` | BacktestResult with metrics |
| `GET` | `/api/stock/backtest/<symbol>/results` | Path param | Latest cached backtest |

---

## Thread Safety

| Resource | Guard | Description |
|----------|-------|-------------|
| Scanner | `_scan_lock` + `_scan_thread` + `_stop_event` | One scan at a time |
| Training | `_train_lock` + `_train_thread` | One training at a time |
| Config | `importlib` injection in threads | Prevents Flask config shadowing |

---

## Module Import Pattern

Background threads (scan, training) use `importlib.util` to force-load `scripts/stock/config.py`:

```python
_spec = importlib.util.spec_from_file_location("config", config_path)
_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)
sys.modules["config"] = _cfg
```

Then clear cached modules (`del sys.modules[mod_name]`) before importing stock modules to ensure fresh references.

---

## Error Handling

- All endpoints wrapped in `try/except` with `traceback.print_exc()`
- Return `{ error: str }` with HTTP 500 on exceptions
- Validation errors return HTTP 400
