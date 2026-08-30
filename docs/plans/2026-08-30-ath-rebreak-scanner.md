# Near-5y High Pullback Rebreak Scanner Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Add a shared 「近5年高 → 回踩 → 二次突破」 detector, a third unified-scan recommendation column, and the same stage block in A-share DeepSeek analysis — without changing left/right funnels.

**Architecture:** Pure function detector `ath_rebreak.py` reads a daily OHLCV DataFrame (existing ~5y 前复权 `daily.csv`). `ath_rebreak_scanner.py` is a plugin scanner (sys-persisted status, `market_df` argument). `unified_scanner` starts it after right-side. `technical_analysis.analyze` and `llm_reasoning._build_deepseek_prompt` call the same detector. UI adds a third column. Do not modify `scanner.py` / `right_side_scanner.py` Layer1–2 filters.

**Tech Stack:** Python 3, pandas, pytest, existing `scan_cache` / `fetch_daily_ohlcv` / `call_deepseek`, Flask `scripts/rag/routes/stock.py`, `scripts/rag/templates/index.html`.

---

## Confirmed decisions (do not re-litigate)

- v1 benchmark = **max(high) of available daily.csv** (~5 years, 前复权). UI/reports must say **「近5年高（前复权）」**, never 「历史最高」 / ATH.
- First close above the prior 5y high is the **mark, not a buy**. Buy candidate = pullback then close through B (if undercut B) or through the flag peak (if `pct_3_8`/`shallow` only), ≥3 bars after first break, live if rebreak is in the last 3 bars.
- Pullback tags (a row may have several): `below_high` (A), `pct_3_8` (B), `shallow` (C).
- Limit-up on rebreak day: still detect, `tradeable=False`.
- Third independent report column in the unified modal; left/right logic unchanged.
- A-share analysis uses the same detector; do not ask DeepSeek to infer the pattern from the 20-day OHLCV table.
- No true listing-since ATH, no backtest module, no left-side filter change.
- 0 picks is a valid outcome.
- Persist scanner state on `sys` (`sys._ath_*`). Pass `market_df` into `start_ath_rebreak_scan`; do not rely on module-level shared df.
- ChiNext/STAR limit-up: `change_pct >= 19.5` if code starts with `30` or `68`; else `>= 9.5`.
- Layer3: if DeepSeek unchecked, keep rule-layer hits and mark 「未经 AI 终审」 (same idea as quality-value).

---

## Review patches (2026-08-30)

Plan review found a state-machine conflict, a missing flag-above-B tag, and vague Layer1 units. The bullets below override the Detector contract and Task 1/4 where they disagree.

1. **Rebreak has priority over a new first-break on the same bar (must-fix).**  
   Walk-forward as first written resets whenever `close[i] > max(high[:i])`. The rebreak bar usually *is* a new 5y high, so the setup would reset and **never emit `rebreak`**.  
   Correct order for each `i`: (a) if there is an open setup from `T` and pullback tags are non-empty and `i >= T+3`, test the trigger; if it fires, record rebreak and **do not** start a new first-break on that same bar. (b) Else if `close[i] > max(high[:i])`, start/replace first-break.

2. **`pct_3_8` is drawdown from peak, not only from B.**  
   A flag that holds above B (peak 10.8 → 10.2, B=10.1) got **zero tags** under the old rule. Tag `pct_3_8` when `0.03 <= pullback_pct <= 0.08` (peak → pullback low). Keep `below_high` as an extra tag when price also lost B.  
   Trigger: if `below_high` in tags → first `close > B`; else (`pct_3_8` or `shallow`) → first `close > peak` computed on `high[T:i]` (new high after the flag).

3. **Layer1 成交额 is 元, floor `>= 30_000_000` (same as right-side).** Do not guess 万元. Cap 100 by `涨跌幅 * 成交额`, not 涨跌幅 alone. Codes: `60/00/30/68` (68 is extra vs right-side; keep it).

