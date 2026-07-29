# Daily Fetch Finance Audio Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Replace Daily Fetch World/China news audio with a single market-impact finance briefing (`finance-news.mp3`), by renaming the world-news pipeline to finance-news and swapping sources + filtering.

**Architecture:** Approach B — full rename. `run-world-news.py` becomes `run-finance-news.py` writing `REPORTS_ROOT/YYYY-MM-DD/finance-news/finance-news-data.json`. Fetch scripts target markets/policy sources (Reuters business/markets, CNBC or Yahoo Finance RSS, China CLS/Sina finance, etc.). A pure-Python market-impact filter + scorer runs at merge time; filtered items (no hard cap) feed one `finance_audio` step. UI/Settings collapse to AI + Finance. Downstream readers (`black_swan_detector`, Casual English) prefer `finance-news/` with fallback to legacy `world-news/`.

**Tech Stack:** Python 3, existing fetcher patterns (`feedparser`/`httpx`/`playwright` + `proxy_strategy`), Ollama translation, Edge TTS narration in `scripts/rag/routes/daily_fetch.py` + `ai_news.py`, Flask Daily Fetch UI in `scripts/rag/templates/index.html`, pytest.

**Approved decisions (do not re-litigate):**
- Keep AI Briefing; one finance audio only
- Chinese default; `audio_lang_finance` in Global Settings
- Transform existing pipeline (not a parallel second pipeline)
- Filter then include **all** surviving items in audio
- Old World/China MP3s not shown in history UI
- Prefer finance path; fallback read old `world-news/` for historical dates only

**Out of scope:** email digest, auto-scheduling, deleting unused old fetcher files (leave on disk, remove from orchestrator list), rewriting all markdown guides beyond the primary impl doc.

---

## Plan amendments (from critical review 2026-07-29)

Do not re-open design; these are executor constraints:

1. **Test imports:** Do **not** use `from scripts.pipeline...`. Follow repo test style: `sys.path.insert` for `scripts/pipeline` (or `scripts`), then `import finance_news_filter`.
2. **Telegram bot is in scope:** Update `scripts/bot_telegram.py` step names (`world_audio`/`china_audio` → `finance_audio`) plus `docs/guides/telegram-bot-guide.md`. Include `scripts/bot_telegram.py` in the Task 9 `rg` sweep.
3. **`--no-fetch`:** `run-world-news.py` does **not** currently define it (daily_fetch probes help and falls back to `merge_news()`). **`run-finance-news.py` MUST implement `--no-fetch`** (merge + write JSON only; skip subprocess fetchers). Prefer the CLI path over importlib.
4. **Legacy orchestrator file:** Stop all callers; **keep `run-world-news.py` on disk unused** (do not delete, do not add shim).
5. **Filter policy (locked):** hit drop-signal → discard; hit keep-signal → keep with score; hit neither → **discard** (finance-source default-deny). Define `MIN_SCORE` (e.g. keep only `score > 0`). Log a warning if kept count &gt; 40 (no hard cap — user choice C).
6. **Intl source soft warning:** If merge finishes with zero non-China items, set `warnings` on merged JSON / step output (do not abort). APAC coverage is **best-effort** via Reuters/CNBC keywords (no dedicated KR/JP fetcher in v1).
7. **Casual English:** Path swap only; keep CJK-title skip behavior; do not redesign the learning product.
8. **UI settings:** Remove both `settAudioWorld` and `settAudioChina` (and save/load) so JS never references missing elements.
9. **Docs:** Task 8 must update `docs/implementation/personal/daily-fetch-impl.md` audio section alongside new `finance-news-impl.md`.

---

### Task 1: Market-impact filter (TDD)

**Files:**
- Create: `scripts/pipeline/finance_news_filter.py`
- Create: `tests/test_finance_news_filter.py`

**Step 1: Write failing tests**

