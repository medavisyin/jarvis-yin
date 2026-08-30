# Memory: Finance News Categories Expansion

**Generated**: 2026-08-27 ~08:50 UTC+8
**Last updated**: 2026-08-29 ~13:40 UTC+8
**Project**: c:\jarvis
**Focus**: Expand Daily Fetch Finance News into 6 categories with per-source fetch, per-category audio, RAG, and Data Analysis summaries

---

## Goal & Scope (required)

Expand Daily Fetch Finance News from one mixed market briefing + one MP3 into selectable sources, six topic categories, per-category audio, automatic RAG ingest, and a Data Analysis (plus chat) summary by date range + category. Trigger: too few sources — missing China policy-on-finance, US political/macro + media commentary, and crypto/gold/oil tracks. User has VPN; US-related news must be original foreign reporting, not Chinese media restating it.

---

## Key Decisions (required)

1. **Taxonomy = 6 categories**: Keep existing mixed market briefing as **综合市场**; add 中国政策金融, 美国政治金融, 数字货币, 黄金, 石油.
2. **Source picker = two layers**: Category on/off + publishers inside each category; re-fetch by category or by publisher.
3. **Data Analysis + chat**: New Data Analysis button (date range + one or more categories → Chinese summary). Chat can also query by time + category via RAG.
4. **Audio = 6 files only**: No combined `finance-news.mp3`.
5. **Official + media**: BLS (NFP/unemployment), Fed, EIA inventories, PBOC/CSRC/etc. plus media commentary.
6. **RAG ingest = automatic** after each Daily Fetch, tagged with date + category + source. No extra Index button required (force re-index can wait).
7. **Summary language = Chinese**; English titles/links may remain.
8. **China sources OK only for 中国政策金融**; US/crypto/gold/oil must use foreign original sources.
9. **Architecture A**: source catalog JSON + single orchestrator; `--sources` for per-publisher refetch.
10. **Source catalog v1 (default ON)**: China PBOC/CSRC/CLS/Yicai; US AP politics+business, BLS, Fed, CNBC economy, Politico Economy; crypto CoinDesk; gold Kitco; oil EIA + OilPrice; markets Reuters/CNBC/Yahoo.
11. **Default OFF (picker)**: 中国政府网, 证券时报, Treasury, MarketWatch, Reuters politics/crypto/metals/energy, The Block, WGC.
12. **Rejected: six independent pipelines** and **NewsAPI aggregator**.
13. **RAG**: same `ai_briefings` collection, payload `doc_type=finance_news` + date/category/source; AI search excludes these; finance queries filter to them.
14. **Audio filenames**: `finance-markets.mp3`, `finance-china-policy.mp3`, `finance-us-political.mp3`, `finance-crypto.mp3`, `finance-gold.mp3`, `finance-oil.mp3`. No combined `finance-news.mp3`.
15. **UI**: two-layer tree in Daily Fetch modal (persisted Global Settings); Data Analysis button + chat intent both use date+category summary.
16. **Execute directly** (no written plan) after design approval.
17. **Rejected: dedicated Qdrant collection**; **Rejected: settings-only source page**; **Rejected: chat-later**.

---

## Confirmed Assumptions (required)

- Existing 综合市场 line keeps Reuters / CNBC / Yahoo as the baseline (more publishers TBD in design).
- AI Briefing pipeline is unchanged.
- Scrape / RSS / API are all allowed; outbound US sites use existing proxy strategy.
- Concrete publisher list is locked to the v1 catalog (default ON vs OFF as in Key Decision 10–11).
- Downstream consumers of `finance-news.mp3` (Telegram, etc.) must be updated to six files.
- Each catalog row maps to exactly one category; same site may have multiple rows (different feeds).
- Soft-fail per source; empty category skips that mp3; RAG index failure warns only.

---

## Constraints & Non-Goals (include when relevant)

- Do not change AI Briefing fetch/audio.
- Do not use NewsAPI or paid aggregators in v1.
- Do not use Chinese media as the source for US/crypto/gold/oil news.

---

## Key Discoveries (required)

- Current finance pipeline: Reuters, CNBC Markets, Yahoo Finance, 中国财经 (财联社/新浪/人民日报). Categories: macro / policy / markets / corporate / geopolitics-market. One MP3: `finance-news.mp3`.
- Unused fetchers already on disk: `fetch-ap-news.py`, `fetch-bbc-news.py`, `fetch-guardian.py`, `fetch-dw-news.py`.
- Data Analysis toolbar currently has Trend Analysis and AI News KB only.
- Proxy/VPN path already exists: `scripts/fetchers/proxy_strategy.py`.
- Loaded session memory `memory-20260824-platform-update-summary.md` is unrelated to this task.

---

## Current State (required)

