---
tags:
  - implementation
  - briefing-pipeline
  - finance-news
category: briefing-pipeline
status: current
last-updated: 2026-08-30
---

# Finance News Pipeline

Six topic categories with a source catalog, per-category audio, RAG ingest, and Data Analysis summaries.

## Overview

`finance_sources.json` is the catalog (category + publisher + fetcher + default on/off). `run-finance-news.py` runs only enabled sources (`--sources` overrides). Merge writes `finance-news/finance-news-data.json` grouped by:

`markets` | `china-policy` | `us-political` | `crypto` | `gold` | `oil`

Daily Fetch generates **six** MP3s (`finance-markets.mp3`, `finance-china-policy.mp3`, `finance-us-political.mp3`, `finance-crypto.mp3`, `finance-gold.mp3`, `finance-oil.mp3`). No combined `finance-news.mp3`.

World geopolitics is a **separate** catalog (`run-world-news.py` → `world-news-data.json`) for the map UI; it is not a substitute for finance audio. Finance readers still prefer `finance-news/` and fall back to `world-news/` only for historical dates (`finance_news_paths.finance_news_data_path`).

## Catalog

See `scripts/pipeline/finance_sources.json`. Default-on: Reuters/CNBC/Yahoo (markets); PBOC, CSRC, 财联社, 第一财经 (China policy); AP, BLS, BEA, Census, ISM PMI, ADP, Fed, CNBC economy, Politico, MarketWatch (US); CoinDesk; Kitco + MINING.COM; EIA + OilPrice.

Weibo/Toutiao are **not** in the finance catalog. US/crypto/gold/oil drop Chinese-domain URLs.

Official sources (`keep_always`: BLS, BEA, Census, ISM, ADP, Fed, EIA, PBOC, CSRC, …) skip the default-deny market-impact filter. Census.gov is Cloudflare-blocked from some datacenter IPs (Playwright fallback). ISM World may bot-challenge or drop connections; Daily Fetch on a VPN/proxy path is the intended runtime.

Merge then folds **near-duplicate stories within each category** (title+summary Jaccard ≥ 0.5), keeping the lower catalog `priority`. Exact title match still drops first. **Yesterday's merged titles** (same key: lowercase, first 80 chars) are dropped so audio and RAG do not repeat the previous day's items. Two days ago is not consulted. Categories do not dedupe against each other. Audio, Reports, and RAG all read the merged JSON.

## Filter

`scripts/pipeline/finance_news_filter.py` still ranks non-official items (drop entertainment; keep Fed/央行/tariff/…; default-deny).

## Orchestrator CLI

```bash
python scripts/pipeline/run-finance-news.py --output-dir <dir>
python scripts/pipeline/run-finance-news.py --output-dir <dir> --sources kitco,eia
python scripts/pipeline/run-finance-news.py --output-dir <dir> --no-fetch --no-translate
```

Outputs:

- `finance-news-data.json`
- `finance-news-timing.json`
- optional `warnings: ["no_international_finance_items"]`

## Daily Fetch UI

Two-layer picker (category + publisher) persisted as `finance_sources_enabled` in Global Settings. Recreate / Refetch per category (`fn_audio:<id>`). Data Analysis → **Finance News Summary**: date range + categories → Chinese summary. Chat intent `finance_news` / tool `finance_news_summary` reads the same on-disk reports.

APIs: `GET/POST /api/toolbar/finance-sources`, `POST /api/toolbar/finance-news-summary`.

## RAG

`index_briefing.py` indexes finance items with `item_type=finance_news` and `doc_type=finance_news`, plus `category` / `date` / `source`. Default AI auto-RAG excludes these unless the query looks like finance.

## Related docs

- World geopolitics catalog: [world-news-impl.md](./world-news-impl.md)
- Map UI: [../personal/world-monitor-impl.md](../personal/world-monitor-impl.md)
- Daily Fetch: [../personal/daily-fetch-impl.md](../personal/daily-fetch-impl.md)
