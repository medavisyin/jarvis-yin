---
tags:
  - implementation
  - briefing-pipeline
  - world-news
category: briefing-pipeline
status: current
last-updated: 2026-09-20
---

# World News Pipeline

Geopolitics RSS catalog (same pattern as finance). Daily Fetch writes `world-news/world-news-data.json`. The map UI reads that JSON: [world-monitor-impl.md](../personal/world-monitor-impl.md).

There is **no** world MP3 in this round. Finance audio stays on `finance-news/`. 微博 / 头条 / 新浪 / 财联社 are **not** in the world catalog (财联社 stays finance).

## Catalog

`scripts/pipeline/world_sources.json` — category + publisher + fetcher + default on/off.

Default-on (2026-09-20):

| id | Display | Fetcher |
|----|---------|---------|
| bbc-news | BBC World News | `fetch-bbc-news.py` |
| reuters | Reuters | `fetch-reuters.py` |
| ap-news | AP News | `fetch-ap-news.py` (scrape) |
| dw-news | Deutsche Welle | `fetch-dw-news.py` |
| guardian | The Guardian | `fetch-guardian.py` |
| peoples-daily | 人民日报 | `fetch-world-rss.py` |
| xinhua | 新华社 | `fetch-world-rss.py` |
| al-jazeera | Al Jazeera | `fetch-world-rss.py` (publisher RSS, not WM `_feeds.ts`) |
| the-diplomat | The Diplomat | `fetch-world-rss.py` |
| kyiv-independent | Kyiv Independent | `fetch-world-rss.py` |

`fetch-china-news.py` remains on disk unused by the catalog.

Settings persist `world_sources_enabled`. APIs: `GET/POST /api/toolbar/world-sources`.

## Orchestrator

```bash
python scripts/pipeline/run-world-news.py --output-dir <dir>
python scripts/pipeline/run-world-news.py --output-dir <dir> --sources bbc-news,xinhua
python scripts/pipeline/run-world-news.py --output-dir <dir> --no-fetch --no-translate
```

`run-all-sources.py` runs this as its world-news phase (after finance). Daily Fetch steps: `world_news_merge`, `world_news_translate`, optional `refetch_world`. `run-all-sources` timeout is 2400s to cover both finance and world fetch.

Flow:

```
run-world-news.py
  ├── Parallel fetch (enabled catalog rows)
  ├── Merge (world_sources.merge_source_jsons)
  │     cluster same-event titles (hash / Jaccard); drop dated items older than 96h;
  │     source-tier canonical row; drop yesterday’s titles; group by category
  ├── Translate English → Chinese via Ollama (optional --no-translate)
  └── world-news-data.json + world-news-timing.json
```

Partial fetcher failure still writes merge JSON (`sources_unavailable` listed).

## Output

`{REPORTS_ROOT}/{YYYY-MM-DD}/world-news/world-news-data.json`

Categories: `politics` | `economics` | `technology` | `science`. Items keep `title`, `title_zh`, `summary`, `source`, `url`, plus `sources` / `source_count` / `source_tier` / `story_hash` after clustering.

## Daily Fetch UI

`WorldSourcesCard` on Settings + Daily Fetch: per-source checkboxes, item counts, Recreate/Refetch world steps via `refetchWorldNewsSteps()` in `web/src/lib/dailyFetch.ts`.

## Tests

`tests/test_world_sources.py`, `tests/test_world_source_routes.py`, `tests/test_fetch_world_rss.py`, `tests/test_daily_fetch_schedule.py` (NEWS_ONLY_STEPS includes world merge/translate).
