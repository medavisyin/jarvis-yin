# Memory: World Monitor vs Daily Fetch

**Generated**: 2026-09-20 ~13:10 UTC+8
**Last updated**: 2026-09-20 ~17:20 UTC+8
**Project**: c:\jarvis
**Focus**: Jarvis-native World monitor: map + hub Headlines + lookback + layer/variant filters + local Ollama hub insight

---

## Goal & Scope (required)

Daily Fetch world-news on a Jarvis-native map (globe.gl 3D + HTML 2D). Click a hub → Headlines filter to that place + Ollama insight. Map layers time window is 1d/2d/5d/7d calendar Daily Fetch folders. No World Monitor source (AGPL). Local Ollama only.

---

## Key Decisions (required)

1. **Loaded** `memory-20260920-deeptutor-comparison.md` at session start (unrelated living-book work still pending).
2. **This round = analysis only** (option A). No Jarvis edits, no plan unless asked later.
3. **Confirmed understanding**: Daily Fetch news vs World Monitor news+map; AGPL means do not copy WM source into Jarvis git.
4. **Verdict**: Feasible as a **Jarvis-native** map on existing JSON; not feasible/wise to vendor or self-host WM as the Daily Fetch UI.
5. **Stop after analysis**: User chose not to design or implement this round.
6. **Reversed: stop after analysis**: User wants a map, but only after **world-news is back in Daily Fetch**.
7. **News gap is geography, not count**: Last 7 days finance ~36–111 items/day (avg 74); AI briefing ~30–36. World-news last run 2026-07-28 had 128 items (72 politics). Finance is US-heavy; ~15/30 finance sources fail daily.
8. **Sources = B**: international wires + 人民日报/新华; no 微博/头条.
9. **Approach B approved**: `world_sources.json` catalog like finance.
10. **Architecture/components/data-flow/error-handling/testing all approved**.
11. **Execute directly** (no written plan). **Update this memory** with the approved design.
12. **Phase 1 no world MP3**. Map is Phase 2.
13. **Do not copy** `C:\\Users\\...\\Downloads\\worldmonitor-main` into Jarvis git (AGPL). Rewrite native.
14. **2D is HTML equirectangular map**, not deck.gl: dual WebGL (Three.js + deck.gl) lost the 2D context (white canvas).
15. **Headlines filter + hub Ollama insight** on light-point click (not just highlight).
16. **Lookback 1d/2d/5d/7d** = last N Daily Fetch folders **that contain world-news JSON** (skip empty calendar days). Calendar-only 7d was identical to 1d because 2026-09-19…14 have no world-news.
17. **Rejected: date picker + top Ollama brief**: toolbar has variants + 3D/2D + lookback only. Local AI is per-hub insight in Headlines.
18. **CII-J1 removed** (2026-09-20): keyword-count instability table was not useful. No CII panel, map layer, or payload field.
19. **Execute lookback/insight directly** (no written plan).
20. **HTTP 405 on insight**: SPA GET-only catch-all matched POST `/world-monitor/insight` when the old agent lacked the route. Insight errors must not render as Headlines. Agent restarted 2026-09-20 ~16:30.
21. **Do not wire Jarvis to `api.worldmonitor.app`** unless the user buys an API key. Hosted REST is a paid product (API Starter $99.99/mo, 1000 req/day), not a drop-in replacement for Daily Fetch RSS. More OSINT data yes; our 人民日报/新华 and local lookback would not get faster.
22. **World RSS expand (2026-09-20)**: add Al Jazeera / The Diplomat / Kyiv Independent via publisher RSS (not WM `_feeds.ts`). USGS/EONET and YouTube Live deferred.
23. **Headlines follow variant + map layers (2026-09-20)**: variants were requesting but still returning all world items; layer checkboxes only hid map dots. Headlines now use the same layer membership as points.

---

## Confirmed Assumptions (required)

