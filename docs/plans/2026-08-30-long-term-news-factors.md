# Long-Term Recs: Finance News + Factor Blocks Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Make「AI 股票推荐(长期)」consume all six Daily Fetch finance-news categories (while keeping world news and AI briefing) and add mandatory thermometer blocks for official macro, oil, USD, US 10Y, and BTC.

**Architecture:** Stay inside `long_term_scanner.py`. Read canonical `finance-news/finance-news-data.json` per day (never `finance_news_data_path`, which collapses finance vs world news). Reuse gold's series stats via `_analyze_series`. Fetch oil/DXY/10Y/BTC from Yahoo chart JSON (same proxy as VIX). Build a macro dashboard from akshare `macro_usa_*` (mocked in tests) plus 14-day official headlines. One extra LLM call returns five outlook objects; gold LLM stays independent. Report/UI render five cards above themes. Soft-fail per source.

**Tech Stack:** Python 3, pandas, pytest, existing `call_deepseek` / Ollama `_call_llm_json`, Yahoo chart HTTP (STOCK_PROXY), akshare, Flask UI in `scripts/rag/templates/index.html`.

---

## Confirmed decisions (do not re-litigate)

- News = **add all**: 6 finance categories **and** world news **and** AI briefing.
- Factors = official macro as structured prints **and** oil / DXY / US 10Y / BTC quantitative series.
- Report = **separate cards** (macro, oil, dollar, rates, crypto), same visual language as gold/silver; then theme LLM.
- **One** combined thermometer LLM (not five). Gold/silver LLM unchanged.
- A-share picks only. Oil/USD/rates/crypto are thermometers + `a_share_implication`, not BTC/US-stock recommendations.
- Keep SGE gold/silver price block. Kitco gold news is news only — **no second gold-price series**.
- Do not change Daily Fetch catalog/fetchers. Do not change unified/short-term scanners.
- Horizon still ~3 months–1 year, max 5 picks, 宁缺毋滥. News window 14 days. Structured series = latest + ~12 months.
- Missing JSON/Yahoo/akshare: warn, empty that block, continue.
- Approach A: extend `long_term_scanner.py` in place (rejected: five extra LLM calls; rejected: extract `long_term_factors.py`).

---

## Review patches (2026-08-30)

Critical review (agent structured reasoning; think-mcp unavailable). These bullets override the task samples where they disagree.

1. **Must-fix: Task 1 test dates vs `datetime.now()`.**  
   `_collect_signals` walks `today - timedelta(days=i)`. A fixture folder named `2026-08-29` with `SIGNAL_WINDOW_DAYS=1` only reads **today**, so the test is red even after a correct implementation.  
   Tests must write into `datetime.now().strftime("%Y-%m-%d")` (and still monkeypatch `SIGNAL_WINDOW_DAYS` to 1). Do not hardcode a calendar day.

2. **Must-fix: Task 5 `tmp_path.glob("*.json")`.**  
   `_save_results` writes `{date}.json` **and** `history.json`. `next(tmp_path.glob("*.json"))` may open history. Assert on `{datetime.now():%Y-%m-%d}.json` explicitly.

3. **Must-fix: Task 1 live-signal helper is not optional.**  
   If `_collect_live_market_signals` is not extracted and called, the pytest monkeypatch does nothing and tests hit black-swan / hot-sectors / VIX. Implement the helper in Task 1 Step 3 before considering ingest done.

4. **Should-fix: UI test must slice `pollLtStatus`, not the first `const phases`.**  
   There is currently one `const phases` in `index.html`, but that is accidental. Take the substring from `function pollLtStatus` to `function renderLtResult`. Assert `data.factors` (or `factors.oil`) inside `renderLtResult`, not the bare word `factors`.

5. **Should-fix: `_analyze_series` must accept `None` / missing columns.**  
   `_analyze_metal` will call `_analyze_series(label, fetch_fn())`; SGE fetch already returns `None`. Return the empty `data_available=False` dict, do not throw.

