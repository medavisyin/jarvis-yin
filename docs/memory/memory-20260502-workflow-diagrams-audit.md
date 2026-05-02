# Memory: Workflow Diagrams Audit & Documentation Update

**Generated**: 2026-05-02 10:30
**Last updated**: 2026-05-02 10:30
**Project**: c:\jarvis
**Focus**: Audit and fix workflow diagram coverage across all Jarvis implementation docs

---

## Goal & Scope (required)

User asked about the "deep dive" feature in learning-guide daily_fetch. This expanded into:
1. Explaining the deep dive feature end-to-end
2. Updating the deep-dive-notes-impl.md with current code references
3. Auditing all 51 implementation docs for workflow diagram coverage
4. Adding workflow diagrams to 15 docs that were missing them
5. Creating a master workflow overview doc

---

## Key Decisions (required)

1. **Deep Dive vs Explain This distinction**: Documented as separate features. Deep Dive = dedicated session with fetched content + tutor prompt. Explain This = one-shot prompt in current chat with optional web search.
2. **Usage-tool stubs upgraded to full docs**: The 3 usage-tool stubs (rag-agent, search-ui, reindex-all) were upgraded from redirect stubs to proper implementation docs with user-facing workflow diagrams. They complement the rag/ canonical docs (backend-focused).
3. **Workflow overview as reading entry point**: Created `workflow-overview.md` as the new step 1 in the reading order, before `tech-stack-overview.md`.
4. **ASCII box style for diagrams**: Used consistent ASCII box art style (┌─┐│└─┘▼▶) matching the existing deep-dive-notes-impl.md and other docs.

---

## Confirmed Assumptions (required)

- All implementation docs should have workflow/architecture diagrams
- The workflow overview should be a top-level routing document connecting all features
- Usage-tool docs should be standalone (not stubs) with user-facing perspective

---

## Key Discoveries (required)

- Code was significantly refactored since docs were written: deep dive code moved from `agent.py` (lines 1449-3018) to `routes/toolbar.py` (194-256), `router.py` (35-83), `prompts.py` (275-289), `intent.py` (50, 246)
- 39/51 docs already had diagrams (76% coverage before this session)
- 3 usage-tool docs were stubs with just links to canonical docs
- `rag/learning-features-impl.md` has TOC numbering drift (says 1-11 but §12 AWS exists)
- `usage-tool/reindex-all-impl.md` had CLI flag mismatches with canonical doc

---

## Current State (required)

- **Working**: All 51+ implementation docs now have workflow diagrams
- **Working**: Master workflow overview (`workflow-overview.md`) created and linked from README
- **Working**: deep-dive-notes-impl.md fully updated with current code references
- **Pending**: None
- **Blocked**: None

---

## Next Steps (required)

1. [ ] Consider fixing the learning-features-impl.md TOC numbering drift
2. [ ] Verify usage-tool/reindex-all CLI flags stay in sync with rag/reindex-all canonical doc

---

## References (required)

- `docs/implementation/workflow-overview.md` — new master workflow overview
- `docs/implementation/README.md` — updated reading order and stub descriptions
- `docs/implementation/learning/deep-dive-notes-impl.md` — fully rewritten with current references
- `docs/implementation/rag/` — 6 docs got diagrams added
- `docs/implementation/stock/` — 2 docs got diagrams added
- `docs/implementation/briefing-pipeline/` — 3 docs got diagrams added
- `docs/implementation/tech-stack-overview.md` — diagram added
- `docs/implementation/usage-tool/` — 3 stubs upgraded to full docs

---

**Confirmed at**: 2026-05-02 10:30
