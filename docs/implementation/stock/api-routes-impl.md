# Stock API Routes Implementation

## Overview

All stock API endpoints are defined in `scripts/rag/agent.py` using Flask. The `@_with_stock_imports` decorator ensures `scripts/stock/` is on `sys.path` before each handler.

---

## Endpoint Reference

### Stock Analysis

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/analyze` | `{ symbol, mode }` | Report strings per mode |

**Modes:** `technical`, `fundamental`, `sentiment`, `xgboost`, `full`

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

### Price Prediction & Training

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| `POST` | `/api/stock/train/daily` | — | `{ ok, message }` |
| `GET` | `/api/stock/train/status` | — | Progress + results + verifications |
| `GET` | `/api/stock/predict/<symbol>` | Path: 6-digit symbol | `{ prediction, accuracy }` |

**Training thread flow:**
1. Mutex check (`_train_lock`)
2. For each watchlist stock: `update_stock_data` → `backfill_actuals` → `get_latest_verification` → `train_price_prediction` → `record_prediction` → `get_accuracy_stats`
3. After all stocks: `fetch_all_sentiment()` + `scan_world_news()`
4. Write `train_progress.json` with status, results, verifications, sentiment, black_swan

**Status response includes:**
- `status`: `running` / `done` / `idle`
- `total`, `completed`, `current`
- `results[]`: per-stock predictions + health grades
- `verifications[]`: yesterday's prediction vs actual comparison
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