- **Working**: Source catalog includes US official macro v1 (BLS, BEA RSS, Census scrape, ISM PMI scrape, ADP NER scrape, Fed, MarketWatch default ON). Unit tests: `test_finance_sources` + `test_us_macro_sources`. Live fetch from this agent host: BEA 12 items, ADP 6 NER items; Census Cloudflare challenge; ISM connection dropped. User VPN/proxy still required for Census/ISM.
- **Pending**: Restart Jarvis; Recreate AI Briefing (zh); refetch 黄金; Daily Fetch Reports; follow-up code review of US macro sources.
- **Blocked**: Census.gov Cloudflare and ISM World empty-response from this datacenter IP (soft-fail).
- **Code review** (2026-08-27): first pass not merge-ready; accepted findings implemented this session. M2 rejected.

---

## Next Steps (required)

1. [x] Implement source catalog + orchestrator (`--sources`, enabled filter)
2. [x] Add/retarget fetchers for default-ON sources
3. [x] Per-category audio + Daily Fetch two-layer picker
4. [x] RAG ingest + Data Analysis summary + chat intent
5. [x] Update Telegram / docs; tests green
6. [x] Triage review findings (receiving-code-review) then apply accepted fixes
7. [x] US official macro v1 in 美国政治金融: BEA, Census, ISM, ADP; MarketWatch default ON (no 7th category)
8. [ ] Follow-up `requesting-code-review` (user gate)

---

## US official macro sources (2026-08-29)

Stay in **美国政治金融**. No dedicated economic-calendar crawler. No Chinese restatement of US prints.

| Report | Source |
|---|---|
| NFP / JOLTS / CPI | BLS `bls_latest.rss` (already on) |
| GDP / PCE | BEA `https://apps.bea.gov/rss/rss.xml` |
| Retail / durables / housing | Census scrape (+ RSS if not Cloudflare) |
| ISM manufacturing + services PMI | Scrape monthly `ism-pmi-reports/pmi|services/{month}/` |
| ADP NER | `mediacenter.adp.com` scrape |
| FOMC | Fed RSS (already on) |
| Commentary | CNBC Economy, AP, MarketWatch now default ON |

Live check 2026-08-29: BEA 12, ADP 6; Census CF interstitial; ISM `ERR_EMPTY_RESPONSE` from this host.

---

## Code Review Findings (2026-08-27)

Source: same-session reviewer. Severity preserved from reviewer.

### Critical
- **C1**: `daily_fetch.py` dropped `from config import JIRA_REPORT_SCRIPT, KNOWLEDGE_ROOT, REPORTS_ROOT` → `NameError` at module load (`JIRA_SCRIPT = JIRA_REPORT_SCRIPT` line 37). Jarvis will not start.
- **C2**: Category refetch passes `--sources`; `merge_source_jsons(..., enabled_ids=enabled)` rewrites the day's `finance-news-data.json` with only those sources. Gold refetch wipes other categories.

### Important
- **I1**: RAG index is Phase 3 **before** Phase 5 finance fetch; Daily Fetch refetch never calls `index_briefing`. Auto-ingest does not actually run.
- **I2**: Only `auto_rag_search` strips `finance_news`; `tool_rag_search` / `briefing_search` do not. Keyword gate is leaky.
- **I3**: Daily Fetch `fetch_sources` timeout still **600s** vs inner finance **900s**; full run also always runs `refetch_finance` again (double fetch).
- **I4**: CLS/Yicai lack `keep_always`; default-deny filter can empty china-policy.
- **I5**: AP Playwright vs 120s `PER_SCRIPT_TIMEOUT` — often TIMEOUT.
- **I6**: No tests for subset-merge-not-wiping or post-finance ingest.
- **I7**: Picker needs explicit Save; Run Today's Fetch does not POST current checkboxes.

### Minor
- **M1** duplicate CNBC RSS; **M2** `scripts_to_run` doesn’t really dedupe; **M3** unknown source_id can crash `fetch-rss-source`; **M4** `reuters-politics` is world RSS; **M5** empty cats stay in `missing_steps`; **M6** stock heuristics steal finance_news; **M7** docs still say two MP3s in overview; **M8** China-domain list omits weibo/toutiao.

---

## Notes for Next Session (include when relevant)

- Question channel this session: `AskQuestion`
- Related older memories: `memory-20260803-daily-fetch-voice-finance.md`, `memory-20260821-daily-fetch-audio-global-lang.md`

---

## References (required)

- `scripts/pipeline/run-finance-news.py` — current orchestrator
- `scripts/pipeline/finance_news_filter.py` — market-impact filter
- `scripts/rag/routes/daily_fetch.py` — Daily Fetch steps + finance audio
- `docs/implementation/briefing-pipeline/finance-news-impl.md` — current finance docs
- `scripts/rag/templates/index.html` — Data Analysis + Daily Fetch UI
- `scripts/pipeline/finance_sources.json` — source catalog (to add)
- `scripts/pipeline/finance_sources.py` — catalog loader (to add)

---

**Confirmed at**: 2026-08-27 ~08:50 UTC+8