6. **Should-fix: `_theme_system_prompt()` must still inject `recommended_stocks` when `_use_deepseek`.**  
   Do not drop the existing DeepSeek-only field while extracting the prompt for the string test.

7. **Suggestion: LLM strings in new UI cards should use `escHtml`.**  
   Theme stocks already escape; the gold outlook block does not. New factor cards should follow the theme-stock pattern (`escHtml` on drivers/advice/implication).

8. **Suggestion: Yahoo DXY fallback.**  
   If `DX-Y.NYB` 404s, retry `DXY`. Soft-fail remains the last resort.

Implement Tasks 1–7 **with patches 1–6 applied**; 7–8 are recommended in the same change set.

---

## Constants to add in `long_term_scanner.py`

```python
FINANCE_CATEGORIES = (
    "markets", "china-policy", "us-political", "crypto", "gold", "oil",
)
FINANCE_CAT_LABELS = {
    "markets": "综合市场",
    "china-policy": "中国政策金融",
    "us-political": "美国政治金融",
    "crypto": "数字货币",
    "gold": "黄金",
    "oil": "石油",
}
OFFICIAL_SOURCE_IDS = frozenset({
    "pboc", "csrc", "bls", "bea", "census", "ism", "adp", "fed",
})
HEADLINES_PER_FINANCE_CAT = 20  # recency-first (was 12, official-first)
YAHOO_SERIES = {
    "oil": {"symbol": "CL=F", "label": "WTI原油"},
    "dollar": {"symbol": "DX-Y.NYB", "label": "美元指数"},
    "rates": {"symbol": "^TNX", "label": "美债10Y"},
    "crypto": {"symbol": "BTC-USD", "label": "比特币"},
}
```

Yahoo range: `1y`. Parser must produce a DataFrame with columns `date`, `price` (drop NaN, sort).

Macro akshare names to try (getattr, skip missing):

```python
USA_MACRO_SERIES = (
    ("nfp", "非农就业", ("macro_usa_non_farm", "macro_usa_non_farm_payroll")),
    ("unemployment", "失业率", ("macro_usa_unemployment_rate",)),
    ("ism_pmi", "ISM制造业PMI", ("macro_usa_ism_pmi", "macro_usa_pmi")),
    ("adp", "ADP就业", ("macro_usa_adp_employment", "macro_usa_adp")),
)
```

Keep last 12 non-null prints per series: `{name, label, latest, prior, date, history: [{date, value}, ...], data_available}`.

---

### Task 1: Finance news ingest (no path fallback)

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` (`_extract_news_items`, `_collect_signals`)
- Test: `tests/test_long_term_news_factors.py`

**Step 1: Write the failing test**

```python
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import long_term_scanner as lt


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _finance_payload():
    return {
        "categories": [
            {
                "category": "china-policy",
                "label": "中国政策金融",
                "items": [
                    {
                        "title": "PBOC holds rates",
                        "title_zh": "央行维持利率不变",
                        "summary": "policy",
                        "summary_zh": "政策纪要",
                        "source_id": "pboc",
                    },
                    {
                        "title": "Yicai market color",
                        "title_zh": "第一财经市场观察",
                        "summary": "color",
                        "source_id": "yicai",
                    },
                ],
            },
            {
                "category": "oil",
                "label": "石油",
                "items": [
                    {
                        "title": "Brent climbs",
                        "title_zh": "布伦特上涨",
                        "summary": "supply",
                        "source_id": "oilprice",
                    }
                ],
            },
        ]
    }