4. **Tests must use `pd.bdate_range("2024-01-02", periods=n, freq="B")`** for dates — never `2025-01-{i}` (overflows 31).

5. **Add a unit test** where the rebreak bar is also a new 5y high; it must still be `stage=rebreak` and `signal_live=True`.

---

## Review patches (round 2, 2026-08-30)

First-pass patches were incomplete: the Detector contract still contradicted itself, Task 1 still used overflowing dates, and the stale-signal test was dropped.

6. **Detector rules 2 and 6 are superseded by patches 1–2.** Do not implement “every `close > running max` starts a new first-break” as an unconditional first step. Walk each bar in this order only: open-setup trigger → else new first-break. `pct_3_8` is **peak drawdown**, never `(B - low) / B`.

7. **Restore `test_stale_rebreak_not_live`.** Verification Summary still requires it. `_ohlcv` dates **must** be `pd.bdate_range("2024-01-02", periods=n, freq="B")` (the sample code below is wrong if it still uses `2025-01-{i}`).

8. **Limit-up column after `load_ohlcv`:** 涨跌幅 is renamed to `pct_change`. Detector must read `pct_change` or `涨跌幅` or `change_pct`. Otherwise `analyze()` never marks 涨停.

9. **Task 2:** `tmp_path.joinpath("600000").mkdir()` before `analyze`, or writing `technical.json` fails.

10. **Layer2 I/O:** ATH Layer1 prefers names with 涨幅 > +7%，右侧缓存往往没有这些票。最多 100 次 `fetch_daily_ohlcv`。必须用与 `right_side_scanner.analyze_single` 同类的线程池 + `eastmoney_throttle`，不要串行。

11. **Add `test_flag_above_b_pct_3_8`:** peak 回撤 3%–8% 且从未跌破 B，二次收盘创新高 → `pct_3_8` + live rebreak.

12. **Task 8:** `docs/plans/README.md` 已有本计划行，不要重复加。

---

## Review patches (round 3, 2026-08-30)

No new architecture. Two remaining contract/test bugs:

13. **Stale rebreak vs Rule 8.** Old Rule 8 said “only keep a rebreak if live, else current setup”, which would make `test_stale_rebreak_not_live` get `stage=none`. Return the last rebreak even when stale, unless a **newer** first-break opened after it.

14. **Task 2 mock bypasses `load_ohlcv` rename.** `analyze()` then `compute_indicators` needs English `close/high/...`. The analyze test DataFrame must already be normalized (or built with English names), not the Chinese `_ohlcv()` helper.

Implement the **Walk-forward rules** block only; patches 1–14 are rationale.

---

## Detector contract (authoritative)

```python
# Return dict always JSON-serializable.
{
  "ok": bool,
  "benchmark_label": "近5年高（前复权）",
  "benchmark": float | None,          # B = prior running max(high) that was first broken
  "benchmark_date": str | None,       # date of the bar that first closed > B
  "peak": float | None,               # max high from first-break bar through pullback window
  "stage": "insufficient_history" | "none" | "first_break" | "pullback" | "rebreak",
  "pullback_tags": list[str],         # subset of {"below_high", "pct_3_8", "shallow"}
  "pullback_pct": float | None,       # (peak - pullback_low) / peak, 0-1
  "rebreak_date": str | None,
  "signal_live": bool,                # stage==rebreak and rebreak within last 3 bars
  "tradeable": bool,                  # signal_live and not limit-up on rebreak bar
  "limit_up_on_rebreak": bool,
  "reason": str,
}
```

**Walk-forward rules** (this block is authoritative; ignore any older “reset on every new high first” wording)

