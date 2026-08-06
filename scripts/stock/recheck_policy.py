"""Shared deep-analysis recheck policy for left/right scanners.



Aligns AI 推荐 picks with A股分析&AI预测:



Direction gate (both sides):

- 看空 → always veto

- 中性 with confidence >= threshold → veto

- 看多 / low-confidence 中性 → continue to empty-entry gate



Empty-position entry gate (empty_entry vs current price):

- now → pass (near-price buy zone still OK)

- wait_pullback → left soft-wait (keep pick as 等回调); right hard veto

- avoid → hard veto on both sides

- missing/invalid empty_entry → treat as now

"""



from __future__ import annotations



NEUTRAL_VETO_MIN_CONFIDENCE = 60



EMPTY_ENTRY_NOW = "now"

EMPTY_ENTRY_WAIT = "wait_pullback"

EMPTY_ENTRY_AVOID = "avoid"

_VALID_EMPTY_ENTRIES = frozenset(

    {EMPTY_ENTRY_NOW, EMPTY_ENTRY_WAIT, EMPTY_ENTRY_AVOID}

)



ACTION_PASS = "pass"

ACTION_SOFT_WAIT = "soft_wait"

ACTION_VETO = "veto"





def should_veto_recheck(

    verdict: dict | None,

    *,

    neutral_min_confidence: int = NEUTRAL_VETO_MIN_CONFIDENCE,

) -> tuple[bool, str]:

    """Return (should_veto, reason) from generate_prediction_verdict output."""

    if not verdict or not verdict.get("ok"):

        return False, ""



    direction = str(verdict.get("direction") or "").strip()

    try:

        confidence = float(verdict.get("confidence") or 0)

    except (TypeError, ValueError):

        confidence = 0.0



    if direction == "看空":

        return True, str(

            verdict.get("veto_reason") or verdict.get("reason") or "深度分析判空"

        )



    if direction == "中性" and confidence >= neutral_min_confidence:

        reason = str(verdict.get("reason") or "").strip()

        if not reason:

            reason = f"深度分析中性(置信度{confidence:.0f})"

        elif "中性" not in reason:

            reason = f"深度分析中性: {reason}"

        return True, reason



    return False, ""





def normalize_empty_entry(verdict: dict | None) -> str:

    """Map verdict.empty_entry to now|wait_pullback|avoid; invalid → now."""

    if not verdict:

        return EMPTY_ENTRY_NOW

    raw = str(verdict.get("empty_entry") or "").strip().lower()

    if raw in _VALID_EMPTY_ENTRIES:

        return raw

    # tolerate common LLM variants

    if raw in ("wait", "pullback", "callback", "等回调", "回调"):

        return EMPTY_ENTRY_WAIT

    if raw in ("no", "none", "skip", "回避", "不宜"):

        return EMPTY_ENTRY_AVOID

    if raw in ("buy", "buy_now", "enter", "现价", "可买"):

        return EMPTY_ENTRY_NOW

    return EMPTY_ENTRY_NOW





def coerce_confidence(raw, default: int = 50) -> int:

    """Parse verdict confidence; None/invalid → default (never raise)."""

    if raw is None or raw == "":

        return int(default)

    try:

        return int(float(raw))

    except (TypeError, ValueError):

        return int(default)





def classify_recheck_action(

    verdict: dict | None,

    *,

    side: str,

    neutral_min_confidence: int = NEUTRAL_VETO_MIN_CONFIDENCE,

) -> tuple[str, str]:

    """Return (pass|soft_wait|veto, reason) for left/right scanners."""

    side_norm = (side or "left").strip().lower()

    if side_norm not in ("left", "right"):

        side_norm = "left"



    veto, reason = should_veto_recheck(

        verdict, neutral_min_confidence=neutral_min_confidence

    )

    if veto:

        return ACTION_VETO, reason



    if not verdict or not verdict.get("ok"):

        return ACTION_PASS, ""



    entry = normalize_empty_entry(verdict)

    note = str(

        verdict.get("entry_note") or verdict.get("reason") or ""

    ).strip()



    if entry == EMPTY_ENTRY_AVOID:

        return ACTION_VETO, note or "深度空仓建议：现阶段不宜建仓"



    if entry == EMPTY_ENTRY_WAIT:

        reason_wait = note or "深度空仓建议：不追现价，等回调"

        if side_norm == "right":

            return ACTION_VETO, reason_wait

        return ACTION_SOFT_WAIT, reason_wait



    return ACTION_PASS, ""