def test_collect_reads_finance_and_world_news_separately(tmp_path, monkeypatch):
    day = "2026-08-29"
    root = tmp_path
    _write_json(
        root / day / "world-news" / "world-news-data.json",
        {"categories": [{"category": "world", "items": [{"headline": "UN vote"}]}]},
    )
    _write_json(
        root / day / "briefing-data.json",
        {"categories": [{"category": "ai", "items": [{"title": "New LLM"}]}]},
    )
    _write_json(
        root / day / "finance-news" / "finance-news-data.json",
        _finance_payload(),
    )
    monkeypatch.setattr(lt, "_REPORTS_AI_ROOT", str(root))
    monkeypatch.setattr(lt, "SIGNAL_WINDOW_DAYS", 1)
    monkeypatch.setattr(lt, "_collect_live_market_signals", lambda signals: None)

    signals = lt._collect_signals()
    assert any(i["headline"] == "UN vote" for i in signals["world_news"])
    assert any("LLM" in i["headline"] for i in signals["ai_tech_news"])
    headlines = [i["headline"] for i in signals["finance_news"]]
    assert "央行维持利率不变" in headlines
    assert "布伦特上涨" in headlines
    assert signals["finance_by_category"]["china-policy"]
    assert signals["finance_by_category"]["oil"]


def test_finance_prefers_zh_and_keeps_source_id():
    items = lt._extract_finance_news_items(_finance_payload(), "2026-08-29")
    pboc = next(i for i in items if i["source_id"] == "pboc")
    assert pboc["headline"] == "央行维持利率不变"
    assert pboc["category"] == "china-policy"
    assert pboc["source_type"] == "finance"


def test_does_not_use_world_news_as_finance_fallback(tmp_path, monkeypatch):
    day = "2026-08-29"
    _write_json(
        tmp_path / day / "world-news" / "world-news-data.json",
        {"categories": [{"category": "world", "items": [{"headline": "Only world"}]}]},
    )
    monkeypatch.setattr(lt, "_REPORTS_AI_ROOT", str(tmp_path))
    monkeypatch.setattr(lt, "SIGNAL_WINDOW_DAYS", 1)
    monkeypatch.setattr(lt, "_collect_live_market_signals", lambda signals: None)
    signals = lt._collect_signals()
    assert signals["finance_news"] == []
    assert any(i["headline"] == "Only world" for i in signals["world_news"])
```

If `_collect_live_market_signals` does not exist yet, the test may fail on import of the monkeypatch target — that is expected until Step 3. Alternatively monkeypatch `black_swan_detector` / `hot_sectors` / `market_sentiment` imports by stubbing those three try-blocks via a helper you add in Step 3.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_collect_reads_finance_and_world_news_separately tests/test_long_term_news_factors.py::test_finance_prefers_zh_and_keeps_source_id tests/test_long_term_news_factors.py::test_does_not_use_world_news_as_finance_fallback -v`

Expected: FAIL (`_extract_finance_news_items` / `finance_news` missing).

**Step 3: Write minimal implementation**

1. Add `_extract_finance_news_items(data, date_str)`:
   - Walk `data["categories"]`.
   - Headline = `title_zh` or `title` or `headline` (truncate 200).
   - Summary = `summary_zh` or `summary` (truncate 500).
   - Keep `source_id`, `category`, `source_type="finance"`.
2. In `_collect_signals`, initialize `finance_news=[]` and `finance_by_category={cid: [] for cid in FINANCE_CATEGORIES}`.
3. Each day, if `{root}/{date}/finance-news/finance-news-data.json` exists, parse and extend. **Do not** import or call `finance_news_paths.finance_news_data_path`.
4. Extract the black-swan / hot-sectors / sentiment try-blocks into `_collect_live_market_signals(signals)` so tests can no-op them. Call it at the end of `_collect_signals`.

Prefer official `source_id` when later capping (Task 4), but collect everything here.

**Step 4: Run test to verify it passes**

Run: same pytest command as Step 2.

Expected: PASS.

---

### Task 2: Series analyzer + Yahoo parser (no live network)

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` (refactor `_analyze_metal` internals into `_analyze_series`; add Yahoo helpers)
- Test: `tests/test_long_term_news_factors.py`

**Step 1: Write the failing test**

```python
def _prices(n=80, start=100.0, step=0.4):
    vals = [start + i * step for i in range(n)]
    dates = pd.bdate_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"date": dates, "price": vals})