```python
# tests/test_finance_news_filter.py
import os
import sys

_PIPELINE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline"))
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from finance_news_filter import (  # noqa: E402
    score_market_impact,
    filter_and_rank_items,
    assign_region,
)

def test_keeps_circuit_breaker_and_fed():
    items = [
        {"title": "Korea stock market hits circuit breaker", "summary": "KOSPI plunges 8%", "source": "Reuters"},
        {"title": "Celebrity wedding draws fans", "summary": "Entertainment news", "source": "Weibo"},
        {"title": "Fed signals rate cut", "summary": "Powell speech", "source": "CNBC"},
    ]
    out = filter_and_rank_items(items, report_date="2026-07-29")
    titles = [i["title"] for i in out]
    assert any("circuit breaker" in t.lower() for t in titles)
    assert any("Fed" in t for t in titles)
    assert not any("Celebrity" in t for t in titles)

def test_assign_region_china_us_apac():
    assert assign_region({"title": "PBOC cuts RRR", "source": "财联社"}) == "china"
    assert assign_region({"title": "S&P 500 futures jump", "source": "CNBC"}) == "us"
    assert assign_region({"title": "Nikkei surges on BOJ", "source": "Reuters"}) == "apac"

def test_higher_impact_sorts_first():
    items = [
        {"title": "Minor midcap earnings beat", "summary": "small company", "source": "Yahoo"},
        {"title": "Trump announces new China tariffs", "summary": "trade war", "source": "Reuters"},
    ]
    out = filter_and_rank_items(items, report_date="2026-07-29")
    assert "tariff" in out[0]["title"].lower() or "Trump" in out[0]["title"]
```

**Step 2: Run tests — expect FAIL**

```bash
python -m pytest tests/test_finance_news_filter.py -v
```

Expected: import/collection errors or failed asserts.

**Step 3: Implement `finance_news_filter.py`**

