# Quality Undervalued Stock Screener Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Add an independent toolbar scanner that finds high-quality, undervalued A-shares (same-industry cheap PE/PB + dividend + fundamental landmine filter + PB-ROE rank + DeepSeek cycle/trap veto), outputting at most 5 names for a 6-month–2-year hold.

**Architecture:** New `quality_value_scanner.py` cloned from the long-term scanner lifecycle (background thread, progress JSON, start/status/stop/result). Funnel is batch-first: one market snapshot with PE/PB/dividend + **read-only cached** industry map for Layer1 (never rebuild all boards during this scan); Layer1 sorted by relative cheapness and **capped at 100**; fundamentals only for those survivors; 5-year PE percentile only for top ~15–20; **one** DeepSeek call for remaining candidates (JSON array, ≤5). Do not change unified left/right or long-term scanners. Do not reuse the 1–2 week DeepSeek persona.

**Tech Stack:** Python 3, pandas, akshare / Eastmoney clist, local percentile helper (do **not** import `valuation._percentile_rank`), `fundamental_analysis` THS annuals, `eastmoney_throttle`, Flask `stock.py` routes, `index.html` modal, pytest under `tests/`.

---

## Confirmed decisions (do not re-litigate)

- Independent toolbar button (not a third column, not folded into long-term).
- Full four-step funnel + PB-ROE + DeepSeek final review.
- Horizon: **6 months – 2 years**.
- Finance/bank/insurance: skip debt-ratio hard gate; PB&lt;1 is an undervaluation signal; still require ROE and dividend.
- Max **5** picks, industry-diversified; 0 picks is valid.
- Missing 扣非 / 分红 / 5y percentile → `unknown`, do **not** auto-kill.
- Unchecked DeepSeek → rule-layer Top5, report marked 「未经 AI 终审」.
- No Telegram. Do index the markdown report to RAG the same way long-term does.
- Layer1 **hard cap 100** after same-industry filter, sorted by relative cheapness (lower PE/行业均值 × PB/行业均值 first).
- Layer1 **excludes ChiNext (创业板 300/301)** via `board_filters.is_chinext` (user cannot trade it). STAR 科创板 688/689 stays. Drop ChiNext before industry-mean so they do not skew peers.
- Industry map: **cache only**. If `.industry_map.json` / valuation industry cache miss → blank industry → `industry_unknown`. Do **not** call `stock_board_industry_cons_em` for every board inside this scan.
- Layer4 is **one batch LLM call** (like `long_term_scanner._llm_final_selection`), not 8–10 sequential per-stock calls.
- Copy a local `_percentile_rank`; do not import `valuation._percentile_rank`.
- 商誉暴雷: v1 is **DeepSeek qualitative only** (prompt must mention 商誉/减值). No rule-layer goodwill filter. Docs must say so.
- Dividend: Eastmoney `f133` is a guess — also map akshare `股息率`. Finance: missing yield = `unknown` (keep); numeric yield &lt; 2.5% = drop.
- Persist scanner thread/status on `sys` (right-side pattern). Add module to `_STOCK_MODULES`.
- `tests/` may be gitignored; still run pytest locally.

---

## Review patches (2026-08-16)

Plan review found Layer1 unbounded fetches, industry-map cold start, per-stock DeepSeek cost, private-API import, and missing 商誉 handling. The bullets above and the task edits below are authoritative. Do not re-litigate them.

## Task 1: Finance flag + Layer1 same-industry coarse filter

**Files:**
- Create: `scripts/stock/quality_value_scanner.py` (funnel helpers only in this task)
- Test: `tests/test_quality_value_funnel.py`

**Step 1: Write the failing test**