def test_analyze_series_rising_not_overheated():
    out = lt._analyze_series("WTI原油", _prices())
    assert out["data_available"] is True
    assert out["latest_price"] is not None
    assert out["change_14d_pct"] > 0
    assert out["trend"] in ("上涨", "震荡", "过热")
    assert 0 <= out["upside_score"] <= 100


def test_analyze_series_insufficient():
    df = pd.DataFrame({"date": pd.bdate_range("2024-01-02", periods=10, freq="B"), "price": list(range(10))})
    out = lt._analyze_series("WTI原油", df)
    assert out["data_available"] is False


def test_parse_yahoo_chart_json():
    payload = {
        "chart": {
            "result": [{
                "timestamp": [1704067200 + i * 86400 for i in range(5)],
                "indicators": {"quote": [{"close": [70.0, 71.0, None, 72.5, 73.0]}]},
            }]
        }
    }
    df = lt._yahoo_chart_to_df(payload)
    assert list(df["price"]) == [70.0, 71.0, 72.5, 73.0]
    assert len(df) == 4


def test_fetch_yahoo_daily_uses_proxy_and_symbol(monkeypatch):
    calls = {}

    class _Resp:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "chart": {
                    "result": [{
                        "timestamp": [1704067200 + i * 86400 for i in range(40)],
                        "indicators": {"quote": [{"close": [50.0 + i for i in range(40)]}]},
                    }]
                }
            }

    def fake_get(url, headers=None, timeout=None, proxies=None):
        calls["url"] = url
        calls["proxies"] = proxies
        return _Resp()

    monkeypatch.setattr(lt.requests, "get", fake_get)
    monkeypatch.setattr(lt, "_yahoo_proxies", lambda: {"http": "http://127.0.0.1:9", "https": "http://127.0.0.1:9"})
    df = lt._fetch_yahoo_daily("CL=F")
    assert "CL=F" in calls["url"] or "CL%3DF" in calls["url"]
    assert calls["proxies"]["https"]
    assert len(df) >= 30
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_analyze_series_rising_not_overheated tests/test_long_term_news_factors.py::test_analyze_series_insufficient tests/test_long_term_news_factors.py::test_parse_yahoo_chart_json tests/test_long_term_news_factors.py::test_fetch_yahoo_daily_uses_proxy_and_symbol -v`

Expected: FAIL (functions missing).

**Step 3: Write minimal implementation**

- `_analyze_series(label, df)`: copy the scoring body of `_analyze_metal` but take a DataFrame instead of `fetch_fn`. Require `len(df) >= 30`.
- `_analyze_metal` becomes `return _analyze_series(label, fetch_fn())` with the same empty-result if fetch is None.
- `_yahoo_chart_to_df(payload)`: zip timestamp × close, drop None, `date` as UTC datetime.
- `_yahoo_proxies()`: same env `STOCK_PROXY` pattern as `market_sentiment.py` (`{"http": proxy, "https": proxy}` or `{}`).
- `_fetch_yahoo_daily(symbol)`: try `query1` then `query2` chart URLs, `interval=1d&range=1y`, User-Agent header, timeout 15. On failure return None.
- `_analyze_market_factors()` → `{oil, dollar, rates, crypto}` each from `_analyze_series(label, df)` when df is usable.

Encode Yahoo symbols with `requests.utils.quote(symbol, safe="")` so `^TNX` and `DX-Y.NYB` are valid path segments.

**Step 4: Run test to verify it passes**

Run: same command as Step 2.

Expected: PASS.

---

### Task 3: Macro dashboard

**Files:**
- Modify: `scripts/stock/long_term_scanner.py`
- Test: `tests/test_long_term_news_factors.py`

**Step 1: Write the failing test**

```python
def test_macro_dashboard_from_history_and_headlines():
    history = {
        "nfp": [
            {"date": "2026-06-01", "value": 200.0},
            {"date": "2026-07-01", "value": 180.0},
            {"date": "2026-08-01", "value": 150.0},
        ]
    }
    headlines = [
        {"category": "us-political", "source_id": "fed", "headline": "Fed holds", "date": "2026-08-28"},
        {"category": "china-policy", "source_id": "pboc", "headline": "央行维持利率不变", "date": "2026-08-29"},
        {"category": "oil", "source_id": "oilprice", "headline": "ignore me", "date": "2026-08-29"},
    ]
    dash = lt._build_macro_dashboard(history, headlines)
    nfp = next(s for s in dash["series"] if s["id"] == "nfp")
    assert nfp["latest"] == 150.0
    assert nfp["prior"] == 180.0
    assert nfp["data_available"] is True
    texts = [h["headline"] for h in dash["official_headlines"]]
    assert "Fed holds" in texts
    assert "央行维持利率不变" in texts
    assert "ignore me" not in texts