def _safe_float(val) -> float | None:

    if val is None or val == "":

        return None

    try:

        return float(val)

    except (TypeError, ValueError):

        return None





def _pullback_range_usable(verdict: dict | None, pick: dict) -> tuple[float, float] | None:

    """Return (low, high) only when pullback is at/below current price."""

    if not verdict:

        return None

    low = _safe_float(verdict.get("pullback_low"))

    high = _safe_float(verdict.get("pullback_high"))

    if low is None or high is None:

        return None

    if low > high:

        low, high = high, low

    price = _safe_float(pick.get("price"))

    # Invalid unless the whole pullback band is at/below spot
    if price is not None and (low > price or high > price):

        return None

    return round(low, 2), round(high, 2)





def _apply_veto_mutation(

    pick: dict,

    verdict: dict | None,

    reason: str,

    *,

    score_cap: int | float,

) -> None:

    pick["deepseek_verdict"] = verdict

    pick["verdict"] = "观望"

    try:

        cur = float(pick.get("final_score") or 0)

    except (TypeError, ValueError):

        cur = 0.0

    pick["final_score"] = min(cur, float(score_cap))

    orig = pick.get("reasoning", "")

    pick["reasoning"] = (

        f"【深度复核否决：与深度分析方向冲突（{reason}）】"

        + (f"\n{orig}" if orig else "")

    )

    pick["recheck_vetoed"] = True

    pick.pop("recheck_wait_pullback", None)





def _apply_soft_wait_mutation(

    pick: dict,

    verdict: dict | None,

    reason: str,

) -> None:

    pick["deepseek_verdict"] = verdict

    pick["verdict"] = "等回调"

    pick["recheck_wait_pullback"] = True

    pick.pop("recheck_vetoed", None)



    rng = _pullback_range_usable(verdict, pick)

    if rng is not None:

        pick["buy_low"], pick["buy_high"] = rng



    note = reason or "深度空仓建议等回调，非现价追入"

    orig = pick.get("reasoning", "")

    pick["reasoning"] = (

        f"【深度复核·等回调：{note}】" + (f"\n{orig}" if orig else "")

    )

    strat = str(pick.get("strategy") or "").strip()

    prefix = f"【深度优先·等回调建仓】{note}。"

    if rng is not None:

        prefix += f"回调区间 ¥{rng[0]:.2f}~¥{rng[1]:.2f}。"

    else:

        prefix += "回调区间待确认。"

    pick["strategy"] = prefix + (f" {strat}" if strat else "")





def apply_recheck_action(

    pick: dict,

    verdict: dict | None,

    *,

    side: str,

    score_cap: int | float,

    neutral_min_confidence: int = NEUTRAL_VETO_MIN_CONFIDENCE,

) -> str:

    """Mutate pick per side-aware policy. Returns pass|soft_wait|veto."""

    action, reason = classify_recheck_action(

        verdict,

        side=side,

        neutral_min_confidence=neutral_min_confidence,

    )

    if action == ACTION_VETO:

        _apply_veto_mutation(pick, verdict, reason, score_cap=score_cap)

        return ACTION_VETO

    if action == ACTION_SOFT_WAIT:

        _apply_soft_wait_mutation(pick, verdict, reason)

        return ACTION_SOFT_WAIT

    return ACTION_PASS





def apply_recheck_veto(

    pick: dict,

    verdict: dict | None,

    *,

    score_cap: int | float,

    neutral_min_confidence: int = NEUTRAL_VETO_MIN_CONFIDENCE,

) -> bool:

    """Mutate pick if direction recheck says veto. Returns True when veto applied.



    Legacy helper (direction-only). Prefer apply_recheck_action for entry timing.

    """

    veto, reason = should_veto_recheck(

        verdict, neutral_min_confidence=neutral_min_confidence

    )

    if not veto:

        return False



    _apply_veto_mutation(pick, verdict, reason, score_cap=score_cap)

    return True


