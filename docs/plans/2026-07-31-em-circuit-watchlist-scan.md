# East Money Circuit Breaker + Watchlist Light Refresh + ChiNext Filter

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Stop East Money `RemoteDisconnected` from burning minutes of retries on watchlist refresh and unified left/right scans; make「刷新列表」Sina-realtime-only; exclude ChiNext (`300`/`301`) from scanner universes while keeping STAR (`688`/`689`).

**Architecture:** Add a process-wide East Money circuit breaker next to the existing throttle. When open, EM akshare/hist/info/fund-flow paths skip immediately to proven fallbacks (Sina OHLCV, CompanySurvey, cached fund-flow). Watchlist `refresh_all_data` only updates realtime quotes via Sina. Left (`scanner.py`) and right (`right_side_scanner.py`) Layer-1 filters drop `300`/`301`.

**Tech Stack:** Python 3, existing `eastmoney_throttle`, `fetch_market_data`, `china_market_data`, `watchlist`, pytest.

**Approved decisions (do not re-litigate):**
1. Approach C + B: circuit breaker + fast fallback; watchlist refresh = Sina realtime only; full update stays on「数据预热」.
2. Same EM failure root cause fixes unified scanner (left + right · shared data) via shared circuit — not a separate scanner redesign.
3. Exclude ChiNext prefixes `300` and `301` only; **keep** STAR `688`/`689`.
4. Do not block adding ChiNext symbols to the personal watchlist.
5. Prefer fixing root wasted retries over “fail empty faster” as the primary success metric.

**Out of scope:** Changing buy-gate / Layer-3 policy; removing STAR; Telegram-only paths; rewriting national-team ETF logic.

**Runtime evidence (2026-07-31):**
| Source | Result |
|--------|--------|
| Sina realtime / Sina OHLCV / CompanySurvey / `stock_news_em` | OK (~0.2–1.3s) |
| `stock_zh_a_hist` / `stock_individual_info_em` | `RemoteDisconnected` |
| Watchlist size | 39 symbols; full `update_stock_data` × 6-retry EM ≈ minutes–hours |

---

## Plan amendments (from critical review 2026-07-31)

Do not re-open product decisions; these are **executor constraints** that fix plan gaps:

1. **Half-open recovery (mandatory):** Pure “open until success” never recovers if all callers skip EM while open. Implement time-based half-open: after `open_cooldown_sec` (default **60**), allow **one** probe call (`should_skip_eastmoney()` returns False once / `allow_probe()`). Success → close; disconnect failure → reopen and reset cooldown. Add tests for half-open.
2. **Circuit scope ≠ all eastmoney.com hosts:** Circuit gates akshare/push-style paths that `RemoteDisconnected` (hist, individual_info, fund_flow, spot_em used as heavy fallback). **CompanySurvey** (`emweb.securities.eastmoney.com`) stayed healthy in probes — keep it as profile fallback even when circuit is open. Do not short-circuit Survey solely because the circuit is open.
3. **Thread-safe circuit state:** Scans use thread pools. Protect fail count / open flag / half-open probe with the same style of lock as the throttle (`threading.Lock`).
4. **Light refresh still dangerous:** `fetch_realtime_quote` falls back to `ak.stock_zh_a_spot_em` + `_retry`×6 if Sina fails — one bad symbol can re-introduce multi-minute stalls. For watchlist refresh path: if Sina fails, **do not** call full-market spot with 6 retries; fail that symbol soft (keep cache / empty) or at most **1** spot attempt and only when circuit closed. Prefer a `fetch_realtime_quote(symbol, *, heavy_fallback=False)` flag used by `refresh_all_data`.
5. **Right-side STAR is a behavior change:** Today right Layer-1 is `startswith(("60","00","30"))` — **688 was already excluded**. Including `688` while dropping ChiNext is intentional per user (“科创板保留”). Document in code comment; do not silently leave STAR excluded.
6. **Shared Layer-1 snapshot:** `unified_scanner._fetch_shared_market_df` still tries `ak.stock_zh_a_spot_em` first with no circuit. When circuit open (or after first disconnect), skip to东财直连 / 新浪分页 without long ak retries. Wire `record_*` on that path too.
7. **Fund-flow backfill:** `fetch_resilience.backfill_fund_flow` must not sleep 2s×N when circuit is open and every fetch is a guaranteed skip — if `should_skip_eastmoney()`, return early (0 repaired) or skip sleep when fetch was skipped.
8. **Task 2 test completeness:** Replace the `...` placeholder with an explicit `tmp_path` / monkeypatched `_symbol_dir` + `_save_daily_csv` so tests never write under `C:\reports\stock`.
9. **Sina OHLCV quality:** Unadjusted Sina fallback sets `adjust_source=sina_raw` / may mark `ml_safe=False` — acceptable under EM outage; do not “fix” by forcing fake qfq.

