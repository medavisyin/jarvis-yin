# Memory: Daily Fetch topic_dedup Timeout

**Generated**: 2026-09-10 ~14:40 UTC+8
**Last updated**: 2026-09-10 ~14:40 UTC+8
**Project**: c:\jarvis
**Focus**: Continue failed on topic_dedup because filter_topics.py exceeded the 60s subprocess timeout

---

## Goal & Scope (required)

Unblock Daily Fetch Continue when `topic_dedup` reports `Command '['python', '...filter_topics.py', 'C:\\repo…'`. Root cause is a 60s timeout vs ~71s classify time, not a missing script.

---

## Key Decisions (required)

1. **Approach C approved**: speed up `TopicIndex.match_topic` AND raise timeout 60s → 180s AND show stderr/timeout in the UI instead of a truncated argv list. Then generate today's `briefing-data-filtered.json`.
2. **Rejected: timeout-only**: index will keep growing (~1661 topics today).
3. **Rejected: matching-speed-only with 60s timeout**: no safety margin.
4. **Execute directly** (no written plan). Memory file yes.
5. **Matching design**: cache normalized titles + keyword sets; O(1) exact-title map; SequenceMatcher only top ~100 keyword-overlap candidates; cap aliases at 8; early-exit if combined score ≥ 0.85.

---

## Confirmed Assumptions (required)

- User chose start-fresh for session memory load; Daily Fetch continue error is today's 2026-09-10 run.
- `briefing-data.json` exists; `briefing-data-filtered.json` does not.
- Continue still prints "Continue complete!" because a failed `topic_dedup` does not abort later steps.

---

## Key Discoveries (required)

- `sp.run(..., timeout=60)` in `scripts/rag/routes/daily_fetch.py` (two `filter_topics.py` call sites). `TimeoutExpired` is caught and `str(e)[:200]`, which truncates at `C:\\reports\\…` → UI shows `C:\\repo`.
- `topic-index.json`: 1661 topics, 2.15 MB, 2950 aliases (max 162 on a few mega-topics). `match_topic` SequenceMatcher's every topic × every alias per incoming item.
- Timing (2026-09-10, 45 items): load 0.02s, classify_all **71.4s**, slowest item 2.47s.

---

## Runtime Evidence (include when relevant)

- User UI: `Continue complete!` + `✘ topic_dedup — Command '['python', 'C:\\jarvis\\scripts\\pipeline\\filter_topics.py', 'C:\\repo`
- `python tmp/_debug_topic_dedup_timing.py`: classify_all_s=71.438

---

## Current State (required)

- **Working**: Matching speedup; 180s timeout; Continue + Recreate error formatting; newest-8 alias fuzzy match; today’s filtered JSON (37 kept / 8 stale).
- **Pending**: Follow-up code review of applied triage fixes; user Daily Fetch Continue (restart Jarvis for in-process timeout/error text).
- **Blocked**: none

---

## Next Steps (required)

1. [x] TDD: tests for candidate-capped matching, timeout constant, error formatting
2. [x] Implement match_topic speedup + 180s timeout + error formatting
3. [x] Run filter_topics on today's briefing-data.json
4. [ ] Click Daily Fetch Continue again (restart Jarvis first if you want the new timeout/error text)
5. [ ] Code review if user confirms

---

## Notes for Next Session (include when relevant)

- `tests/` is gitignored; keep a correctness case in `topic_index.py --test` as well.
- Do not treat "Continue complete!" as all steps succeeded — check per-step marks.

---

## References (required)

- `scripts/pipeline/topic_index.py` — matcher
- `scripts/pipeline/filter_topics.py` — CLI
- `scripts/rag/routes/daily_fetch.py` — timeout=60 call sites ~564 and ~797
- `C:/reports/ai/topic-index.json`
- `C:/reports/ai/2026-09-10/briefing-data.json`

---

**Confirmed at**: 2026-09-10 ~14:40 UTC+8