def test_macro_empty_series_still_ok():
    dash = lt._build_macro_dashboard({}, [])
    assert dash["series"]
    assert all(s["data_available"] is False for s in dash["series"])
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_macro_dashboard_from_history_and_headlines tests/test_long_term_news_factors.py::test_macro_empty_series_still_ok -v`

Expected: FAIL.

**Step 3: Write minimal implementation**

`_build_macro_dashboard(history_by_id, headlines)`:
- For each `USA_MACRO_SERIES` id, take last 12 history points, set latest/prior.
- `official_headlines`: items whose `source_id` is in `OFFICIAL_SOURCE_IDS`, cap 20, newest first.
- `_fetch_usa_macro_history()`: for each id, try akshare function names in order; normalize date/value columns defensively (`日期`/`date`/`时间`, first numeric column or `今值`/`value`). Wrap in try/except, skip failures.
- `_analyze_all_factors(signals)` returns:

```python
{
  "macro": dashboard,
  "oil": series_or_empty,
  "dollar": ...,
  "rates": ...,
  "crypto": ...,
}
```

Do not call live akshare/Yahoo from unit tests; Task 3 tests only `_build_macro_dashboard`.

**Step 4: Run test to verify it passes**

Run: same as Step 2.

Expected: PASS.

---

### Task 4: Signal summary, theme prompt, thermometer LLM parse

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` (`_build_signal_summary`, `_llm_theme_analysis`, new `_llm_thermometer_outlook`, `_parse_thermometer_outlook`)
- Test: `tests/test_long_term_news_factors.py`

**Step 1: Write the failing test**

```python
def test_signal_summary_caps_finance_and_prefers_official():
    signals = {
        "world_news": [{"date": "d", "headline": "W"}] * 3,
        "ai_tech_news": [],
        "black_swan": None,
        "hot_sectors": [],
        "market_sentiment": None,
        "finance_news": [
            {"date": "d", "category": "us-political", "source_id": "yicai", "headline": f"media-{i}"}
            for i in range(20)
        ] + [
            {"date": "d", "category": "us-political", "source_id": "fed", "headline": "Fed official"},
            {"date": "d", "category": "oil", "source_id": "oilprice", "headline": "Oil story"},
        ],
        "finance_by_category": {},
    }
    text = lt._build_signal_summary(signals, {}, factors=None)
    assert "【财经新闻-美国政治金融" in text
    assert "Fed official" in text
    assert "Oil story" in text
    us_block = text.split("【财经新闻-美国政治金融")[1].split("【")[0]
    assert us_block.count("media-") <= 11  # 12 cap including the official line


def test_theme_prompt_requires_new_factors():
    prompt = lt._theme_system_prompt()
    for needle in ("中国政策", "石油", "美元", "利率", "加密", "官方宏观"):
        assert needle in prompt
    assert "禁止只凭科技简报" in prompt or "不要只根据AI" in prompt


def test_parse_thermometer_outlook_ok():
    raw = {
        "macro": {"trend": "中性", "drivers": "NFP放缓", "overheated": False, "advice": "观察", "a_share_implication": "内需"},
        "oil": {"trend": "看涨", "drivers": "供给", "overheated": False, "advice": "跟踪", "a_share_implication": "油服"},
        "dollar": {"trend": "看跌", "drivers": "降息", "overheated": False, "advice": "观察", "a_share_implication": "出口"},
        "rates": {"trend": "震荡", "drivers": "10Y", "overheated": False, "advice": "观察", "a_share_implication": "成长"},
        "crypto": {"trend": "看涨", "drivers": "风险偏好", "overheated": True, "advice": "谨慎", "a_share_implication": "风险偏好"},
        "summary": "风险偏好回暖",
    }
    out = lt._parse_thermometer_outlook(raw)
    assert out["oil"]["a_share_implication"] == "油服"
    assert "error" not in out


def test_parse_thermometer_outlook_malformed():
    out = lt._parse_thermometer_outlook(["not", "a", "dict"])
    assert out.get("error")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_signal_summary_caps_finance_and_prefers_official tests/test_long_term_news_factors.py::test_theme_prompt_requires_new_factors tests/test_long_term_news_factors.py::test_parse_thermometer_outlook_ok tests/test_long_term_news_factors.py::test_parse_thermometer_outlook_malformed -v`