---

### Task 1: Circuit breaker API (TDD)

**Files:**
- Modify: `scripts/stock/eastmoney_throttle.py`
- Test: `tests/test_eastmoney_throttle.py` (extend) or create `tests/test_eastmoney_circuit.py`

**Step 1: Write failing tests**

```python
# tests/test_eastmoney_circuit.py
from __future__ import annotations
import os, sys
_STOCK = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "stock"))
if _STOCK not in sys.path:
    sys.path.insert(0, _STOCK)

import eastmoney_throttle as em

def setup_function(_fn=None):
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3)

def test_circuit_opens_after_threshold_remote_disconnects():
    err = ConnectionError("Remote end closed connection without response")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.is_eastmoney_circuit_open() is True

def test_circuit_ignores_unrelated_errors():
    em.record_eastmoney_failure(ValueError("bad payload"))
    em.record_eastmoney_failure(ValueError("bad payload"))
    em.record_eastmoney_failure(ValueError("bad payload"))
    assert em.is_eastmoney_circuit_open() is False

def test_success_resets_circuit():
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.is_eastmoney_circuit_open()
    em.record_eastmoney_success()
    assert em.is_eastmoney_circuit_open() is False

def test_should_skip_eastmoney_when_open():
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.should_skip_eastmoney() is True

def test_half_open_allows_probe_after_cooldown(monkeypatch):
    em.reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=10)
    err = ConnectionError("RemoteDisconnected")
    for _ in range(3):
        em.record_eastmoney_failure(err)
    assert em.should_skip_eastmoney() is True
    # pretend cooldown elapsed
    monkeypatch.setattr(em, "_circuit_opened_mono", __import__("time").monotonic() - 11)
    assert em.should_skip_eastmoney() is False  # one probe allowed
    assert em.should_skip_eastmoney() is True   # further calls skip until success/fail recorded
```

**Step 2: Run to verify fail**

Run: `pytest tests/test_eastmoney_circuit.py -v`  
Expected: FAIL (API missing) or ImportError.

**Step 3: Implement minimal circuit in `eastmoney_throttle.py`**

Add (names may match tests exactly):

