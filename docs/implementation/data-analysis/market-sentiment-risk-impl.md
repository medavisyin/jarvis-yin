---
tags:
  - implementation
  - data-analysis
  - market-sentiment-risk
category: data-analysis
status: current
last-updated: 2026-04-28
---

# Market Sentiment & Risk Detection

> **Category**: DATA ANALYSIS | **Source**: `scripts/stock/market_sentiment.py`, `scripts/stock/black_swan_detector.py`, `scripts/stock/china_market_data.py`, `scripts/stock/hot_sectors.py`

## Overview

This cluster measures **global-style fear/greed and VIX**, scans **world news for thematic “black swan” risk**, pulls **A-share–specific flows and institutional footprints** (northbound, per-stock and market fund flow, Dragon-Tiger (LHB), margin, limit-up/down temperature, **national-team ETF share monitoring**), and surfaces **rotating hot sectors** for scanners and overlays.

## Architecture & Design

### System Context

```text
market_sentiment.fetch_all_sentiment ──► cache under STOCK_REPORTS_ROOT/market_sentiment
black_swan_detector.scan_world_news ──► alerts + sector mapping
china_market_data.* ──► caches (.cache subdirs) + national_team markdown for RAG
hot_sectors.fetch_hot_sectors ──► daily JSON cache + stock code sets
```

### Data Flow

1. **Fear & Greed**: `fetch_fear_greed` tries `api.alternative.me/fng` then CNN `production.dataviz.cnn.io` JSON; `_save_cache` per component (`market_sentiment.py`).
2. **VIX**: Yahoo chart API with `_parse_yahoo_vix` (`fetch_vix`).
3. **Combined mood**: `fetch_all_sentiment` builds `market_mood` via `_classify_mood` (thresholds on FG and VIX) and `_mood_recommendation` text.
4. **Black swan**: `scan_world_news` loads `JARVIS_REPORTS_ROOT/{date}/world-news/world-news-data.json`, regex-matches `RISK_PATTERNS` categories, emits `alerts` with severity and `affected_industries`; `check_stock_risk` matches sector strings (`black_swan_detector.py`).
5. **China flows**: `fetch_northbound` / `northbound_momentum`; `fetch_stock_fund_flow` / `stock_fund_flow_signals` / `detect_smart_money_accumulation`; `fetch_lhb_*` / `stock_lhb_activity`; `fetch_margin_data` / `margin_sentiment`; `fetch_limit_pool` / `market_temperature`; `national_team_monitor` aggregates `CORE_ETF_LIST` shares, anomaly detection, history append, `_save_national_team_knowledge` markdown (`china_market_data.py`).
6. **Hot sectors**: `fetch_hot_sectors` prefers akshare concept boards with constituents; falls back to Eastmoney API; daily file in `STOCK_CACHE_DIR` (`hot_sectors.py`).

### Key Design Decisions

- **Caching**: Most China endpoints use `_cache_fresh` with hour-based TTLs to limit akshare load (`china_market_data.py` `_cache_fresh`).
- **National team**: Interprets broad ETF total share changes (&gt;5% “大幅增持” etc.) and per-ETF &gt;3% moves as anomalies (`_detect_share_anomalies`).
- **Black swan severity**: Based on headline match count per risk type (`scan_world_news` 128–137).

## Implementation Details

### Core Components

| Module | Key entrypoints |
|--------|-----------------|
| `market_sentiment.py` | `fetch_fear_greed`, `fetch_vix`, `fetch_all_sentiment`, `load_cached_sentiment`, `_classify_mood` |
| `black_swan_detector.py` | `scan_world_news`, `load_cached_alerts`, `check_stock_risk`, `RISK_PATTERNS` |
| `china_market_data.py` | `fetch_northbound`, `northbound_momentum`, `fetch_stock_fund_flow`, `stock_fund_flow_signals`, `fetch_lhb_institutional`, `margin_sentiment`, `market_temperature`, `national_team_monitor`, `fetch_all_china_data` |
| `hot_sectors.py` | `fetch_hot_sectors`, `get_hot_stock_set` |