Expected: FAIL.

**Step 3: Write minimal implementation**

- `_build_signal_summary(signals, metals, factors=None)`:
  - Keep world 60 / AI 40.
  - For each finance category, select up to 12: official `source_id` first, then the rest.
  - Headings: `【财经新闻-{label} (n条)】`.
  - If `factors` present, append compact lines for macro latest prints + oil/dollar/rates/crypto 14d/60d/RSI/trend (skip `data_available` false).
- Extract theme `system_prompt` into `_theme_system_prompt()` so the test can assert strings. Add: must use 中国政策、美国宏观/政治、石油、美元、利率、加密、黄金新闻 and thermometer conclusions; do not theme from AI briefing alone; `a_share_implication` is mapping, not a US/BTC pick list.
- `_parse_thermometer_outlook(raw)`: require dict with keys `macro,oil,dollar,rates,crypto`; each subdict may be partial; else `{"error": "..."}`.
- `_llm_thermometer_outlook(factors, signal_summary)`: one `_call_llm_json` asking for that schema; attach as `factors["llm_outlook"]`. Cap news context like metals (`signal_summary[:4000]`).

**Step 4: Run test to verify it passes**

Run: same as Step 2.

Expected: PASS.

---

### Task 5: Report, JSON save, orchestration

**Files:**
- Modify: `scripts/stock/long_term_scanner.py` (`_generate_report`, `_save_results`, `_save_lt_history`, `_run_lt_scan_inner`)
- Test: `tests/test_long_term_news_factors.py`

**Step 1: Write the failing test**

```python
def _empty_series(label="x"):
    return {"name": label, "data_available": False}


def _sample_factors():
    oil = lt._analyze_series("WTI原油", _prices())
    return {
        "macro": {
            "series": [{"id": "nfp", "label": "非农就业", "latest": 150, "prior": 180, "date": "2026-08-01", "data_available": True, "history": []}],
            "official_headlines": [{"headline": "Fed holds", "source_id": "fed"}],
        },
        "oil": oil,
        "dollar": _empty_series("美元指数"),
        "rates": _empty_series("美债10Y"),
        "crypto": _empty_series("比特币"),
        "llm_outlook": {
            "oil": {"trend": "看涨", "drivers": "供给", "advice": "跟踪油服", "a_share_implication": "油服"},
            "summary": "油强美元弱",
        },
    }


def test_report_has_thermometer_sections_when_data_present():
    md = lt._generate_report([], {}, [], {"world_news_count": 1, "ai_news_count": 0, "finance_news_count": 3}, factors=_sample_factors())
    assert "## 二、宏观与市场温度计" in md
    assert "### 油价" in md
    assert "### 官方宏观" in md
    assert "非农就业" in md
    assert "油服" in md
    assert "## 三、投资主题" in md
    assert "## 四、长期推荐" in md
    assert "财经新闻" in md or "finance_news_count" in md or "3 条" in md


def test_report_omits_empty_series_subsections():
    factors = {
        "macro": {"series": [], "official_headlines": []},
        "oil": _empty_series("WTI原油"),
        "dollar": _empty_series("美元指数"),
        "rates": _empty_series("美债10Y"),
        "crypto": _empty_series("比特币"),
    }
    md = lt._generate_report([], {}, [], {}, factors=factors)
    assert "### 油价" not in md
    assert "## 二、宏观与市场温度计" in md  # heading may still exist with 暂无
```