```python
# tests/test_quality_value_funnel.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from quality_value_scanner import (
    is_finance_industry,
    layer1_coarse_filter,
)


def test_finance_industry_keywords():
    assert is_finance_industry("银行")
    assert is_finance_industry("非银金融")
    assert is_finance_industry("保险")
    assert is_finance_industry("证券")
    assert not is_finance_industry("白酒")
    assert not is_finance_industry("互联网")  # do not match bare 金融 via 互联网金融 unless listed


def test_layer1_excludes_st_and_nonpositive_pe():
    rows = [
        {"symbol": "000001", "name": "平安银行", "industry": "银行", "pe": 5.0, "pb": 0.8, "div_yield": 4.0},
        {"symbol": "000002", "name": "ST地产", "industry": "房地产", "pe": 8.0, "pb": 0.5, "div_yield": 5.0},
        {"symbol": "300001", "name": "亏损科技", "industry": "软件", "pe": -10.0, "pb": 8.0, "div_yield": 0.0},
    ]
    kept, stats = layer1_coarse_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "000002" not in symbols
    assert "300001" not in symbols


def test_layer1_pe_pb_vs_industry_mean_not_cross_industry():
    rows = [
        {"symbol": "A1", "name": "银行甲", "industry": "银行", "pe": 5.0, "pb": 0.7, "div_yield": 4.0},
        {"symbol": "A2", "name": "银行乙", "industry": "银行", "pe": 9.0, "pb": 1.2, "div_yield": 3.0},
        {"symbol": "B1", "name": "软件甲", "industry": "软件", "pe": 25.0, "pb": 3.0, "div_yield": 2.6},
        {"symbol": "B2", "name": "软件乙", "industry": "软件", "pe": 40.0, "pb": 6.0, "div_yield": 2.6},
    ]
    kept, _ = layer1_coarse_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "A1" in symbols
    assert "A2" not in symbols  # PE and PB above bank mean
    assert "B1" in symbols
    assert "B2" not in symbols


def test_layer1_missing_dividend_does_not_kill():
    rows = [
        {"symbol": "C1", "name": "制造甲", "industry": "机械", "pe": 10.0, "pb": 1.2, "div_yield": None},
        {"symbol": "C2", "name": "制造乙", "industry": "机械", "pe": 12.0, "pb": 1.5, "div_yield": None},
    ]
    kept, _ = layer1_coarse_filter(rows)
    assert {r["symbol"] for r in kept} == {"C1"}  # cheaper vs peer; no div kill


def test_layer1_unknown_industry_skips_relative_filter():
    rows = [
        {"symbol": "U1", "name": "未知甲", "industry": "", "pe": 8.0, "pb": 1.0, "div_yield": 3.0},
    ]
    kept, _ = layer1_coarse_filter(rows)
    assert kept[0]["symbol"] == "U1"
    assert kept[0].get("industry_unknown") is True


def test_layer1_caps_at_100_keeping_cheapest():
    rows = []
    for i in range(1, 301):
        rows.append({
            "symbol": f"{i:06d}",
            "name": f"机{i}",
            "industry": "机械",
            "pe": float(i),
            "pb": 1.0,
            "div_yield": 3.0,
        })
    kept, stats = layer1_coarse_filter(rows, cap=100)
    assert len(kept) == 100
    assert stats["out"] == 100
    pes = [r["pe"] for r in kept]
    assert max(pes) < min(r["pe"] for r in rows if r["symbol"] not in {x["symbol"] for x in kept} and r["pe"] < 150)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quality_value_funnel.py -v`

Expected: FAIL with `ModuleNotFoundError` or import error for `quality_value_scanner`.

**Step 3: Write minimal implementation**

In `scripts/stock/quality_value_scanner.py`:

```python
"""Quality + undervalued A-share scanner (value funnel + PB-ROE + DeepSeek)."""
from __future__ import annotations

import logging
from collections import defaultdict

log = logging.getLogger("quality_value_scanner")

LAYER1_CAP = 100
_FINANCE_INDUSTRIES = ("银行", "非银金融", "保险", "证券", "多元金融")
_ST_MARKERS = ("ST", "*ST", "退市")


def is_finance_industry(industry: str | None) -> bool:
    text = str(industry or "")
    return any(k in text for k in _FINANCE_INDUSTRIES)


def _is_st(name: str) -> bool:
    n = str(name or "")
    return any(m in n for m in _ST_MARKERS)


def _industry_means(rows: list[dict]) -> dict[str, dict]:
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        ind = str(r.get("industry") or "").strip()
        if not ind:
            continue
        buckets[ind].append(r)
    out = {}
    for ind, items in buckets.items():
        pes = [float(x["pe"]) for x in items if x.get("pe") and float(x["pe"]) > 0]
        pbs = [float(x["pb"]) for x in items if x.get("pb") and float(x["pb"]) > 0]
        if len(pes) >= 2:
            out[ind] = {
                "pe_mean": sum(pes) / len(pes),
                "pb_mean": (sum(pbs) / len(pbs)) if pbs else None,
                "n": len(items),
            }
    return out


def layer1_coarse_filter(rows: list[dict], cap: int | None = None) -> tuple[list[dict], dict]:
    """Same-industry PE/PB cheap screen. Dividend ≥2.5% only when present. Cap after ranking."""
    cleaned = []
    dropped_st = dropped_pe = 0
    for r in rows:
        if _is_st(r.get("name", "")):
            dropped_st += 1
            continue
        pe = r.get("pe")
        try:
            pe_f = float(pe) if pe is not None else None
        except (TypeError, ValueError):
            pe_f = None
        if pe_f is None or pe_f <= 0:
            dropped_pe += 1
            continue
        item = dict(r)
        item["pe"] = pe_f
        try:
            item["pb"] = float(r["pb"]) if r.get("pb") is not None else None
        except (TypeError, ValueError):
            item["pb"] = None
        try:
            item["div_yield"] = float(r["div_yield"]) if r.get("div_yield") is not None else None
        except (TypeError, ValueError):
            item["div_yield"] = None
        cleaned.append(item)

    means = _industry_means(cleaned)
    kept = []
    for r in cleaned:
        ind = str(r.get("industry") or "").strip()
        if not ind or ind not in means:
            r["industry_unknown"] = True
            if r.get("div_yield") is not None and r["div_yield"] < 2.5:
                continue
            kept.append(r)
            continue
        m = means[ind]
        if r["pe"] >= m["pe_mean"]:
            continue
        if r.get("pb") is not None and m.get("pb_mean") and r["pb"] >= m["pb_mean"]:
            continue
        if r.get("div_yield") is not None and r["div_yield"] < 2.5:
            continue
        r["industry_pe_mean"] = round(m["pe_mean"], 2)
        r["industry_pb_mean"] = round(m["pb_mean"], 2) if m.get("pb_mean") else None
        if is_finance_industry(ind) and r.get("pb") is not None and r["pb"] < 1:
            r["finance_pb_undervalue"] = True
        pe_m = m["pe_mean"] or r["pe"]
        pb_m = m.get("pb_mean") or r.get("pb") or 1.0
        r["cheapness"] = (r["pe"] / pe_m) * ((r["pb"] / pb_m) if r.get("pb") else 1.0)
        kept.append(r)
    kept.sort(key=lambda x: x.get("cheapness", 9e9))
    if cap is None:
        cap = LAYER1_CAP
    kept = kept[:cap]
    stats = {"in": len(rows), "out": len(kept), "dropped_st": dropped_st, "dropped_pe": dropped_pe}
    return kept, stats
```

Add `LAYER1_CAP = 100` and `def layer1_coarse_filter(rows, cap=None)`. The cap test’s last assertion is easy to get wrong — simpler equivalent: `assert kept[0]["pe"] == 1.0` and `assert all(r["pe"] <= kept[-1]["pe"] for r in kept)`.

**Implementer note:** if the 300-row mean/filter yields fewer than 100 names, lower every PE into a band that still beats the mean, or split across two industries. The contract is: after the relative filter, never return more than `cap` rows, cheapest first.

**Step 4: Run tests and make sure they pass**

Run: `python -m pytest tests/test_quality_value_funnel.py -v`

Expected: PASS. If `test_layer1_unknown_industry` fails because empty industry also fails the dividend check, keep `div_yield: 3.0` as written. If `互联网` fails because of `多元金融` — it should not.

---

## Task 2: Layer2 fundamental landmine gates

**Files:**
- Modify: `scripts/stock/quality_value_scanner.py`
- Test: `tests/test_quality_value_funnel.py`

**Step 1: Write the failing tests**