1. Require ≥ 60 bars after column normalize (`date/open/high/low/close/volume` and `pct_change`; accept 日期/开盘/最高/最低/收盘/成交量/涨跌幅). Cast numerics to Python `float` before returning JSON.
2. Scan `i = 1 .. n-1`. Maintain at most one **open setup** (`B`, `T`).
3. **Per bar, in this order:**
   - If an open setup exists, `i >= T+3`, and pullback tags using bars `T+1 .. i-1` are non-empty, test trigger (step 6). On success: record rebreak at `i`, close the setup, **stop processing this bar** (do not also open a new first-break).
   - Else if `close[i] > max(high[:i])`: open/replace first-break with `B = max(high[:i])`, `T = i`.
4. If the last event is an open first-break with fewer than 3 later bars → `stage=first_break`.
5. Pullback tags (bars after `T`, before trigger):
   - `below_high` if any `low < B` or `close < B`
   - `pullback_pct = (peak - pullback_low) / peak` with `peak = max(high[T:i])` (exclude current bar when testing trigger), `pullback_low = min(low[T+1:i])`
   - `pct_3_8` if `0.03 <= pullback_pct <= 0.08`
   - `shallow` if `0 < pullback_pct < 0.03`
6. Trigger (tags must be non-empty):
   - `below_high` → `close[i] > B`
   - else `pct_3_8` or `shallow` → `close[i] > max(high[T:i])`
7. `signal_live` if trigger index `>= n-3`. `tradeable` if live and not `is_limit_up` on that bar’s `pct_change`/`涨跌幅`/`change_pct`.
8. No first-break in the series → `stage=none`. After a rebreak, later bars may open a **new** first-break (next cycle). **Return value:** if a newer open setup exists after the last rebreak, report that setup; else if any rebreak was recorded, `stage=rebreak` with `signal_live` only if that rebreak index `>= n-3` (stale rebreak stays `stage=rebreak`, `signal_live=False`). Do not drop a stale rebreak down to `none`.

Do not fetch network inside `ath_rebreak.py`.

---

### Task 1: Detector unit tests + `ath_rebreak.py`

**Files:**
- Create: `tests/test_ath_rebreak.py`
- Create: `scripts/stock/ath_rebreak.py`

**Step 1: Write the failing test**

