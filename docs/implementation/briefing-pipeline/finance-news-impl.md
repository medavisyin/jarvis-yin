---
tags:
  - implementation
  - briefing-pipeline
  - finance-news
category: briefing-pipeline
status: current
last-updated: 2026-07-29
---

# Finance News Pipeline

> Replaces the former World News + China News audio split with a single **market-impact finance briefing**.

## Overview

`run-finance-news.py` fetches markets-oriented sources in parallel, merges + filters by market-impact policy, optionally translates via Ollama, and writes `finance-news/finance-news-data.json`. Daily Fetch generates one MP3: `finance-news.mp3`.

Legacy `run-world-news.py` remains on disk unused. Readers prefer finance paths and fall back to `world-news/` for historical dates (`finance_news_paths.finance_news_data_path`).

## Sources

| Script | Output JSON | Role |
|--------|-------------|------|
| `fetch-reuters.py` | `reuters.json` | Markets/business/world |
| `fetch-cnbc-markets.py` | `cnbc-markets.json` | US markets RSS (soft-fail) |
| `fetch-yahoo-finance.py` | `yahoo-finance.json` | Yahoo Finance RSS (soft-fail) |
| `fetch-china-news.py` | `china-news.json` | CLS / Sina finance / People Daily; Weibo/Toutiao gated |

## Filter

`scripts/pipeline/finance_news_filter.py`:

- Drop entertainment/sports; keep Fed/央行/tariff/熔断/earnings/…
- Default-deny if neither keep nor drop
- Attach `region` (`us`/`apac`/`china`/`global`) + `impact_score`
- Soft warn if kept count > 40 (no hard cap)

## Orchestrator CLI

```bash
python scripts/pipeline/run-finance-news.py --output-dir <dir>
python scripts/pipeline/run-finance-news.py --output-dir <dir> --no-fetch --no-translate
```

Outputs:

- `finance-news-data.json`
- `finance-news-timing.json`
- optional `warnings: ["no_international_finance_items"]`

## Daily Fetch steps

| Step | Purpose |
|------|---------|
| `refetch_finance` | Run fetchers + merge (`--no-translate`) |
| `finance_news_merge` | Recovery merge via `--no-fetch` |
| `finance_news_translate` | In-process Chinese translation |
| `finance_audio` | Segmented narration → `finance-news.mp3` |

Settings key: `audio_lang_finance` (default `zh`). UI: AI Briefing + Finance News only.

## Downstream

- `black_swan_detector.py` — finance path first
- Casual English — English titles from finance JSON
- Telegram `/fetch_step finance_audio`, sends `finance-news.mp3`

## Related docs

- Former world pipeline: [world-news-impl.md](./world-news-impl.md) (historical)
- Daily Fetch: [../personal/daily-fetch-impl.md](../personal/daily-fetch-impl.md)
- Plan: `docs/plans/2026-07-29-daily-fetch-finance-audio.md`
