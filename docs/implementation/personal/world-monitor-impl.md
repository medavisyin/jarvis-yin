---
tags:
  - implementation
  - personal
  - world-monitor
category: personal
status: current
last-updated: 2026-09-20
---

# World Monitor (Jarvis-native)

News → **World monitor** (`/news/monitor`). A map + Headlines dashboard built from Daily Fetch `world-news-data.json` (and finance / AI briefing JSON for some variants). Local Ollama only.

This is **not** a copy of [World Monitor](https://www.worldmonitor.app/docs) (AGPL-3.0). We do not vendor their source, do not call `api.worldmonitor.app`, and do not implement live CII / AIS / ADS-B.

World-news **fetch** is documented separately: [world-news-impl.md](../briefing-pipeline/world-news-impl.md). Session decisions: `docs/memory/memory-20260920-worldmonitor-daily-fetch.md`.

## What the page does

| Control | Effect |
|---------|--------|
| World / Tech / Finance / Commodity / Happy / Energy | Reloads dashboard. Headlines and map points use that variant’s layer catalog and item pool. |
| 3D 地球 / 2D 地图 | Same points. 3D = `globe.gl` (Three.js). 2D = HTML equirectangular image + projected dots (not deck.gl). |
| 1d / 2d / 5d / 7d | Last **N dated folders that contain** `world-news-data.json` (skips empty calendar days). |
| Map layer checkboxes | Filter both globe dots and Headlines (`layers` on each headline). |
| Click a hub | Headlines filter to that city/country; `POST /insight` asks local Ollama for ≤120 字. |

## Data flow

```
Daily Fetch date folders
  {REPORTS_ROOT}/{YYYY-MM-DD}/world-news/world-news-data.json
  {REPORTS_ROOT}/{YYYY-MM-DD}/finance-news/finance-news-data.json
  {REPORTS_ROOT}/{YYYY-MM-DD}/briefing-data(-filtered).json   # tech variant AI items
        │
        ▼
GET /api/toolbar/world-monitor?date=&variant=&lookback=
        │  scripts/pipeline/world_monitor.py :: build_dashboard
        │  geo_hubs.infer_hubs(title+summary) → lat/lon
        │  classify_streams / news_category / finance_category → layer ids
        ▼
JSON: points, headlines (with layers[]), correlation, finance_radar, panels
        │
        ▼
WorldMonitorPage.tsx
  DualMap (pointsForLayers)
  Headlines (headlinesForLayers then headlinesForHub)
        │ click hub
        ▼
POST /api/toolbar/world-monitor/insight  { date, variant, lookback, hub_id }
        │  ollama_hub_insight → OLLAMA_HOST / OLLAMA_MODEL_FAST
        ▼
Chinese insight shown only if classifyInsight === "ok"
```

## Variant item pools

| Variant | Headline / map pool | Typical layers |
|---------|---------------------|----------------|
| `world` | World-news items | politics, military, economic, disaster, escalation |
| `tech` | World-news + AI briefing items | `news_technology`, `news_science` |
| `finance` | Finance-news items | `finance_exchanges`, commodities, crypto, economic |
| `commodity` / `energy` | Finance + world | commodities + `energy` keyword |
| `happy` | World-news | `happy` keyword |

An item is dropped if it has **no layer in that variant’s catalog**. That is why World vs Tech Headlines differ.

## Lookback

`recent_report_days(root, end, n)` lists dated folders `≤ end` that contain world-news JSON, newest first, take `n`. Merge dedupes by URL then title. CII was removed; lookback does **not** recompute a country index.

Empty calendar days (e.g. 9/19–9/14 with no world-news file) are skipped, so 7d is not “the last 7 calendar days”.

## Map engines

`globe.gl` keeps a WebGL context. A second WebGL stack (`deck.gl` BitmapLayer) lost the 2D context (white canvas). 2D therefore uses `equirectangularProject` on an earth JPEG. Do not put deck.gl on the same page as the globe.

## HTTP

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/toolbar/world-monitor` | Query: `date`, `variant`, `lookback` ∈ {1,2,5,7} |
| POST | `/api/toolbar/world-monitor/insight` | Body: same + `hub_id` |
| GET/POST | `/api/toolbar/world-sources` | Catalog + `world_sources_enabled` (Settings / Daily Fetch) |

SPA fallback in `spa_static.py` must not treat unknown `/api/*` POST as GET-only HTML (that produced **HTTP 405** painted as the first “headline”). API misses should 404. `classifyInsight` hides `HTTP 4xx` / `Method Not Allowed`.

Blueprint: `scripts/rag/routes/world_monitor.py`, registered from `agent.py`.

## Frontend files

| File | Role |
|------|------|
| `web/src/pages/NewsPage.tsx` | Tab `monitor` |
| `web/src/lib/newsTabs.ts` | `/news/monitor` |
| `web/src/features/news/worldMonitor/WorldMonitorPage.tsx` | Toolbar, layers, Headlines |
| `web/src/features/news/worldMonitor/DualMap.tsx` | 3D + 2D |
| `web/src/lib/worldMonitor.ts` | Types, layer filter, hub filter, insight classifier |
| `web/src/features/news/WorldSourcesCard.tsx` | Settings picker |

After UI changes: `cd web && npm run build`, then **Ctrl+F5**. Python route changes need an **agent restart**.

## Backend files

| File | Role |
|------|------|
| `scripts/pipeline/world_monitor.py` | Dashboard assembly, variants, insight prompt |
| `scripts/pipeline/geo_hubs.json` / `geo_hubs.py` | Keyword → hub lat/lon |
| `scripts/pipeline/world_sources.json` / `world_sources.py` | Fetch catalog |
| `scripts/fetchers/news/fetch-world-rss.py` | Catalog-driven RSS (人民日报, 新华, Al Jazeera, …) |

## Tests

- `tests/test_world_monitor.py` — variants, lookback, no CII
- `tests/test_world_monitor_routes.py` — GET payload, lookback, insight POST
- `tests/test_world_sources.py` / `test_world_source_routes.py` / `test_fetch_world_rss.py`
- `tests/test_geo_hubs.py`
- `tests/test_agent_spa.py` — POST `/api/*` is not 405 HTML
- `web/src/lib/worldMonitor.test.ts`

## Explicitly out of scope

- World Monitor AGPL source, paid REST, live CII v8
- ACLED / GDELT / AIS / ADS-B / NASA FIRMS (deferred)
- YouTube Live News panel (deferred)
- Date picker and whole-dashboard Ollama brief button
- World-news MP3 (finance audio stays; world catalog is for the map)
