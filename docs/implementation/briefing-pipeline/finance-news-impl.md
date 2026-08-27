---
tags:
  - implementation
  - briefing-pipeline
  - finance-news
category: briefing-pipeline
status: current
last-updated: 2026-08-27
---

# Finance News Pipeline

Six topic categories with a source catalog, per-category audio, RAG ingest, and Data Analysis summaries.

## Overview

`finance_sources.json` is the catalog (category + publisher + fetcher + default on/off). `run-finance-news.py` runs only enabled sources (`--sources` overrides). Merge writes `finance-news/finance-news-data.json` grouped by:

`markets` | `china-policy` | `us-political` | `crypto` | `gold` | `oil`

Daily Fetch generates **six** MP3s (`finance-markets.mp3`, `finance-china-policy.mp3`, `finance-us-political.mp3`, `finance-crypto.mp3`, `finance-gold.mp3`, `finance-oil.mp3`). No combined `finance-news.mp3`.

Legacy `run-world-news.py` remains on disk unused. Readers prefer finance paths and fall back to `world-news/` for historical dates (`finance_news_paths.finance_news_data_path`).

## Catalog

See `scripts/pipeline/finance_sources.json`. Default-on: Reuters/CNBC/Yahoo (markets); PBOC, CSRC, 财联社, 第一财经 (China policy); AP, BLS, Fed, CNBC economy, Politico (US); CoinDesk; Kitco; EIA + OilPrice.

Weibo/Toutiao are **not** in the finance catalog. US/crypto/gold/oil drop Chinese-domain URLs.

Official sources (`keep_always`: BLS, Fed, EIA, PBOC, CSRC, …) skip the default-deny market-impact filter.

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

- Former world pipeline: [world-news-impl.md](./world-news-impl.md) (historical)
- Daily Fetch: [../personal/daily-fetch-impl.md](../personal/daily-fetch-impl.md)