```python
# tests/test_ath_rebreak.py
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from ath_rebreak import detect_five_year_rebreak, is_limit_up, BENCHMARK_LABEL


def _ohlcv(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs or [c + 0.1 for c in closes]
    lows = lows or [c - 0.1 for c in closes]
    dates = pd.bdate_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘": closes,
        "最高": highs,
        "最低": lows,
        "收盘": closes,
        "成交量": [1_000_000] * n,
        "涨跌幅": [0.0] * n,
    })


def test_label_is_five_year_not_ath():
    assert "历史最高" not in BENCHMARK_LABEL
    assert "近5年高" in BENCHMARK_LABEL


def test_insufficient_history():
    df = _ohlcv([10.0] * 20)
    out = detect_five_year_rebreak(df, "600000")
    assert out["ok"] is False
    assert out["stage"] == "insufficient_history"


def test_first_break_is_not_a_buy():
    # 60 bars at 10, then close 11 > prior high 10.1
    closes = [10.0] * 60 + [11.0]
    highs = [10.1] * 60 + [11.2]
    lows = [9.9] * 60 + [10.8]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "first_break"
    assert out["signal_live"] is False
    assert out["tradeable"] is False
    assert out["benchmark"] == 10.1


def test_rebreak_requires_three_day_pause():
    # first break at i=60, then immediately another close above B the next day
    closes = [10.0] * 60 + [11.0, 11.2]
    highs = [10.1] * 60 + [11.2, 11.3]
    lows = [9.9] * 60 + [10.0, 10.0]  # dipped below B=10.1
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] in ("first_break", "pullback")
    assert out["signal_live"] is False


def test_below_high_then_rebreak_live():
    # 60 @10, break 11, three days below B, then close 11.5
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5]
    chg = [0.0] * 64 + [2.0]
    df = _ohlcv(closes, highs, lows)
    df["涨跌幅"] = chg
    out = detect_five_year_rebreak(df, "600000")
    assert out["ok"] is True
    assert out["stage"] == "rebreak"
    assert "below_high" in out["pullback_tags"]
    assert out["signal_live"] is True
    assert out["tradeable"] is True


def test_limit_up_rebreak_not_tradeable():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5]
    df = _ohlcv(closes, highs, lows)
    df["涨跌幅"] = [0.0] * 64 + [10.0]
    out = detect_five_year_rebreak(df, "600000")
    assert out["signal_live"] is True
    assert out["limit_up_on_rebreak"] is True
    assert out["tradeable"] is False


def test_is_limit_up_gem():
    assert is_limit_up("300001", 19.5) is True
    assert is_limit_up("300001", 10.0) is False
    assert is_limit_up("600000", 9.5) is True
    assert is_limit_up("600000", 9.4) is False


def test_rebreak_bar_that_is_also_new_five_year_high_still_counts():
    """Regression: do not reset first-break on the trigger bar."""
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 12.0]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 12.1]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is True


def test_stale_rebreak_not_live():
    body = [10.0] * 60
    closes = body + [11.0, 9.8, 9.7, 9.6, 11.5, 11.4, 11.3, 11.2]
    highs = [10.1] * 60 + [11.2, 10.0, 9.9, 9.8, 11.6, 11.5, 11.4, 11.3]
    lows = [9.9] * 60 + [10.8, 9.5, 9.4, 9.3, 10.5, 11.0, 11.0, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is False


def test_flag_above_b_pct_3_8():
    """Hold above B, 5% flag from peak, then new high."""
    body = [10.0] * 60
    # break to 11, flag 11.0 → 10.45 (~5% off 11.2 high), never under B=10.1, then 12
    closes = body + [11.0, 10.7, 10.5, 10.45, 12.0]
    highs = [10.1] * 60 + [11.2, 10.8, 10.6, 10.5, 12.1]
    lows = [9.9] * 60 + [10.8, 10.5, 10.45, 10.4, 11.0]
    out = detect_five_year_rebreak(_ohlcv(closes, highs, lows), "600000")
    assert "pct_3_8" in out["pullback_tags"]
    assert "below_high" not in out["pullback_tags"]
    assert out["stage"] == "rebreak"
    assert out["signal_live"] is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ath_rebreak.py -v`
Expected: FAIL with `ModuleNotFoundError: ath_rebreak` (or import error).

**Step 3: Write minimal implementation**

Create `scripts/stock/ath_rebreak.py` implementing `BENCHMARK_LABEL`, `is_limit_up`, `_normalize_ohlcv`, `detect_five_year_rebreak` exactly as **Detector contract** above. Keep it side-effect free.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ath_rebreak.py -v`
Expected: PASS. Fix the detector if a synthetic edge fails; do not weaken tests. Dates in tests are `bdate_range` (Review patch 7).

---

### Task 2: Attach detector to technical analysis

**Files:**
- Modify: `scripts/stock/technical_analysis.py` (`analyze`)
- Test: `tests/test_ath_rebreak.py` (add one test that mocks analyze OR test a thin wrapper)

**Step 1: Failing test**

Add to `tests/test_ath_rebreak.py`:

```python
def test_analyze_includes_five_year_rebreak(monkeypatch, tmp_path):
    import technical_analysis as ta
    n = 61
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-02", periods=n, freq="B"),
        "open": [10.0] * n,
        "high": [10.1] * 60 + [11.2],
        "low": [9.9] * 60 + [10.8],
        "close": [10.0] * 60 + [11.0],
        "volume": [1_000_000] * n,
        "pct_change": [0.0] * n,
    })
    monkeypatch.setattr(ta, "load_ohlcv", lambda symbol: df)
    monkeypatch.setattr(ta, "STOCK_DATA_DIR", str(tmp_path))
    (tmp_path / "600000").mkdir()
    result = ta.analyze("600000")
    assert "five_year_rebreak" in result
    assert result["five_year_rebreak"]["benchmark_label"] == BENCHMARK_LABEL