Clarify in implementation: if **all** five are empty, still emit `## 二、宏观与市场温度计` with `暂无数据（源缺失，已跳过）` so the reader sees the scan tried. Omit `### 油价` when that series is unavailable.

Also add:

```python
def test_save_results_includes_factors(tmp_path, monkeypatch):
    monkeypatch.setattr(lt, "LONG_TERM_DIR", str(tmp_path))
    monkeypatch.setattr(lt, "_index_report_to_rag", lambda *a, **k: None)
    lt._save_results([], {}, [], {"finance_news_count": 2}, factors=_sample_factors())
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert "factors" in data
    assert data["factors"]["oil"]["data_available"] is True
    hist = json.loads((tmp_path / "history.json").read_text(encoding="utf-8"))
    assert hist[-1].get("oil_trend")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_report_has_thermometer_sections_when_data_present tests/test_long_term_news_factors.py::test_report_omits_empty_series_subsections tests/test_long_term_news_factors.py::test_save_results_includes_factors -v`

Expected: FAIL (`factors` kwarg missing).

**Step 3: Write minimal implementation**

- `_generate_report(..., factors=None)`: meta line for finance count; after 贵金属, add 温度计 section (macro table + series subsections + outlook lines); renumber 主题→三, 推荐→四.
- `_save_results(..., factors=None)`: persist `factors` on the JSON; pass into report.
- `_save_lt_history(..., factors=None)`: add `oil_trend`, `dollar_trend`, `rates_trend`, `crypto_trend` when available.
- `_run_lt_scan_inner`:
  1. collect signals
  2. metals + metals LLM (existing)
  3. `progress["status"] = "analyzing_factors"` then `_analyze_all_factors(signals)` then thermometer LLM
  4. rebuild `signal_summary` **including factors** before theme LLM
  5. rest unchanged
  6. `scan_meta["finance_news_count"]` and per-category counts
- Wrap factor fetch/LLM in try/except; on failure `factors = {}` and continue.
- `_llm_final_selection`: include a short factor/metals blurb in the user prompt (the `_signal_summary` argument is currently unused — use a 1500-char slice).

**Step 4: Run test to verify it passes**

Run: same as Step 2.

Expected: PASS.

---

### Task 6: Frontend

**Files:**
- Modify: `scripts/rag/templates/index.html` (`pollLtStatus` phases, `renderLtResult`, history chips)
- Test: `tests/test_long_term_news_factors.py` (HTML string asserts, same style as `test_ath_rebreak_ui.py`)

**Step 1: Write the failing test**

```python
HTML = Path(__file__).resolve().parents[1] / "scripts" / "rag" / "templates" / "index.html"


def test_lt_ui_has_factor_cards_and_phase():
    text = HTML.read_text(encoding="utf-8")
    fn = text[text.find("function renderLtResult"): text.find("async function loadLtHistory")]
    for needle in ("官方宏观", "油价", "美元", "美债", "加密", "factors"):
        assert needle in fn
    poll = text[text.find("const phases = {"): text.find("if (d.status === 'done')")]
    assert "analyzing_factors" in poll
    hist = text[text.find("async function loadLtHistory"): text.find("async function loadLtDate")]
    assert "oil_trend" in hist
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_long_term_news_factors.py::test_lt_ui_has_factor_cards_and_phase -v`

Expected: FAIL.

**Step 3: Write minimal implementation**