Implement:
- Keyword/regex tables for keep signals (央行/Fed/tariff/熔断/circuit breaker/制裁/财报/IPO/利率/…）and drop signals (娱乐/体育/…)
- **Policy:** drop-hit → discard; keep-hit → score; neither → discard (`MIN_SCORE` / keep only `score > 0`)
- `score_market_impact(item) -> int`
- `assign_region(item) -> "us"|"apac"|"china"|"global"` (source tags + title keywords)
- `is_same_day(item, report_date) -> bool` — keep undated items but mark `date_uncertain=True` and slightly lower score
- `filter_and_rank_items(items, report_date) -> list` — apply policy, sort by score desc with light region diversity (optional: after sorting, ensure first N includes at least one of us/apac/china if present)
- Attach `region` and `impact_score` onto each kept item (copy, do not mutate caller unexpectedly)
- If `len(kept) > 40`, print/log a soft warning (still return all kept items)

**Step 4: Re-run tests — expect PASS**

```bash
python -m pytest tests/test_finance_news_filter.py -v
```

---

### Task 2: Create `run-finance-news.py` from world-news orchestrator

**Files:**
- Create: `scripts/pipeline/run-finance-news.py` (copy + adapt from `scripts/pipeline/run-world-news.py`)
- Leave unused: `scripts/pipeline/run-world-news.py` (stop all callers in later tasks; **do not delete**; **no shim**)

**Step 1: Copy orchestrator**

Copy `run-world-news.py` → `run-finance-news.py`.

**Step 2: Change constants**

```python
FETCH_SCRIPTS = [
    "fetchers/news/fetch-reuters.py",          # retargeted markets (Task 3)
    "fetchers/news/fetch-cnbc-markets.py",     # new (Task 3)
    "fetchers/news/fetch-yahoo-finance.py",    # new (Task 3) — implement at least one US markets RSS
    "fetchers/news/fetch-china-news.py",       # tightened (Task 4)
]

SOURCE_META = {
    "reuters": {"display": "Reuters Markets", "priority": 1},
    "cnbc-markets": {"display": "CNBC Markets", "priority": 2},
    "yahoo-finance": {"display": "Yahoo Finance", "priority": 3},
    "china-news": {"display": "中国财经 (财联社/新浪/人民日报/…)", "priority": 0},
}

CATEGORY_ORDER = ["macro", "policy", "markets", "corporate", "geopolitics-market"]
CATEGORY_LABELS = {
    "macro": "Macro & Central Banks",
    "policy": "Policy & Regulation",
    "markets": "Markets & Trading",
    "corporate": "Corporate & Earnings",
    "geopolitics-market": "Geopolitics (Market Impact)",
}
```

Map old fetcher categories into new keys in merge (e.g. `economics`→`markets`/`macro`, `politics`→`policy`/`geopolitics-market` via keywords). APAC is best-effort via keywords on international items.

**Step 3: Wire filter into `merge_news` + `--no-fetch`**

After dedupe, before building categories:
1. Flatten items
2. `filter_and_rank_items(...)`
3. Group by new category (fetcher may still emit old cats — normalize)
4. Write `finance-news-data.json` and `finance-news-timing.json`
5. Default temp dir `_finance_news_tmp`
6. CLI help text: "Finance news orchestrator"
7. If zero non-China kept items → add `merged["warnings"] = ["no_international_finance_items"]` (and print warning)

Keep `merge_news()`, `translate_news_to_chinese()`, `--no-translate`.

**Required CLI:** add `--no-fetch` that skips parallel fetcher subprocesses and only runs `merge_news` (+ optional translate unless `--no-translate`) then writes `finance-news-data.json`. This is the preferred recovery path for `finance_news_merge` in daily_fetch.

**Step 4: Smoke-run merge-only with fixture**

Create `tests/fixtures/finance_news_sources/` with 2 tiny JSON files matching fetcher output schema (`items` with title/summary/category). Point merge at that dir in a unit test:

```python
def test_merge_finance_news_applies_filter(tmp_path):
    # write reuters.json + china-news.json fixtures
    # call merge_news(str(tmp_path))
    # assert finance filter dropped entertainment; output structure has categories
```

Add to `tests/test_finance_news_filter.py` or `tests/test_run_finance_news_merge.py`.

**Step 5: Run pytest for filter + merge tests**

```bash
python -m pytest tests/test_finance_news_filter.py tests/test_run_finance_news_merge.py -v
```

---

### Task 3: Retarget / add international market fetchers

**Files:**
- Modify: `scripts/fetchers/news/fetch-reuters.py`
- Create: `scripts/fetchers/news/fetch-cnbc-markets.py`
- Create: `scripts/fetchers/news/fetch-yahoo-finance.py` (RSS; if blocked, script exits 0 with empty items + stderr note — must not hang)

**Step 1: Reuters — markets-first feeds**

Replace/narrow `RSS_FEEDS` / sections to business, markets, finance, world politics only as needed for tariffs/geopolitics. Raise `MAX_ITEMS` modestly (e.g. 8–15 per feed) since audio no longer caps hard. Prefer RSS path; keep Playwright fallback.

Set `SOURCE_NAME = "reuters"` unchanged so `reuters.json` still matches `SOURCE_META`.

**Step 2: CNBC Markets fetcher**

Follow `fetch-reuters.py` structure:
- `SOURCE_NAME = "cnbc-markets"`
- RSS candidates (try in order; skip dead):
  - `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664` (finance) — verify live during impl; if 404, use Yahoo-only and document in timing `sources_unavailable`
- Output `cnbc-markets.json` with `items[]` `{title,url,date,summary,category,points}`
- Use `proxy_strategy.get_proxy_for_httpx`
- Timeout disciplined (<120s total)

**Step 3: Yahoo Finance RSS**

- Feeds like `https://finance.yahoo.com/news/rssindex` or region headlines
- Same item schema; `category` default `markets`
- `SOURCE_NAME = "yahoo-finance"`

**Step 4: Manual smoke (optional if network blocked in CI)**

```bash
python scripts/fetchers/news/fetch-yahoo-finance.py tmp/_finance_fetcher_smoke
```

Expected: JSON file written; empty OK if network blocked — script must exit 0 or non-zero consistently; orchestrator already tolerates failures.

**Do not** add BBC/AP/DW/Guardian to `FETCH_SCRIPTS`. Leave those files on disk unused.

---

### Task 4: Tighten China finance fetcher paths

**Files:**
- Modify: `scripts/fetchers/news/fetch-china-news.py`

**Step 1: Cross-day dedup path**

Change yesterday path from `world-news` → `finance-news`:

```python
prev_path = os.path.join(parent, yesterday, "finance-news", f"{SOURCE_NAME}.json")
# fallback:
alt = os.path.join(parent, yesterday, "world-news", f"{SOURCE_NAME}.json")
```

Default `OUTPUT_DIR` tmp name → `_finance_news_tmp`.

**Step 2: Source weighting**

- Keep: Sina finance channel, CLS, People's Daily (policy)
- Toutiao / Weibo: pre-filter with finance keywords before append; drop pure entertainment hot searches
- Prefer finance LID volumes; politics channel keep but tag category `policy`

**Step 3: Same-day preference**

Prefer items where `_is_today(date)`; undated keep with lower priority field if present.

**Step 4: Quick unit test for keyword gate on Weibo-like titles** (pure function extract if needed)

```python
def test_china_hot_search_gate():
    from fetchers... or local helper
    assert keep_china_item("央行降准")
    assert not keep_china_item("某明星恋情曝光")
```

---

### Task 5: Wire Daily Fetch worker to finance pipeline + single audio

**Files:**
- Modify: `scripts/rag/routes/daily_fetch.py` (primary)
- Modify: `scripts/pipeline/run-all-sources.py` (~226–230)
- Modify: `scripts/rag/agent.py` if it still embeds world-news paths / global settings defaults (`audio_lang_world` → add `audio_lang_finance`)

**Step 1: Global settings**

In `_GLOBAL_SETTINGS` (agent.py / settings route):
- Add `"audio_lang_finance": "zh"`
- Keep old keys briefly for migration read; when loading settings, if `audio_lang_finance` missing, set from `audio_lang_world` or `"zh"`

Update `_AUDIO_LANG_KEYS` map:

```python
"finance_audio": "audio_lang_finance",
# remove world_audio / china_audio entries
```

**Step 2: `run-all-sources.py`**

Replace world-news block with:

```python
finance_script = os.path.join(SCRIPT_DIR, "run-finance-news.py")
finance_dir = os.path.join(output_dir, "finance-news")
# subprocess same flags as before (--no-translate if translation is in-process in daily_fetch)
```

Match existing behavior: if world news ran with translate inside orchestrator vs deferred — **preserve current daily_fetch split** (refetch with `--no-translate`, then in-process translate). Point all paths to `finance-news/finance-news-data.json`.

**Step 3: Rename steps in `_run_daily_fetch`**

| Old | New |
|-----|-----|
| `refetch_world` | `refetch_finance` |
| `world_news_translate` | `finance_news_translate` |
| `world_news_merge` | `finance_news_merge` |
| `world_audio` / `china_audio` | `finance_audio` |

Implementation of `finance_audio`:
- Load `finance-news/finance-news-data.json`
- Build segments from **all** categories/items (remove `max_per_cat` cap; if a category is huge, split into multiple segments by ~8–12 items to protect LLM context)
- `_generate_segmented_narrations(..., "finance" or reuse "world" prompt key — prefer new prompt flavor `"finance"` if `_generate_segmented_narrations` switches on type; otherwise reuse `"world"` with updated system blurb in that function)
- Write `finance-news.mp3`
- `_already_done`: check `finance-news.mp3`

**Step 4: History / missing_steps / stats**

- `has_finance_audio` instead of wn/cn
- `missing_steps` emit `finance_*` only
- Stats: `finance_news_items` (+ optional region counts from item `region` field)
- Do not treat old `world-news.mp3`/`china-news.mp3` as complete finance audio

**Step 5: Summary bullets**

Where daily summary reads world-news JSON, read finance-news JSON (fallback legacy path).

**Step 6: Syntax check**

```bash
python -m py_compile scripts/rag/routes/daily_fetch.py scripts/pipeline/run-finance-news.py scripts/pipeline/run-all-sources.py
```

---

### Task 6: UI + Global Settings controls

**Files:**
- Modify: `scripts/rag/templates/index.html` (Daily Fetch history block ~2030–2145, settings ~257, save/load ~3572/3588, `recreateAudio` ~2283–2290)

**Step 1: Settings dropdown**

Remove `settAudioWorld` and `settAudioChina` entirely (HTML + JS load/save). Add one:

```html
<label>Finance News Audio</label>
<select id="settAudioFinance">...</select>
```

Load/save `audio_lang_finance` only.

**Step 2: History audio section**

- Keep AI Briefing block
- Single Finance News block: translate btn (`finance_audio`, `audio_lang_finance`), Recreate, Refetch & Recreate
- Player src: `/api/toolbar/audio-file/<date>/finance-news.mp3`
- Remove World/China blocks
- Update `stepLabels` map for new step names
- Stats display: finance item count

**Step 3: `recreateAudio` preSteps**

```javascript
} else if (stepName === 'finance_audio') {
  preSteps = ['refetch_finance', 'finance_news_merge', 'finance_news_translate', stepName];
}
```

Align with whatever translate step name Task 5 uses (include translate if refetch uses `--no-translate`).

**Step 4: Completion hardcoded audio trio** (~2139)

Replace three `<audio>` tags with AI + Finance only (or rely on `loadDailyFetchHistory` — prefer history renderer only).

---

### Task 7: Downstream path updates + fallback

**Files:**
- Create: `scripts/pipeline/finance_news_paths.py` (or colocate with filter)
- Create: `tests/test_finance_news_paths.py`
- Modify: `scripts/stock/black_swan_detector.py` (`_load_world_news`)
- Modify: `scripts/rag/agent.py` and/or `scripts/rag/learning/helpers.py` (`_load_recent_world_news_titles`, article fetch paths)
- Modify: `scripts/bot_telegram.py` — replace `world_audio`/`china_audio` with `finance_audio` in help text, `/fetch_step` usage, and post-done audio handling
- Modify: `docs/guides/telegram-bot-guide.md` step list

**Step 1: Helper**

```python
def finance_news_data_path(reports_root, date_str) -> str | None:
    candidates = [
        os.path.join(reports_root, date_str, "finance-news", "finance-news-data.json"),
        os.path.join(reports_root, date_str, "world-news", "world-news-data.json"),  # legacy
        os.path.join(reports_root, date_str, "world-news-data.json"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None
```

**Step 2: Point black_swan + casual english loaders at helper** (path swap only; keep CJK skip for casual english)

**Step 3: Telegram bot step rename**

In `scripts/bot_telegram.py`, all user-facing and continue step lists that mention `world_audio` / `china_audio` must use `finance_audio` only.

**Step 4: Unit test path resolution order**

```python
def test_prefers_finance_over_legacy(tmp_path):
    # create both files; assert helper returns finance path
```

---

### Task 8: Narration prompt + docs touch-up

**Files:**
- Modify: narration prompt selection in `scripts/rag/routes/ai_news.py` (or wherever `_generate_segmented_narrations` lives)
- Update: `docs/implementation/briefing-pipeline/world-news-impl.md` → add banner pointing to new doc **or** create `docs/implementation/briefing-pipeline/finance-news-impl.md` and update `docs/implementation/personal/daily-fetch-impl.md` audio section
- Update: `docs/implementation/personal/global-settings-impl.md` lang keys

**Step 1: Finance narration system blurb**

Emphasize: market impact, regions US/APAC/China, concise Chinese broadcast style, mention tickers/policy names clearly for TTS.

**Step 2: Impl doc**

Short finance-news-impl covering sources, filter, output files, single MP3, settings key — enough for next session.

---

### Task 9: Verification

**Step 1: Unit tests**

```bash
python -m pytest tests/test_finance_news_filter.py tests/test_run_finance_news_merge.py tests/test_finance_news_paths.py -v
```

Expected: all PASS.

**Step 2: Orchestrator dry run (network optional)**

```bash
python scripts/pipeline/run-finance-news.py --output-dir tmp/_finance_news_dry --no-translate
```

Expected: directory `tmp/_finance_news_dry` with per-source JSON (some may fail) + `finance-news-data.json` (possibly empty if all fail — still valid structure).

**Step 3: Static references sweep**

```bash
rg -n "world_audio|china_audio|audio_lang_world|audio_lang_china|run-world-news|world-news\\.mp3|china-news\\.mp3" scripts/rag scripts/pipeline scripts/stock scripts/bot_telegram.py --glob "!**/__pycache__/**"
```

Expected: no remaining **live** references in daily_fetch/UI/settings/bot (legacy fallback strings in path helper OK; unused `run-world-news.py` file OK).

**Step 4: Manual UI checklist (user or agent with running Jarvis)**

- [ ] Settings shows Finance audio lang only
- [ ] History shows AI + Finance players
- [ ] Recreate finance uses existing JSON
- [ ] Refetch & Recreate runs finance fetch chain
- [ ] Continue/missing_steps lists `finance_audio` when MP3 absent

---

## Verification Summary

- [ ] Market filter unit tests pass; entertainment dropped; tariffs/Fed/circuit breaker kept
- [ ] `run-finance-news.py` writes `finance-news-data.json` under `finance-news/`
- [ ] Daily Fetch generates `finance-news.mp3` only (not world/china)
- [ ] UI + settings use `finance_audio` / `audio_lang_finance`
- [ ] black_swan + casual english resolve finance path first, legacy second
- [ ] `rg` sweep clean for active world/china audio wiring

---

## Notes for executor

- Prefer TDD on filter/paths; fetchers are integration-fragile — fail soft
- Do not commit unless user asks
- Temp/smoke outputs under `tmp/` only (workspace temp-files rule)
- After implementation, offer `requesting-code-review` per session rules
- Honor **Plan amendments** section above (import path, `--no-fetch`, bot, filter default-deny, leave old orchestrator file)