```

`analyze` currently writes `technical.json` under `STOCK_DATA_DIR`. Monkeypatch that path so tests do not touch real data.

**Step 2:** Run the new test — FAIL (`five_year_rebreak` missing).

**Step 3:** In `analyze`, after `calc_support_resistance`:

```python
from ath_rebreak import detect_five_year_rebreak
result["five_year_rebreak"] = detect_five_year_rebreak(df, symbol)
```

Do not change support/resistance lookback.

**Step 4:** Re-run `python -m pytest tests/test_ath_rebreak.py -v` — PASS.

---

### Task 3: DeepSeek materials + persona line

**Files:**
- Modify: `scripts/stock/llm_reasoning.py` (`_build_deepseek_prompt` around the technical section ~410–437; `generate_prediction_deepseek` system_prompt list)
- Test: `tests/test_ath_rebreak_prompt.py`

**Step 1: Failing test**

```python
# tests/test_ath_rebreak_prompt.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from llm_reasoning import format_five_year_rebreak_section


def test_section_says_not_a_buy_on_first_break():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "first_break",
        "pullback_tags": [],
        "signal_live": False,
        "tradeable": False,
        "reason": "标杆已立",
    })
    assert "近5年高" in text
    assert "历史最高" not in text
    assert "还不是买点" in text


def test_live_rebreak_is_candidate():
    text = format_five_year_rebreak_section({
        "ok": True,
        "benchmark_label": "近5年高（前复权）",
        "benchmark": 10.1,
        "stage": "rebreak",
        "pullback_tags": ["below_high"],
        "signal_live": True,
        "tradeable": True,
        "rebreak_date": "2026-08-28",
        "reason": "",
    })
    assert "买点候选" in text
```

**Step 2:** FAIL — `format_five_year_rebreak_section` missing.

**Step 3:** Implement `format_five_year_rebreak_section(block: dict) -> str` in `llm_reasoning.py`:

- `insufficient_history` / missing → `## 近5年高二次突破\n数据不足，无法判断该形态。`
- `first_break` → 标杆已立，还不是买点
- `pullback` → 阶段=回踩, tags, 等待二次突破
- `rebreak` + live + tradeable → 策略买点候选；仍须交叉验证资金/估值
- `rebreak` + live + not tradeable → 形态成立但涨停买不到
- `rebreak` not live → 历史二次突破，不是当前买点

Call it from `_build_deepseek_prompt` using `tech.get("five_year_rebreak")` **and**, if missing, compute via `detect_five_year_rebreak` on full `daily.csv` (not the 20-row slice). Add one system_prompt bullet: 「近5年高形态以材料中的检测结果为准，禁止用近20日表自行发明历史高点。」

**Step 4:** `python -m pytest tests/test_ath_rebreak_prompt.py tests/test_ath_rebreak.py -v` — PASS.

---

### Task 4: Scanner Layer1 + Layer2 (no LLM)

**Files:**
- Create: `scripts/stock/ath_rebreak_scanner.py` (lifecycle + Layer1/2 only in this task)
- Test: `tests/test_ath_rebreak_scanner_funnel.py`

Follow `docs/guides/stock-new-strategy-guide.md` skeleton. Names: `start_ath_rebreak_scan`, `stop_ath_rebreak_scan`, `get_ath_rebreak_scan_status`, `get_latest_ath_rebreak_result`, `get_ath_rebreak_result_by_date`, `list_ath_rebreak_scan_dates`. Sys keys: `_ath_status`, `_ath_thread`, `_ath_stop`, `_ath_lock`.

**Layer1 (`layer1_active_near_high(df) -> list[dict]`)** — operate on shared spot `market_df` columns `代码/名称/最新价/涨跌幅/换手率/成交额`:

- Drop name containing `ST` or `退`
- Code startswith `60`/`00`/`30`/`68`
- `最新价` in [3, 300]
- `换手率 >= 1.0`, `成交额 >= 30_000_000`（元；与右侧 Layer1 同一单位，不要当万元）
- Sort by `涨跌幅 * 成交额` descending, **cap 100**
- Do **not** apply right-side `涨跌幅 <= +7` cap

**Layer2:** for each Layer1 name, `scan_cache.ohlcv_done` → skip fetch; else `fetch_daily_ohlcv(sym)` + `mark_ohlcv`. `load_ohlcv` + `detect_five_year_rebreak`. Keep rows with `signal_live`. Include non-tradeable limit-up rows with a flag. Cap kept list at 15 before Layer3. Fetch with a thread pool + `eastmoney_throttle` (do not loop 100 symbols serially).

**Step 1: Failing tests** for `layer1_active_near_high` (ST dropped, cap 100, +8% name kept) and a Layer2 helper `filter_live_rebreaks(results)` keeping only `signal_live`.

**Step 2:** FAIL.

**Step 3:** Implement those functions in `ath_rebreak_scanner.py`. `_run_thread` may still no-op Layer3.

**Step 4:** `python -m pytest tests/test_ath_rebreak_scanner_funnel.py -v` — PASS.

---

### Task 5: Layer3 DeepSeek + JSON/MD reports

**Files:**
- Modify: `scripts/stock/ath_rebreak_scanner.py`
- Modify: `scripts/stock/llm_reasoning.py` — add `build_ath_rebreak_layer3_system_prompt()` next to `build_right_layer3_system_prompt` (reuse `deepseek_shared_persona_rules`, plus: 确认是否假突破/吹顶；涨停则 verdict 不买入；文案用近5年高)
- Test: `tests/test_ath_rebreak_layer3.py` — parse JSON verdict; empty picks markdown contains 「暂无」 and 「近5年高」 not 「历史最高」

**Step 1:** Test `_parse_ath_json` and `_generate_ath_markdown_report([])`.

**Step 2:** FAIL.

**Step 3:** Mirror `right_side_scanner.py` save path pattern:

- JSON: `{STOCK_REPORTS_ROOT}/data/ath_rebreak_scan/ath_rebreak_{date}.json`
- MD: `{STOCK_REPORTS_ROOT}/ath_rebreak_scan_reports/ath_rebreak_scan_report_{date}.md`
- `scan_type`: `ath_rebreak`
- Each pick: symbol, name, price, detector fields, `verdict`, `reasoning`, `risk`, `buy_low`/`buy_high`, `stop_loss`, `judged_by`
- Layer3 only on `tradeable` names unless you still want DeepSeek to say 不买入 for limit-up — prefer: limit-up stays in report as 观察/买不到 **without** counting as a buy pick
- Optional RAG index: copy `_index_rs_report_to_rag` pattern; if it is more than ~20 lines of new glue, skip RAG in v1 (YAGNI) and say so in the markdown footer

**Step 4:** pytest for this task PASS. Manual: do not call live DeepSeek in unit tests (mock `call_deepseek`).

---

### Task 6: Wire `unified_scanner`

**Files:**
- Modify: `scripts/stock/unified_scanner.py`
  - `_status` / `start_unified_scan` init: add `"ath": None`
  - `_stale` list: add `"ath_rebreak_scanner"`, `"ath_rebreak"`
  - `stop_unified_scan`: also `stop_ath_rebreak_scan()`
  - `_run_unified_inner`: after right scan, start ath with `market_df=df`; `_ensure_stock_config` before start (same comment as right-side)
  - Progress: market 0–8, left 8–40, right 40–68, ath 68–100 (`base_progress`/`span` on `_wait_for`)
  - `get_latest_unified_result`: add `"ath": get_ath_rebreak_result_by_date(...)`
- Test: `tests/test_unified_ath_wiring.py` — import the module and assert `get_latest_unified_result` has key `ath` (mock the three getters). If import is heavy, test a small helper `merge_unified_payload(left, right, ath)` extracted for this purpose — prefer extracting 10-line helper over mocking the world.