In `renderLtResult`, after the 贵金属 block and before themes, render five cards from `data.factors`:
- macro: compact table of `series` where `data_available`, plus official headline bullets, plus `llm_outlook.macro`.
- oil/dollar/rates/crypto: clone gold card fields (`latest_price`, 14d/60d, RSI, 52w, trend color, outlook drivers/advice/`a_share_implication`).
Skip a card when that key is missing or `data_available` is false **and** there is no outlook. If macro has only headlines, still show the card.

`pollLtStatus` phases: insert `'analyzing_factors': {pct: '40%', text: '宏观/油/美元/利率/加密分析...'}` and shift themes to ~55% (keep later phases).

History: show small chips for `oil_trend` / `dollar_trend` next to gold/silver.

**Step 4: Run test to verify it passes**

Run: same as Step 2 plus the full file:

`python -m pytest tests/test_long_term_news_factors.py -v`

Expected: all PASS.

---

### Task 7: Strategy docs + plans index

**Files:**
- Modify: `docs/stock-modules/strategy-long-term-deepseek.md`
- Modify: `docs/stock-modules/long_term_scanner.md`
- Modify: `docs/plans/README.md`
- Test: none required beyond docs existing; if a doc-string test is already in the repo, do not add a new one.

**Step 1: Update strategy (小白版)**

In `strategy-long-term-deepseek.md`:
- §1.1: mention 6-category finance news **plus** world news + AI briefing; 14-day window unchanged.
- Funnel step ①: add finance categories.
- After 贵金属: five thermometer blocks (宏观 / 油 / 美元 / 10Y / BTC) with one combined LLM outlook.
- §4.2 inputs: list new sources; gold price remains SGE only.
- Comparison table / 最后更新 date → 2026-08-30.
- LLM count: 4 calls (metals, thermometer, themes, picks).

**Step 2: Update `long_term_scanner.md`**

- Upstream: `YYYY-MM-DD/finance-news/finance-news-data.json` **in addition to** world-news and briefing.
- Data structures: `finance_news`, `factors`.
- Function table: `_extract_finance_news_items`, `_analyze_series`, `_fetch_yahoo_daily`, `_build_macro_dashboard`, `_llm_thermometer_outlook`.
- Explicit: do not use `finance_news_data_path` fallback.

**Step 3: Index the plan**

Add a row to the Active Plans table in `docs/plans/README.md`:

`| [long-term-news-factors](2026-08-30-long-term-news-factors.md) | Active | 长期推荐接入 6 类财经新闻 + 宏观/油/美元/利率/加密温度计 | docs/stock-modules/long_term_scanner.md |`

**Step 4: Re-run the full test file**

Run: `python -m pytest tests/test_long_term_news_factors.py -v`

Expected: PASS.

---

## Verification Summary

- [ ] Finance JSON and world-news both load on the same day; missing finance file does not steal world-news.
- [ ] Headlines prefer `title_zh`; official sources rank first inside the 12/category cap.
- [ ] `_analyze_series` scores a synthetic frame; Yahoo parser drops null closes; fetch is unit-tested with a fake `requests.get`.
- [ ] Macro dashboard computes latest vs prior and filters official headlines.
- [ ] Theme prompt cites the new factor names; thermometer JSON parse has a happy path and an error path.
- [ ] Report headings 一金银 / 二温度计 / 三主题 / 四推荐; empty series subsections omitted.
- [ ] Saved JSON contains `factors`; history has oil/dollar chips.
- [ ] UI `renderLtResult` has five cards; `analyzing_factors` phase exists.
- [ ] Strategy + module docs updated. No Daily Fetch / unified-scanner edits.
- [ ] `python -m pytest tests/test_long_term_news_factors.py -v` green.
- [ ] No live Yahoo/akshare/DeepSeek required for CI.
- [ ] Review patches 1–6 applied in tests and implementation.

---

## Out of scope

- Daily Fetch source catalog, fetchers, audio, RAG ingest of finance news.
- Unified / left / right / quality-value / ATH scanners.
- Recommending BTC or US-listed names.
- Second gold-price block (COMEX/Kitco prices).
- Extracting `long_term_factors.py`.
- Five separate thermometer LLM calls.