### API Surface

- **CLI**: `python market_sentiment.py` prints `fetch_all_sentiment`; `hot_sectors.py` **main** lists top sectors.
- **Library**: Consumed by `features.py` (fund flow, northbound, mood), `model_price_predictor._add_sentiment_features`, `llm_reasoning._build_deepseek_prompt`, `long_term_scanner._collect_signals`, `scanner._layer1_quick_filter`.

### Configuration

- `STOCK_REPORTS_ROOT`, `STOCK_CACHE_DIR`, `STOCK_PROXY` env for requests proxies.
- `_CACHE_DIR` sentiment: `{STOCK_REPORTS_ROOT}/market_sentiment`.
- `JARVIS_REPORTS_ROOT` (default `C:/reports/ai`) for world news and national-team knowledge markdown subtree.

### Error Handling & Edge Cases

- VIX / FG: log warnings and partial `None` values if all sources fail.
- Northbound: if series all NaN, returns zeroed `northbound_momentum` with `"无数据"` trend (`china_market_data.py` 131–133).
- Hot sectors: empty list if both akshare and Eastmoney fail.

## Code Walkthrough

- **Mood classification**

```149:175:scripts/stock/market_sentiment.py
def _classify_mood(fg_value, vix_value) -> dict:
    """Classify overall market mood from fear/greed + VIX."""
    signals = []
    risk_level = "normal"

    if fg_value is not None:
        if fg_value <= 20:
            signals.append("极度恐惧 (Extreme Fear)")
            risk_level = "high_fear"
        elif fg_value <= 40:
            signals.append("恐惧 (Fear)")
            risk_level = "fear"
        elif fg_value >= 80:
            signals.append("极度贪婪 (Extreme Greed)")
            risk_level = "high_greed"
        elif fg_value >= 60:
            signals.append("贪婪 (Greed)")
            risk_level = "greed"
        else:
            signals.append("中性 (Neutral)")

    if vix_value is not None:
        if vix_value >= 30:
            signals.append(f"VIX {vix_value:.1f} — 高波动/恐慌")
```

- **Black swan match loop**

```116:137:scripts/stock/black_swan_detector.py
    for risk_type, config in RISK_PATTERNS.items():
        matched = []
        for headline, body in all_text:
            combined = f"{headline} {body}"
            for pat in config["keywords"]:
                if re.search(pat, combined, re.IGNORECASE):
                    matched.append(headline)
                    break

        if matched:
            severity = "high" if len(matched) >= 3 else "medium" if len(matched) >= 2 else "low"
            alerts.append({
                "type": risk_type,
                "label": config["label"],
                "severity": severity,
```

- **National team snapshot**

```802:867:scripts/stock/china_market_data.py
def national_team_monitor() -> dict:
    """监控国家队核心ETF份额变化。"""
    ...
    for etf in CORE_ETF_LIST:
        share = _get_etf_share(etf["code"], sse_df, szse_df)
        ...
    _detect_share_anomalies(result)
    ...
    _append_history(result)
    _save_national_team_knowledge(result)
```

- **Hot sector cache**

```54:62:scripts/stock/hot_sectors.py
    cache = _cache_path()
    if os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                log.info("使用缓存的热门板块数据 (%d 个板块)", len(data))
                return data
```

## Improvement Ideas

### Short-term

- Wire push alerts when `market_mood.risk_level` is `high_fear` / `high_greed` or black swan `severity == "high"`.

### Medium-term

- Correlation dashboard: northbound vs. index returns; margin balance vs. breadth.

### Long-term

- Custom risk pattern packs per portfolio; cross-market signals (HK, US ADRs) unified with A-share flows.

## References

- `scripts/stock/market_sentiment.py`, `scripts/stock/black_swan_detector.py`
- `scripts/stock/china_market_data.py`, `scripts/stock/hot_sectors.py`
- `scripts/stock/features.py`, `scripts/stock/scanner.py`, `scripts/stock/long_term_scanner.py`