```python
from quality_value_scanner import layer2_fundamental_filter


def test_layer2_requires_roe_and_growth():
    rows = [
        {"symbol": "G1", "industry": "白酒", "roe": 12, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
        {"symbol": "G2", "industry": "白酒", "roe": 8, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
        {"symbol": "G3", "industry": "白酒", "roe": 12, "np_cagr_3y": 2, "debt_ratio": 40, "nonrecurring_ratio": 0.9},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    assert {r["symbol"] for r in kept} == {"G1"}


def test_layer2_debt_gate_skips_finance():
    rows = [
        {"symbol": "BK", "industry": "银行", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": 4.0},
        {"symbol": "MF", "industry": "机械", "roe": 11, "np_cagr_3y": 5, "debt_ratio": 92, "div_yield": 4.0},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    symbols = {r["symbol"] for r in kept}
    assert "BK" in symbols
    assert "MF" not in symbols


def test_layer2_unknown_nonrecurring_does_not_kill():
    rows = [
        {"symbol": "U", "industry": "机械", "roe": 12, "np_cagr_3y": 6, "debt_ratio": 40, "nonrecurring_ratio": None},
    ]
    kept, _ = layer2_fundamental_filter(rows)
    assert kept[0]["symbol"] == "U"
    assert kept[0]["nonrecurring_status"] == "unknown"
```

**Step 2: Run to verify fail**

Run: `python -m pytest tests/test_quality_value_funnel.py::test_layer2_requires_roe_and_growth -v`

Expected: FAIL (`layer2_fundamental_filter` not defined).

**Step 3: Implement**

```python
def layer2_fundamental_filter(rows: list[dict]) -> tuple[list[dict], dict]:
    kept = []
    for r in rows:
        roe = r.get("roe")
        growth = r.get("np_cagr_3y")
        if roe is None or float(roe) < 10:
            continue
        if growth is None or float(growth) < 5:
            continue
        finance = is_finance_industry(r.get("industry"))
        debt = r.get("debt_ratio")
        if not finance:
            if debt is None or float(debt) >= 60:
                continue
        else:
            if r.get("div_yield") is not None and float(r["div_yield"]) < 2.5:
                continue
        nr = r.get("nonrecurring_ratio")
        item = dict(r)
        if nr is None:
            item["nonrecurring_status"] = "unknown"
        else:
            if float(nr) < 0.80:
                continue
            item["nonrecurring_status"] = "ok"
        payout = r.get("payout_stable")  # True / False / None
        if payout is False:
            continue
        if payout is None:
            item["payout_status"] = "unknown"
        else:
            item["payout_status"] = "ok"
        kept.append(item)
    return kept, {"in": len(rows), "out": len(kept)}
```

**Step 4:** `python -m pytest tests/test_quality_value_funnel.py -v` → PASS.

---

## Task 3: Layer3 PB-ROE rank, industry cap, 5-year PE percentile window

**Files:**
- Modify: `scripts/stock/quality_value_scanner.py`
- Test: `tests/test_quality_value_funnel.py`

**Step 1: Failing tests**

```python
import pandas as pd
from quality_value_scanner import (
    pb_roe_score,
    layer3_rank_and_cap,
    pe_percentile_in_window,
)


def test_pb_roe_prefers_high_roe_low_pb():
    cheap_quality = {"roe": 20.0, "pb": 1.0}
    expensive_weak = {"roe": 10.0, "pb": 4.0}
    assert pb_roe_score(cheap_quality) > pb_roe_score(expensive_weak)


def test_layer3_caps_two_per_industry_and_keeps_top():
    rows = []
    for i in range(5):
        rows.append({"symbol": f"B{i}", "industry": "白酒", "roe": 20 - i, "pb": 1 + i * 0.2})
    for i in range(3):
        rows.append({"symbol": f"M{i}", "industry": "机械", "roe": 18 - i, "pb": 1.1 + i * 0.2})
    ranked = layer3_rank_and_cap(rows, per_industry=2, top_n=20)
    industries = [r["industry"] for r in ranked]
    assert industries.count("白酒") <= 2
    assert industries.count("机械") <= 2
    assert ranked[0]["symbol"] == "B0"


def test_pe_percentile_uses_five_year_window_not_all_history():
    idx = pd.date_range("2015-01-01", periods=10, freq="YE")
    # old years very high PE, recent 5y clustered around 10
    pe = [40, 40, 40, 40, 40, 10, 10, 10, 10, 11]
    hist = pd.DataFrame({"数据日期": idx, "PE(TTM)": pe})
    as_of = pd.Timestamp("2024-12-31")
    pct = pe_percentile_in_window(11.0, hist, as_of=as_of, years=5)
    assert pct is not None
    assert pct <= 30  # 11 is at the high end of recent 10s but still not 40s
```