- Module state: `_fail_count`, `_circuit_open`, `_failure_threshold` (default **3**), `_open_cooldown_sec` (default **60**), `_circuit_opened_mono`, `_half_open_probe_allowed`, protected by `threading.Lock`.
- `reset_circuit_for_tests(failure_threshold=3, open_cooldown_sec=60)` — clear open flag / count / probe; call from existing `reset_for_tests` so old tests stay isolated.
- `is_disconnect_error(exc) -> bool` — true if message/type contains `RemoteDisconnected`, `Connection aborted`, or `ConnectionResetError` / similar disconnects (keep list small and tested).
- `record_eastmoney_failure(exc)` — increment only when `is_disconnect_error`; open circuit at threshold; log once when opening; on failure during half-open probe, reopen.
- `record_eastmoney_success()` — reset count + close circuit.
- `is_eastmoney_circuit_open() -> bool`
- `should_skip_eastmoney() -> bool` — True when open **and** not granting a half-open probe (see amendment #1).

Do **not** change semaphore defaults here.

**Step 4: Run tests**

Run: `pytest tests/test_eastmoney_circuit.py tests/test_eastmoney_throttle.py -v`  
Expected: all PASS.

---

### Task 2: Fast-cut OHLCV + profile in `fetch_market_data.py`

**Files:**
- Modify: `scripts/stock/fetch_market_data.py`
- Test: `tests/test_fetch_em_circuit_wiring.py`

**Step 1: Failing tests (monkeypatch)**

```python
def test_ohlcv_skips_em_when_circuit_open(monkeypatch):
    import eastmoney_throttle as em
    import fetch_market_data as fmd
    em.reset_for_tests(max_concurrent=2, min_interval_sec=0.0)
    em.reset_circuit_for_tests(failure_threshold=3)
    for _ in range(3):
        em.record_eastmoney_failure(ConnectionError("RemoteDisconnected"))

    calls = {"ak": 0}
    def boom(*a, **k):
        calls["ak"] += 1
        raise AssertionError("should not call ak hist")
    monkeypatch.setattr(fmd, "_fetch_ohlcv_akshare", boom)

    sina_df = __import__("pandas").DataFrame({
        "日期": ["2026-07-30"], "开盘": [1.0], "收盘": [1.1], "最高": [1.2],
        "最低": [0.9], "成交量": [100], "成交额": [0.0], "振幅": [0.0],
        "涨跌幅": [1.0], "涨跌额": [0.1], "换手率": [0.0],
    })
    monkeypatch.setattr(fmd, "_fetch_ohlcv_sina", lambda *a, **k: sina_df)
    monkeypatch.setattr(fmd, "validate_and_persist", lambda *a, **k: {"passed": True})
    monkeypatch.setattr(fmd, "_symbol_dir", lambda sym: str(tmp_path / sym))
    monkeypatch.setattr(fmd, "_save_daily_csv", lambda df, sym: str(tmp_path / sym / "daily.csv"))
    df = fmd.fetch_daily_ohlcv("600519", start_date="20260701", end_date="20260731")
    assert calls["ak"] == 0
    assert len(df) == 1
```

(`tmp_path` from pytest.) Also test: when circuit closed, first disconnect records failure and remaining attempts for **that call** are capped at **2** (not 6) before Sina fallback.

**Step 2: Run — expect FAIL**

**Step 3: Implement**

In `fetch_daily_ohlcv`:
1. If `should_skip_eastmoney()`: skip akshare loop; go straight to existing Sina / cache-qfq path.
2. Else: max EM attempts = **2** (replace `_MAX_RETRIES` loop for hist only, or pass `retries=2`).
3. On each EM failure: `record_eastmoney_failure(e)`; on success: `record_eastmoney_success()`.
4. After attempts exhausted → existing Sina / qfq-cache fallback unchanged.

In `_fetch_profile_akshare` / `fetch_company_profile`:
1. If circuit open → skip akshare; use `_fetch_profile_em_survey` only (or try survey first when open).
2. Else: profile akshare retries ≤ **2**; on disconnect record failure; if empty/fail → CompanySurvey (already present).

Leave `fetch_stock_news` retries modest (news was OK in probe); still record success/failure if using EM, but do not block watchlist light refresh (Task 4).

**Step 4: pytest green**

---

### Task 3: Fund-flow path respects circuit

**Files:**
- Modify: `scripts/stock/china_market_data.py` — `fetch_stock_fund_flow` (~178–215)
- Test: extend `tests/test_eastmoney_circuit.py` or wiring test

**Behavior:**
1. If `should_skip_eastmoney()` at start → do not enter 6-attempt loop; return cache CSV if present else empty DataFrame.
2. While closed: keep throttle; on disconnect `record_eastmoney_failure`; **cap attempts at 2** when `is_disconnect_error` (optional: keep 6 for non-disconnect errors, or always 2 for scan speed — prefer **2 for disconnect-class**, 3 max otherwise).
3. On success: `record_eastmoney_success()`.

**Verify:** monkeypatch `ak.stock_individual_fund_flow` must not be called when circuit open; empty/cache path still works.

---

### Task 4: Watchlist「刷新列表」= Sina realtime only

**Files:**
- Modify: `scripts/stock/watchlist.py` — `refresh_all_data`
- Test: `tests/test_watchlist_refresh_light.py`

**Step 1: Failing test**

```python
def test_refresh_all_data_only_realtime(monkeypatch):
    import watchlist as wl
    monkeypatch.setattr(wl, "list_stocks", lambda: [{"symbol": "600519", "name": "茅台"}])
    calls = []
    monkeypatch.setattr(
        "fetch_market_data.fetch_realtime_quote",
        lambda sym: calls.append(("rt", sym)) or {"代码": sym, "最新价": 1.0},
    )
    def boom_update(sym):
        raise AssertionError("update_stock_data must not run")
    monkeypatch.setattr("fetch_market_data.update_stock_data", boom_update)
    results = wl.refresh_all_data()
    assert calls == [("rt", "600519")]
    assert results and results[0]["symbol"] == "600519"
```

**Step 2: Implement**

```python
def refresh_all_data() -> list[dict]:
    """Refresh watchlist realtime quotes only (Sina-first via fetch_realtime_quote).
    Full OHLCV/profile/news remains on data_prefetch / update_stock_data.
    """
    from fetch_market_data import fetch_realtime_quote
    stocks = list_stocks()
    results = []
    for s in stocks:
        sym = s["symbol"]
        log.info("刷新实时行情 %s (%s)...", sym, s.get("name", ""))
        summary = {"symbol": sym, "errors": []}
        try:
            # heavy_fallback=False: never pull full-market spot_em with long retries
            rt = fetch_realtime_quote(sym, heavy_fallback=False)
            summary["realtime"] = bool(rt)
        except Exception as e:
            summary["errors"].append(f"实时行情: {e}")
            summary["realtime"] = False
        results.append(summary)
    _backfill_watchlist_info()
    return results
```

Implement `fetch_realtime_quote(..., heavy_fallback: bool = True)` for backward compatibility; watchlist refresh passes `False` (amendment #4).

Confirm `data_prefetch.py` still calls `update_stock_data` (unchanged).

**Also (amendment #6/#7):** In the same PR/task batch or a short Task 4b — wire circuit into `unified_scanner._fetch_shared_market_df` and early-out `backfill_fund_flow` when circuit open.

**Step 3: pytest green**

---

### Task 5: Exclude ChiNext `300`/`301` from scanners (keep `688`)

**Files:**
- Prefer small helper: `scripts/stock/board_filters.py` (new) OR add to an existing tiny util
- Modify: `scripts/stock/scanner.py` — `_layer1_quick_filter` mask
- Modify: `scripts/stock/right_side_scanner.py` — Layer-1 `startswith(("60", "00", "30"))` and any ingest allow-list that admits `30*`
- Test: `tests/test_board_filters.py`

**Helper:**

```python
# scripts/stock/board_filters.py
CHINEXT_PREFIXES = ("300", "301")  # exclude from AI scan universe; keep 688/689

def is_chinext(symbol: str) -> bool:
    s = str(symbol or "").strip()
    return s.startswith(CHINEXT_PREFIXES)

def allow_in_ai_scan(symbol: str) -> bool:
    return not is_chinext(symbol)
```

**Left scanner:** after base mask (or as part of it), drop rows where `is_chinext(代码)`.

**Right scanner:** change Layer-1 board line from:

```python
& df["代码"].apply(lambda x: str(x).startswith(("60", "00", "30")))
```

to something that allows `60`/`00`/`688` (and existing Beijing codes if already allowed upstream) but **rejects** `300`/`301`. Example:

```python
def _board_ok(code: str) -> bool:
    c = str(code)
    if c.startswith(("300", "301")):
        return False
    return c.startswith(("60", "00", "688"))  # align with product: keep STAR; drop ChiNext
```

Update comment that currently says「主板或创业板」.

Also update `_fetch_market_eastmoney_direct` allow prefix tuple if it feeds candidates with `30` before Layer-1 — filtering at Layer-1 is enough if Layer-1 always runs; still safe to exclude `300`/`301` early when building rows.

**Do not** change midday_scanner unless unified path uses it for this UI; focus on left + right used by `unified_scanner.py`.

**Tests:**

```python
assert is_chinext("300750") and is_chinext("301001")
assert not is_chinext("688981") and not is_chinext("600519")
assert allow_in_ai_scan("688981") and not allow_in_ai_scan("300750")
```

Optional: unit-test right-side mask with a tiny DataFrame of codes.

---

### Task 6: Smoke + docs touch (minimal)

**Step 1: Unit suite**

```bash
pytest tests/test_eastmoney_circuit.py tests/test_eastmoney_throttle.py tests/test_fetch_em_circuit_wiring.py tests/test_watchlist_refresh_light.py tests/test_board_filters.py -v
```

Expected: all PASS.

**Step 2: Optional live smoke (manual, non-CI)**

```bash
cd scripts/stock
python -c "from eastmoney_throttle import should_skip_eastmoney, record_eastmoney_failure; ..."
# or call watchlist.refresh_all_data on 1–2 symbols and confirm seconds not minutes
```

**Step 3: Docs (only if usage text claims refresh does full update)**

- Check `docs/guides/stock-usage-guide.md` for「刷新列表」wording; if it says full OHLCV refresh, update one sentence: realtime only; full data via 数据预热.

---

## Verification Summary

- [x] Circuit opens after 3 disconnect-class failures; success closes it
- [x] Half-open after cooldown allows one probe; success closes / fail reopens
- [x] OHLCV/profile/fund-flow skip EM when open; capped retries when closed; Survey still allowed
- [x] `refresh_all_data` never calls `update_stock_data`; realtime uses `heavy_fallback=False`
- [x] Prefetch still uses `update_stock_data`
- [x] Shared market fetch / fund-flow backfill respect circuit (no long sleep storms)
- [x] Left + right Layer-1 exclude `300`/`301`, **include** `688` on right
- [x] Related pytest files green
- [x] Circuit counters are lock-protected
- [x] Half-open probe cannot be permanently leaked (backfill non-consuming; empty/non-disconnect resolve pending)
- [x] Standalone left/right Layer-1 fetches respect circuit
- [x] EM-direct early allow includes `689`

## Notes for executor

- Import style: `sys.path.insert` → `scripts/stock` like existing stock tests.
- Temp/debug scripts only under `tmp/`, never repo root.
- Do not commit unless user asks.
- After implementation: offer `requesting-code-review` per session rules.
