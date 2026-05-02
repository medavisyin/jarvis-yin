# Market Signals Implementation

## Overview

Two modules provide market-wide risk signals that augment per-stock analysis: the **market sentiment fetcher** (Fear & Greed + VIX) and the **black swan detector** (world news risk scanning).

---

## Architecture & Design

```text
┌──────────────────────────────────────────────────────────────────┐
│  MARKET SENTIMENT (scripts/stock/market_sentiment.py)            │
│  fetch_fear_greed (alt.me → CNN)  → _save_cache("fear_greed")    │
│  fetch_vix (Yahoo query2 → query1) → _save_cache("vix")          │
│  fetch_all_sentiment → merge + _classify_mood → combined.json    │
└─────────────────────────────┬────────────────────────────────────┘
                              │ disk: STOCK_REPORTS_ROOT/market_sentiment/
                              ▼
        ┌─────────────────────────────────────────────────────────┐
        │  CONSUMERS                                              │
        │  · GET /api/stock/sentiment (refresh? → fetch vs cache)│
        │  · Train thread: fetch_all_sentiment → progress JSON   │
        │  · model_price_predictor: load_cached_sentiment →     │
        │    _add_sentiment_features (last row only)             │
        └─────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  BLACK SWAN (scripts/stock/black_swan_detector.py)               │
│  _load_world_news → world-news-data.json (today / yesterday)      │
│  _extract_text (headlines + body) → RISK_PATTERNS regex loop     │
│  severity tiers → alerts + _build_risk_summary → _save_result    │
└─────────────────────────────┬────────────────────────────────────┘
                              │ black_swan_alerts.json (+ cache helpers)
                              ▼
        ┌─────────────────────────────────────────────────────────┐
        │  CONSUMERS                                              │
        │  · GET /api/stock/blackswan (?refresh,?date → scan/load)│
        │  · GET /api/stock/risk/<symbol> → check_stock_risk     │
        │  · Train thread: scan_world_news → progress JSON        │
        │  · Stock UI cards (training report)                     │
        └─────────────────────────────────────────────────────────┘
```

---

## `market_sentiment.py` — Fear & Greed + VIX

### Purpose

Fetch global market sentiment indicators as reference signals for trading decisions and as model features.

### Data Sources

#### Fear & Greed Index

| Source | URL | Priority |
|--------|-----|----------|
| alternative.me | `https://api.alternative.me/fng/?limit=1&format=json` | Primary |
| CNN Business | `https://production.dataviz.cnn.io/index/fearandgreed/graphdata` | Fallback |

Returns: `{ value: 0-100, label: str, timestamp: str, source: str }`

#### VIX (CBOE Volatility Index)

| Source | URL | Priority |
|--------|-----|----------|
| Yahoo Finance (query2) | `query2.finance.yahoo.com/v8/finance/chart/%5EVIX` | Primary |
| Yahoo Finance (query1) | `query1.finance.yahoo.com/v8/finance/chart/%5EVIX` | Fallback |

Returns: `{ value: float, change_pct: float, timestamp: str, source: str }`

### Market Mood Classification (`_classify_mood`)

Based on Fear & Greed value + VIX value:

| Fear & Greed | VIX | Risk Level | Recommendation |
|-------------|-----|------------|----------------|
| ≤ 20 | any | `high_fear` | 极度恐慌，建议谨慎操作 |
| ≤ 40 | any | `fear` | 偏恐慌，建议降低仓位 |
| ≥ 80 | any | `high_greed` | 极度贪婪，建议减仓 |
| ≥ 60 | any | `greed` | 偏贪婪，注意风险 |
| 40–60 | any | `normal` | 按计划操作 |
| any | ≥ 30 | overrides to `high_fear` | VIX高波动/恐慌 |
| any | 20–30 | — | VIX偏高 (signal only) |

### Integration with ML Model

`model_price_predictor.py` calls `_add_sentiment_features(df)`:
- Reads `load_cached_sentiment()` → `combined.json`
- Adds `sent_fear_greed` (normalized 0–1) and `sent_vix` (raw) to **last row only**
- These features participate in feature selection and XGBoost training

### Caching

All data cached in `{STOCK_REPORTS_ROOT}/market_sentiment/`:
- `fear_greed.json`
- `vix.json`
- `combined.json` (both + market mood)