Tune the last assertion to whatever `_percentile_rank` semantics produce: existing helper is `% of history strictly below current`. For values `[10,10,10,10,11]` and current 11, percentile ≈ 80. **Change the test** to a cheap case:

```python
    pe = [20, 18, 16, 15, 14, 13, 12, 11, 10, 9]  # yearly
    hist = pd.DataFrame({"数据日期": idx, "PE(TTM)": pe})
    pct = pe_percentile_in_window(10.0, hist, as_of=pd.Timestamp("2024-12-31"), years=5)
    assert pct is not None and pct <= 30
```

Use a 10-year index; last 5 years must include enough points below 10.

**Step 2:** Run → FAIL.

**Step 3: Implement**

```python
import pandas as pd
from datetime import datetime


def _percentile_rank(value: float, series: pd.Series) -> float | None:
    """Local copy — do not import valuation._percentile_rank."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean > 0]
    if not len(clean) or value is None or value <= 0:
        return None
    return float((clean < value).sum() / len(clean) * 100)


def pb_roe_score(row: dict) -> float:
    roe = float(row.get("roe") or 0)
    pb = float(row.get("pb") or 0)
    if pb <= 0:
        return 0.0
    return roe / pb


def layer3_rank_and_cap(rows: list[dict], per_industry: int = 2, top_n: int = 20) -> list[dict]:
    scored = []
    for r in rows:
        item = dict(r)
        item["pb_roe"] = round(pb_roe_score(r), 4)
        scored.append(item)
    scored.sort(key=lambda x: x["pb_roe"], reverse=True)
    counts: dict[str, int] = defaultdict(int)
    out = []
    for r in scored:
        ind = str(r.get("industry") or "未知")
        if counts[ind] >= per_industry:
            continue
        counts[ind] += 1
        out.append(r)
        if len(out) >= top_n:
            break
    return out


def pe_percentile_in_window(current_pe: float, hist: pd.DataFrame, as_of=None, years: int = 5) -> float | None:
    if hist is None or hist.empty or current_pe is None or current_pe <= 0:
        return None
    as_of = pd.Timestamp(as_of or datetime.now())
    df = hist.copy()
    col = "数据日期" if "数据日期" in df.columns else df.columns[0]
    df[col] = pd.to_datetime(df[col], errors="coerce")
    pe_col = "PE(TTM)" if "PE(TTM)" in df.columns else None
    if pe_col is None:
        return None
    start = as_of - pd.DateOffset(years=years)
    window = df[(df[col] >= start) & (df[col] <= as_of)][pe_col]
    pct = _percentile_rank(float(current_pe), window)
    return round(pct, 1) if pct is not None else None
```

Layer3 scan wiring (later task): after rank, for each of top 15–20 call `fetch_valuation_history` + `pe_percentile_in_window`. If percentile is not None and **> 30**, drop. If None, keep with `pe_percentile_status = "unknown"`.

Add test:

```python
def test_layer3_drops_only_when_percentile_known_and_high():
    from quality_value_scanner import apply_pe_percentile_gate
    rows = [
        {"symbol": "LOW", "pe_percentile_5y": 20},
        {"symbol": "HIGH", "pe_percentile_5y": 80},
        {"symbol": "UNK", "pe_percentile_5y": None},
    ]
    kept = apply_pe_percentile_gate(rows, max_pct=30)
    assert {r["symbol"] for r in kept} == {"LOW", "UNK"}
```

```python
def apply_pe_percentile_gate(rows: list[dict], max_pct: float = 30.0) -> list[dict]:
    kept = []
    for r in rows:
        pct = r.get("pe_percentile_5y")
        item = dict(r)
        if pct is None:
            item["pe_percentile_status"] = "unknown"
            kept.append(item)
            continue
        if float(pct) > max_pct:
            continue
        item["pe_percentile_status"] = "ok"
        kept.append(item)
    return kept
```

**Step 4:** pytest Task 1–3 file → PASS.

---

## Task 4: Layer4 DeepSeek JSON parse + cycle veto + max 5

**Files:**
- Modify: `scripts/stock/quality_value_scanner.py`
- Test: `tests/test_quality_value_funnel.py`

**Step 1: Failing tests**