- User wants Daily Fetch’s own news on a similar situational map, not the full 578-host OSINT product.
- Local Ollama only (no Groq/OpenRouter).
- Finance stays; 财联社 stays in finance, not duplicated in world.
- 1d = today's `world-news-data.json`; 7d = union of last 7 calendar folders, dedupe by url/title.
- Clicking a hub still filters Headlines by `hub_ids` / `country_ids`.

---

## Constraints & Non-Goals

- World Monitor is **AGPL-3.0-only**. Copying `rss.ts` / map components would infect Jarvis.
- Do not vendor WM into the Jarvis git tree.
- Do not vendor WM; no live CII v8 / AIS / flights. Jarvis CII-J1 was removed.
- No cloud LLM. No date picker on World monitor. No whole-dashboard Ollama brief button.

---

## Approved design (Phase 1)

- `world_sources.json`: default BBC / Reuters / AP / DW / Guardian / 人民日报 / 新华 / Al Jazeera / The Diplomat / Kyiv Independent.
- Refactor `run-world-news.py` to catalog + `--sources` / `--no-fetch` / `--no-translate` like finance.
- Extract 人民日报/新华 as RSS fetchers; leave `fetch-china-news.py` on disk unused by catalog.
- `NEWS_ONLY_STEPS` add `world_news_merge` + `world_news_translate`.
- Fetch via `run-all-sources` new phase (same pattern as finance Phase 5).
- Settings `world_sources_enabled`; API `/api/toolbar/world-sources`.
- Daily Fetch UI: source picker + item count. Partial fetcher failure still writes JSON.

---

## Key Discoveries (required)

- **World Monitor** geo is keyword hubs (`inferGeoHubsFromTitle`), not LLM on the hot path.
- **Jarvis** finance has region but no lat/lon; no map library in `web/`.
- World-news stopped after **2026-07-28**. `_count_finance_news_items` still falls back to world-news for pre-finance dates; new dates use finance path first.
- **2D white canvas**: deck.gl WebGL context lost while globe.gl Three.js is on the page; BitmapLayer ±90 also invalid in Mercator. 2D now uses `equirectangularProject` + earth JPEG.
- Local AI on this page was only `POST /world-monitor/brief` (≤180字全盘). User wants per-hub `POST /world-monitor/insight` instead.

---

## Current State (required)

- **Working**: Native `/news/monitor`; lookback = N folders with world-news JSON; Headlines follow variant + map layers; insight POST; 10 default world RSS sources; CII-J1 removed; SPA POST `/api/*` is 404 not 405.
- **Docs**: `docs/implementation/personal/world-monitor-impl.md` and updated `world-news-impl.md`.
- **Pending**: USGS/EONET layers and YouTube Live News (user deferred). Next Daily Fetch picks up Al Jazeera / Diplomat / Kyiv Independent.
- **Do not mix**: living-book / stock scanner dirty files.

---

## Next Steps (required)

1. [x] Phase 1 world-news catalog.
2. [x] Native map UI (3D globe.gl, 2D HTML).
3. [x] Hub Headlines + lookback + insight.
4. [x] Variant + layer Headlines.
5. [ ] USGS/EONET or Live News if requested.

---

## Notes for Next Session

- Living-book UI (DeepTutor memory) is a separate in-progress track; do not mix commits.
- Do not re-propose vendoring World Monitor or wiring `api.worldmonitor.app` (user chose skip).

---

## References (required)

- `docs/implementation/personal/world-monitor-impl.md`
- `docs/implementation/briefing-pipeline/world-news-impl.md`
- `docs/implementation/personal/daily-fetch-impl.md`
- `docs/implementation/briefing-pipeline/finance-news-impl.md`
- `scripts/pipeline/world_sources.py`
- `scripts/pipeline/world_monitor.py`
- `scripts/rag/routes/world_monitor.py`
- `web/src/features/news/worldMonitor/WorldMonitorPage.tsx`
- `web/src/features/news/worldMonitor/DualMap.tsx`
- `web/src/lib/worldMonitor.ts`

---

**Confirmed at**: 2026-09-20 ~17:20 UTC+8