Do not change left/right start signatures.

**Verify:** `python -m pytest tests/test_unified_ath_wiring.py tests/test_ath_rebreak.py -v`

---

### Task 7: Routes + unified modal UI

**Files:**
- Modify: `scripts/rag/routes/stock.py` — add `"ath_rebreak"`, `"ath_rebreak_scanner"` to `_STOCK_MODULES`. No new public routes required if results ride on `/api/stock/unified_scan/result`; optional standalone `/api/stock/ath_rebreak_scan/status` is YAGNI unless debugging needs it — **skip standalone routes in v1**.
- Modify: `scripts/rag/templates/index.html`
  - Toolbar tooltip / modal `<h2>`: mention 三套（左/右/近5年高二次突破）
  - Grid: `grid-template-columns:1fr 1fr 1fr`; add `#uniAthResult` column heading 「近5年高 · 二次突破」; placeholder text states 标杆=近5年高（前复权），回踩后再突破才是买点
  - Widen panel `width` from 1080px to ~1280px
  - `startUnifiedScan`: third pane waiting copy
  - `pollUnifiedStatus`: `d.phase === 'ath'`; live `d.ath.step`
  - `loadUnifiedResult`: `d.ath.picks` via `_buildAthRebreakHtml` (clone `_buildRightSideHtml`, show tags, `tradeable`, 买不到)
- Test: `tests/test_ath_rebreak_ui.py` — read `index.html` as text, assert `uniAthResult`, `近5年高`, and `grid-template-columns:1fr 1fr 1fr` exist; assert `历史最高` does **not** appear in the new column placeholder (search the unified modal slice).

**Step 4:** `python -m pytest tests/test_ath_rebreak_ui.py -v` PASS.

Browser (when a running RAG/stock server exists): open unified modal, confirm three columns, start scan only if the user environment is already up — do not invent a hang by fetching 5000 names in the agent unless asked. If the server is not running, record that UI was verified by fixture tests only.

---

### Task 8: Docs (small, match existing stock-module style)

**Files:**
- Create: `docs/stock-modules/ath_rebreak.md` (one-page: detector + scanner + 近5年高 disclaimer)
- Create: `docs/stock-modules/strategy-ath-rebreak-deepseek.md` (small-white: 不是圣杯、涨停买不到、与左右哲学关系)
- Modify: `docs/guides/stock-strategy-guide.md` — add a table row pointing at the new strategy doc
- Modify: `docs/stock-modules/unified_scanner.md` — third branch in the ASCII diagram; `ath` status field
- Modify: `docs/guides/stock-new-strategy-guide.md` — one sentence that `ath_rebreak_scanner` is the first extra plugin on unified
- `docs/plans/README.md` — already lists this plan; skip unless the row is missing

Do not rewrite left/right strategy docs except a one-line pointer in `strategy-unified-left-right-deepseek.md` § related features.

---

## Verification Summary

- [ ] `python -m pytest tests/test_ath_rebreak.py tests/test_ath_rebreak_prompt.py tests/test_ath_rebreak_scanner_funnel.py tests/test_ath_rebreak_layer3.py tests/test_unified_ath_wiring.py tests/test_ath_rebreak_ui.py -v` all PASS
- [ ] Left/right Layer1 filters in `scanner.py` / `right_side_scanner.py` unchanged (diff should not touch those filter blocks)
- [ ] No user-facing string 「历史最高」 in new scanner report templates or unified modal third column
- [ ] `get_latest_unified_result()` returns `ath` key
- [ ] Detector: first break ≠ buy; <3 day pause ≠ rebreak; limit-up ≠ tradeable; stale >3 bars ≠ live

---

## Out of scope

- Listing-since true ATH fetch
- `backtest_engine` strategy
- Telegram
- Changing MA20 right-side definition
- Nightly precomputed high table