```python
from quality_value_scanner import parse_value_verdict, select_final_picks


def test_parse_value_verdict_extracts_json():
    raw = '```json\n{"verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"x","risk":"y"}\n```'
    out = parse_value_verdict(raw)
    assert out["verdict"] == "买入"
    assert out["cycle"] == "平稳"
    assert out["trap"] is False


def test_select_final_picks_vetoes_decline_and_trap_and_caps_five():
    cands = []
    for i in range(8):
        cands.append({
            "symbol": f"S{i}",
            "industry": f"I{i}",
            "llm": {
                "verdict": "买入",
                "score": 90 - i,
                "cycle": "上升" if i < 6 else "衰退",
                "trap": i == 1,
            },
        })
    picks = select_final_picks(cands, max_n=5)
    symbols = [p["symbol"] for p in picks]
    assert "S1" not in symbols  # trap
    assert "S6" not in symbols and "S7" not in symbols  # 衰退
    assert len(picks) <= 5
```

**Step 2:** FAIL.

**Step 3: Implement** using the same JSON-fence stripping pattern as `long_term_scanner` / `scanner` (search `json.loads` there). Also add `parse_value_verdict_list` for a JSON **array** (batch Layer4). `cycle in ("衰退",)` or `trap is True` or `verdict != "买入"` → drop. Sort remaining by score desc, max 5. Prefer unique industries (already capped at Layer3).

Batch output example the LLM must return:

```json
[{"symbol":"600000","verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"...","risk":"...","strategy":"..."}]
```

**Step 4:** pytest PASS.

---

## Task 5: Snapshot row parser (PE / PB / dividend fields)

**Files:**
- Modify: `scripts/stock/quality_value_scanner.py`
- Test: `tests/test_quality_value_funnel.py`

Eastmoney `push2.eastmoney.com/api/qt/clist/get` field map used elsewhere: `f9`=动态PE, `f23`=市净率. Dividend yield is commonly `f133` (percent). If live payload uses another field, parser must accept aliases.

**Step 1: Test**

```python
from quality_value_scanner import parse_clist_row, VALUE_CLIST_FIELDS


def test_parse_clist_row_pe_pb_div():
    item = {"f12": "600000", "f14": "浦发银行", "f2": 8.5, "f9": 5.2, "f23": 0.45, "f133": 5.1, "f20": 1e11}
    row = parse_clist_row(item)
    assert row["symbol"] == "600000"
    assert row["pe"] == 5.2
    assert row["pb"] == 0.45
    assert row["div_yield"] == 5.1


def test_value_clist_fields_include_pb_and_div():
    assert "f23" in VALUE_CLIST_FIELDS
    assert "f133" in VALUE_CLIST_FIELDS or "f37" in VALUE_CLIST_FIELDS
```

**Step 2–4:** Implement `VALUE_CLIST_FIELDS` as the `fields=` query string including existing scanner fields plus `f23` and dividend. `parse_clist_row` uses `_num_val` copied from `right_side_scanner.py` (do not import from that module to avoid coupling). Fallback: if `ak.stock_zh_a_spot_em()` already has `市净率` / `股息率`, map those column names in `rows_from_spot_df(df)`.

Add `rows_from_spot_df` test with a tiny DataFrame of 代码/名称/市盈率-动态/市净率/股息率.

When fetching: try Eastmoney clist with expanded fields → else `ak.stock_zh_a_spot_em` (map `市净率` and `股息率` if present) → else sina (valuation already maps `pb`). **Dividend:** treat `f133` as optional; if the live payload uses another field, accept aliases (`f37`, column `股息率`). If still missing, leave `div_yield=None` (Layer1 must not kill).

**Industry (hard rule):** `attach_industry(rows)` reads only existing caches (`scripts/stock` `.industry_map.json` under `STOCK_CACHE_DIR`, and/or `valuation` `_CACHE_INDUSTRY_MAP`). Do **not** call `ak.stock_board_industry_cons_em` / `_fetch_industry_map` network rebuild from this scanner. Cache miss → empty industry → Layer1 `industry_unknown`.

---

## Task 6: Scanner lifecycle, report, RAG (clone long-term)

**Files:**
- Modify: `scripts/stock/quality_value_scanner.py`
- Test: `tests/test_quality_value_scanner_api.py`

Mirror `long_term_scanner.py` public API:

- `QUALITY_VALUE_DIR = os.path.join(STOCK_REPORTS_ROOT, "quality_value")`
- `PROGRESS_FILE = .../qv_progress.json`
- `start_qv_scan(use_deepseek=False)`, `stop_qv_scan()`, `get_qv_status()`, `get_qv_latest_result()`, `get_qv_history()`, `get_qv_result_by_date(date_str)`
- Persist `sys` globals like `right_side_scanner` / `unified_scanner` if the stock import decorator reloads the module (copy that pattern from `right_side_scanner.py` comments at top).

**Step 1: Test start-already-running and status shape** with a fake target that sleeps, or test `_save_progress` round-trip:

```python
def test_start_qv_scan_rejects_second(monkeypatch):
    import quality_value_scanner as qv
    monkeypatch.setattr(qv, "_qv_thread", type("T", (), {"is_alive": lambda self: True})())
    out = qv.start_qv_scan()
    assert out["ok"] is False
```

(Adjust if you use the `sys` persistence trick — then mock `sys._qv_thread`.)

**Step 2–4:** Implement `_run_qv_scan`:

1. Fetch snapshot → Layer1 → progress `layer1`
2. For each Layer1 survivor (already ≤100), `fetch_fundamentals_for_value(symbol)` (new helper): call `ak.stock_financial_abstract_ths(..., indicator="按年度")`, parse last 3 years 净利润 for CAGR, ROE, 资产负债率. **扣非:** if the column looks like a percent, use it /100; if it looks like 金额, ratio = 扣非净利润/净利润 when 净利润≠0. Dividend via `ak.stock_fhps_detail_em` or `stock_history_dividend` **inside `eastmoney_throttle`**; cache JSON under `STOCK_CACHE_DIR/.quality_value/{symbol}.json` for 24h. Failures → leave fields None (`unknown`).
3. Layer2 → Layer3 rank/cap → percentile gate (only those names).
4. If `use_deepseek`: **one** Layer4 LLM call with all remaining candidates (cap 10 in the prompt), parse JSON array, then `select_final_picks`. Else take Top5 by `pb_roe` and set `llm_skipped: true`.
5. Write `{date}.json` + `{date}-report.md`. Index RAG like `_index_report_to_rag` in `long_term_scanner.py` with `item_type="stock_scan_quality_value"`.
6. Honor `_stop_event` between layers.

Report markdown must include the compliance line: **不构成投资建议**. 0 picks: explain 宁缺毋滥.

Do **not** call `fetch_fundamentals` 5000 times. Cap Layer2 fetches at Layer1 output (expect ≤100). Sleep/throttle between calls.

---

## Task 7: DeepSeek value persona (not 1–2 week ruler)

**Files:**
- Modify: `scripts/stock/llm_reasoning.py`
- Modify: `docs/stock-modules/llm_reasoning.md` (one paragraph listing the new builder)
- Test: `tests/test_quality_value_funnel.py` or `tests/test_llm_reasoning_value_prompt.py`

**Step 1:**

```python
from llm_reasoning import build_quality_value_system_prompt

def test_value_prompt_is_not_short_horizon():
    p = build_quality_value_system_prompt()
    assert "6个月" in p or "6 个月" in p
    assert "2年" in p or "2 年" in p
    assert "价值陷阱" in p
    assert "行业周期" in p
    assert "1周/2周" not in p
```

**Step 3:** New function **does not** call `deepseek_shared_persona_rules()` (that ruler is 1–2 weeks). Write a dedicated value-investor prompt: ROE quality, same-industry cheapness, cycle up/flat/down, trap veto, **商誉/减值风险**, empty-portfolio 6m–2y allocation.

Also add `assert "商誉" in p` to the prompt test.

Output is a **JSON array**, one object per input candidate (or only the ones worth buying — parser must accept both). Each object:

```json
{"symbol":"600000","verdict":"买入","score":75,"cycle":"平稳","trap":false,"reason":"...","risk":"...","strategy":"仓位与6个月～2年持有纪律"}
```

`cycle` ∈ `上升|平稳|衰退`. Wire Layer4 like `long_term_scanner._llm_final_selection` (single call), not left-scanner per-stock Layer3.

**Step 4:** pytest PASS.

---

## Task 8: Flask routes

**Files:**
- Modify: `scripts/rag/routes/stock.py`
  - Add `"quality_value_scanner"` to `_STOCK_MODULES`
  - Copy the long-term block at lines 488–566 to `/api/stock/quality-value/start|status|stop|result|history|dates` and `result/<date_str>`

**Step 1:** If there is an existing route test pattern, add one; otherwise a tiny test that the functions exist:

```python
def test_qv_public_api_exists():
    import quality_value_scanner as qv
    assert callable(qv.start_qv_scan)
    assert callable(qv.get_qv_status)
```

Manual check after UI: POST start returns `{ok: true}`.

Do not modify unified/left/right/long-term route handlers.

---

## Task 9: Toolbar button + modal UI

**Files:**
- Modify: `scripts/rag/templates/index.html`

Clone the long-term modal (`#longTermModal` ~1210–1243) and JS (`openLongTermModal` ~6446+) with prefix `qv` / `quality-value`.

**Toolbar** (after 长期推荐 button, ~line 420):

```html
<button type="button" class="toolbar-btn" onclick="openQualityValueModal()" title="优质低估选股：同业低估 + 基本面排雷 + PB-ROE + DeepSeek 周期终审">&#128176; 优质低估</button>
```

Modal copy: four-step funnel in 小白 language; checkbox DeepSeek; 开始扫描 / 停止 / 历史 / 导出PDF (`exportStockPdf('quality_value','qv')` once Task 11 lands — until then hide PDF or no-op).

Result renderer: cards with 代码、行业、PE/PB、股息、ROE、同业对比、PE分位、PB-ROE、周期、风险. 0 picks: calm empty state, not an error.

Poll `/api/stock/quality-value/status` like `pollLtStatus`.

---

## Task 10: PDF type (optional but in design)

**Files:**
- Modify: `scripts/stock/stock_pdf.py` — add `"quality_value"` to report types and `_build_quality_value` cloning `_build_long_term` with value fields.

If export wiring in `index.html` `exportStockPdf` uses a switch, add the new type there too (search `long_term`).

---

## Task 11: Docs

**Files:**
- Create: `docs/stock-modules/strategy-quality-value-deepseek.md` — follow `strategy-long-term-deepseek.md` template (比喻 → 金融逻辑 → 漏斗 → DeepSeek → 何时用 → 报告怎么读 → 纪律 → 与另外四套对照). Horizon **6 个月～2 年**. Compliance disclaimer. Financial-industry exception. 0 picks is OK. Explicitly: **规则层不筛商誉暴雷**，由 DeepSeek 在终审里看商誉/减值；缺分红/扣非/历史分位只标记 unknown。
- Create: `docs/stock-modules/quality_value_scanner.md` — same 7-section tech template as other module docs (概述 / 金融理论 / 实现 / 数据源 / 配置 / 工作流 / 限制).
- Modify: `docs/guides/stock-strategy-guide.md` — fifth row in the feature table + 「另外三套」→「另外几套」row for 优质低估.
- Modify: `docs/stock-modules/README.md` — strategy table + 扫描与综合层 table.
- Modify: `docs/stock-modules/strategy-unified-left-right-deepseek.md` §8 对照表 — add a column/row pointing at the new strategy (do not change left/right rules).
- Modify: `docs/stock-modules/llm_reasoning.md` — list `build_quality_value_system_prompt`.
- Modify: `docs/plans/README.md` — add this plan to Active Plans.

YAGNI: do not write Telegram help unless you already touch `bot_telegram.py` for a scanner list.

---

## Task 12: Verification

Run:

```
python -m pytest tests/test_quality_value_funnel.py tests/test_quality_value_scanner_api.py tests/test_llm_reasoning_value_prompt.py -v
```

Expected: all PASS.

Manual (when market data available): open 优质低估 → DeepSeek on → start → progress moves layer1→layer2→layer3→layer4 → 0–5 cards; ST names absent; a bank can survive high debt if ROE/dividend ok.

Do **not** claim success without pytest output. Do **not** treat “0 picks on a live scan” as failure.

---

## Out of scope

- Changing left/right unified funnel or 1–2 week persona.
- Folding this into long-term themes.
- Per-stock `compute_valuation()` / DCF on the whole market.
- Guaranteeing 扣非 or 3-year dividend from every data vendor on day one (`unknown` is the spec).
- Rebuilding the full Eastmoney industry board map inside this scanner.
- Rule-layer 商誉 numeric filter (v1).
