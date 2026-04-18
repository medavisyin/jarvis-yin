# Data Layer Implementation

## Overview

The data layer handles all market data acquisition, caching, and enrichment. It provides the foundation for analysis, ML training, and UI display.

## `fetch_market_data.py`

### Purpose

Pull A-share market data via **akshare**, persist to disk, with **Sina Finance** and **East Money** fallbacks.

### Key Functions

| Function | Description | Output |
|----------|-------------|--------|
| `fetch_daily_ohlcv(symbol)` | Daily OHLCV history (前复权 default) | `data/{symbol}/daily.csv` |
| `fetch_realtime_quote(symbol)` | Full-market spot scan, extract one symbol | `data/{symbol}/realtime.json` |
| `fetch_company_profile(symbol)` | Company metadata (name, industry, market cap) | `data/{symbol}/profile.json` |
| `fetch_stock_news(symbol)` | Recent news articles | `data/{symbol}/news/{YYYY-MM-DD}.json` |
| `update_stock_data(symbol)` | Orchestrates all of the above | All above files |
| `load_daily_ohlcv(symbol)` | Load cached CSV as DataFrame | In-memory |
| `load_realtime(symbol)` | Load cached realtime JSON | In-memory |

### Data Sources & Fallback Chain

```
fetch_daily_ohlcv:
  ak.stock_zh_a_hist (threaded, 20s timeout)
    └─ fallback → Sina JSON K-line API (CN_MarketData.getKLineData)

fetch_realtime_quote:
  ak.stock_zh_a_spot_em (full market)
    └─ fallback → Sina hq.sinajs.cn (per-symbol)

fetch_company_profile:
  ak.stock_individual_info_em
    └─ fallback → EastMoney CompanySurvey API (emweb.securities.eastmoney.com)

fetch_stock_news:
  ak.stock_news_em (no fallback)
```

### Threading & Timeout

`fetch_daily_ohlcv` runs akshare in a **daemon thread** with `t.join(timeout=20)`. If the thread hangs or raises, control falls to the Sina path. This is necessary because akshare's East Money HTTP calls can hang indefinitely.

### Retry Logic

`_retry(fn, retries=2, delay=1)` wraps calls with exponential backoff (`delay * (attempt + 1)` seconds).

### Storage Format

- **OHLCV:** CSV with UTF-8 BOM (`utf-8-sig`), no index column
- **JSON files:** `ensure_ascii=False`, `indent=2`, `_fetched_at` ISO timestamps

### Company Profile Fallback Detail

The `_fetch_profile_em_survey` function calls East Money's CompanySurvey web API:
- URL: `https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax`
- Extracts: `股票代码`, `股票简称`, `行业`, `证监会行业` from `jbzl` field
- Prefixes symbol with `SH`/`SZ` based on first digit (6/5/9 → SH, else SZ)

---

## `watchlist.py`

### Purpose

JSON-backed watchlist CRUD with metadata enrichment and batch refresh.

### Key Functions

| Function | Description |
|----------|-------------|
| `list_stocks()` | Return watchlist `stocks` array |
| `add_stock(symbol, name, sector, notes)` | Add stock with auto-resolve of name/sector |
| `remove_stock(symbol)` | Remove by symbol |
| `get_stock(symbol)` | Lookup one entry |
| `update_stock_notes(symbol, notes)` | Update notes field |
| `get_watchlist_with_prices()` | Enrich with latest prices from cached data |
| `refresh_all_data()` | Batch `update_stock_data` for all watchlist stocks |
| `search_stock(keyword)` | Search full market by code/name (akshare) |

### Auto-resolve on Add (`_resolve_stock_info`)

When `add_stock` is called without name/sector, `_resolve_stock_info(symbol)` attempts to fill them from:
1. Local `realtime.json` (name only)
2. Local `profile.json` (name + sector)
3. `ak.stock_zh_a_spot_em()` full-market scan (name only)
4. `fetch_company_profile()` with East Money fallback (name + sector)

### Backfill on Refresh (`_backfill_watchlist_info`)

After `refresh_all_data()`, iterates all watchlist entries. For any with empty name/sector, calls `_resolve_stock_info` and saves.

### Storage

- **File:** `{STOCK_REPORTS_ROOT}/watchlist.json`
- **Schema:** `{ "stocks": [...], "sectors": [...], "updated_at": "ISO" }`

---

## `hot_sectors.py`

### Purpose

Fetch top-performing concept boards for the scanner's Layer 1 scoring bonus.

### Key Functions

| Function | Description |
|----------|-------------|
| `fetch_hot_sectors()` | Fetch and cache today's hot sectors |
| `get_hot_stock_set()` | Return set of stock codes in hot sectors |

### Data Sources

```
Primary: ak.stock_board_concept_name_em()
Fallback: East Money push2 API (push2.eastmoney.com/api/qt/clist/get)
```

### Caching

Daily cache file: `{STOCK_CACHE_DIR}/hot_sectors_{YYYY-MM-DD}.json`. Same-day calls return cached data.

---

## Storage Layout

```
C:/reports/stock/
├── watchlist.json
├── data/
│   └── {symbol}/
│       ├── daily.csv              # OHLCV history
│       ├── realtime.json          # Latest spot quote
│       ├── profile.json           # Company profile
│       └── news/
│           └── {YYYY-MM-DD}.json  # Daily news articles
├── models/
│   └── {symbol}/
│       └── ...                    # Model files (see ml-pipeline-impl.md)
├── .cache/
│   └── hot_sectors_*.json         # Hot sector daily cache
└── market_sentiment/
    └── ...                        # Sentiment cache (see market-signals-impl.md)
```