### API

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| `GET` | `/api/stock/sentiment` | `?refresh=1` | Fetch or return cached sentiment |

---

## `black_swan_detector.py` — World News Risk Scanner

### Purpose

Scan daily world news for high-impact events that may affect specific industries. Uses keyword/regex pattern matching against the Daily Fetch news pipeline output.

### Data Source

`world-news-data.json` from the Daily Fetch pipeline:
- Path: `{JARVIS_REPORTS_ROOT}/{YYYY-MM-DD}/world-news/world-news-data.json`
- Sources: 中国新闻 (Sina + People's Daily + CLS + Toutiao + Weibo), BBC, Reuters, AP, DW, Guardian
- English titles/summaries have Chinese translations (`title_zh`/`summary_zh`)
- Falls back to yesterday's data if today's is unavailable

### Risk Categories

| Type | Label | Keywords (sample) | Affected Industries |
|------|-------|--------------------|---------------------|
| `war` | 战争/军事冲突 | war, military, invasion, airstrike, 战争, 军事冲突 | 军工, 航空, 能源, 石油, 黄金, 航运, 保险 |
| `sanctions` | 制裁/贸易战 | sanctions, trade war, tariff, embargo, 制裁, 贸易战 | 半导体, 芯片, AI, 科技, 电子, 通信, 汽车, 农业 |
| `pandemic` | 疫情/公共卫生 | pandemic, epidemic, outbreak, virus, 疫情, 封锁 | 医药, 生物, 旅游, 航空, 餐饮, 酒店, 零售 |
| `financial_crisis` | 金融危机 | bank fail/collapse, recession, default, 金融危机, 债务违约 | 银行, 保险, 证券, 金融, 房地产, 信托 |
| `natural_disaster` | 自然灾害 | earthquake, tsunami, hurricane, flood, 地震, 台风 | 保险, 建筑, 农业, 能源, 航运, 旅游 |
| `regulation` | 监管政策突变 | antitrust, regulatory crackdown, 反垄断, 监管, 整顿 | 互联网, 游戏, 教育, 金融, 房地产, 医药 |
| `tech_ban` | 科技禁令/出口管制 | chip ban, semiconductor restrict, 芯片禁令, 技术封锁 | 半导体, 芯片, AI, 5G, 通信, 消费电子, 软件 |

### Severity Assessment

Per risk type:
- **high**: ≥ 3 matching headlines
- **medium**: ≥ 2 matching headlines
- **low**: 1 matching headline

### Overall Risk Level

| Level | Condition |
|-------|-----------|
| `critical` | ≥ 2 high-severity alerts |
| `high` | ≥ 1 high-severity alert |
| `elevated` | ≥ 2 medium-severity alerts |
| `low` | Any alerts (all low) |
| `normal` | No alerts |

### Per-Stock Risk Check (`check_stock_risk`)

Matches a stock's sector against alert `affected_industries`:
- Loads cached alerts
- Fuzzy matches sector name against industry list
- Returns matching alerts and max severity

### Integration Points

1. **Training report**: After training completes, `scan_world_news()` runs and results display in UI
2. **Per-stock API**: `GET /api/stock/risk/<symbol>` checks individual stock risk
3. **UI**: Black swan card in training report shows alerts, severity, and affected industries

### Caching

`{STOCK_REPORTS_ROOT}/market_sentiment/black_swan_alerts.json`

### APIs

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| `GET` | `/api/stock/blackswan` | `?refresh=1`, `?date=YYYY-MM-DD` | Scan or return cached alerts |
| `GET` | `/api/stock/risk/<symbol>` | — | Check individual stock risk |

---

## UI Integration

Both market sentiment and black swan data are automatically fetched at the end of each training run. The training report UI renders two cards at the top:

### Market Sentiment Card
- Fear & Greed gauge (0–100 with gradient bar)
- VIX value with change percentage
- Color-coded by mood: red (fear) → yellow (neutral) → green (greed)
- Recommendation text

### Black Swan Card
- Overall risk level (CRITICAL/HIGH/ELEVATED/LOW/NORMAL)
- Per-alert details: type, severity badge, match count, affected industries
- Color-coded border by risk level
