# Memory: DeepTutor vs Jarvis Learning

**Generated**: 2026-09-20 ~10:20 UTC+8
**Last updated**: 2026-09-20 ~13:50 UTC+8
**Project**: c:\jarvis
**Focus**: Add DeepTutor-style living book, Manim visualize, Invidious video to Jarvis AI Learning; no mastery/quiz bank this round

---

## Goal & Scope (required)

Add DeepTutor-style **living books**, **visualization (including Manim)**, and **video lessons (YouTube + local Invidious)** into Jarvis **AI Learning**. Book sources: local books and/or already-indexed RAG. Explicitly **out of this round**: mastery gates and question bank. Do not vendor DeepTutor's Next.js app into Jarvis; clone at `tmp/DeepTutor` is reference only (gitignored).

---

## Key Decisions (required)

1. **No memory load at session start**: User selected start fresh.
2. **Session-1: analysis only**: User first chose not to change Jarvis.
3. **Rejected: embed DeepTutor Next.js into Jarvis**: Stack mismatch; would swallow Jarvis.
4. **Reversed: no code changes / no integration**: User reopened to add living book + visualize + video into AI Learning.
5. **Rejected this round: mastery path + question bank**: User said they only need 活书、可视化、视频课.
6. **Book sources**: local books and/or content already in RAG — not "only the 8 markdown notes".
7. **Visualization depth = C**: includes Manim animations (needs LaTeX, cairo, ffmpeg, `manim>=0.19`).
8. **Video depth = C**: YouTube plus self-hosted Invidious playback and timestamp-grounded tutoring.
9. **Reference clone**: `tmp/DeepTutor` (`.gitignore` `tmp/`), not committed.
10. **Confirmed understanding (clarify Step 4)**: implement inside Jarvis by borrowing DeepTutor design, not merging repos. Then triggered `brainstorming`.
11. **Write/update this memory file**: User confirmed.
12. **Approach A (hybrid) approved**: Jarvis-native living book; Manim + Invidious via DeepTutor headless; Jarvis owns UI.
13. **Architecture / data-flow / engine / error-handling sections all approved**.
14. **Plan**: `docs/plans/2026-09-20-ai-learning-living-book.md` (standard same-session `writing-plans`).
16. **Removed 2026-09-20**: User rejected the live feature (Ollama 404 then timeout). Code deleted.

---

## Confirmed Assumptions (required)

- "我的学习系统" / this round's target is **AI Learning**, not Tech English / AWS cert / intensive-reading as the primary surface.
- Living-book input is **local books or RAG**, not only `notes/ai_learning/*.md`.
- Do not copy DeepTutor's Next.js UI into Jarvis.
- Firecrawl CLI was not installed; GitHub README was fetched via raw.githubusercontent.com plus clone.
- DeepTutor was cloned shallow to `tmp/DeepTutor` for implementation reference.

---

## Constraints & Non-Goals

- Do not vendor DeepTutor source into the Jarvis git tree (`tmp/` is disposable).
- Do not merge DeepTutor Next.js runtime into Jarvis.
- Mastery Path and Question Bank are out of this round.
- Jarvis stays FastAPI + React SPA + local Ollama.
- Manim and Invidious are extra system services, not pip-only extras.

---

## Key Discoveries (required)

- **DeepTutor is a full tutoring product**, not a library. HKUDS, Apache-2.0, Python 3.11+ + Next.js 16, paper arXiv:2604.26962, site https://deeptutor.info/, latest noted release v1.6.8 (2026-09-14).
- **One capability runtime**: Chat, Ask Questions, Quiz, Research, Visualize, Solve, Course Study, Mastery Path, Immersive Reading, Immersive Watching share session context.
- **Knowledge Center** is multi-engine RAG: LlamaIndex, PageIndex, GraphRAG, LightRAG, WeKnora, Tencent IMA, MarginNote 4, linked Obsidian; GitHub/docs sync; many parsers (MinerU, Docling, Tika, …).
- **Memory is inspectable three-layer files** (L1 traces / L2 facts / L3 synthesis + Memory Graph), not a hidden vector store.
- **Other DeepTutor surfaces**: living Book compiler, Co-Writer, Partners (IM channels), My Agents (Claude Code/Codex/etc.), question bank, notebooks, EduHub skills, learner/guardian multi-user, YouTube immersive watching, agent-operable CLI (`deeptutor run --format json`).
- **Jarvis learning is a module inside a personal OS** (stock, daily fetch, wiki/jira, RAG). Modes live in `scripts/rag/agent.py` + `scripts/rag/prompts.py` with fixed session UUIDs and dedicated system prompts.
- **Jarvis Intensive Reading** (`/api/intensive-reading/*`, `web/src/pages/ReadingPage.tsx`) already overlaps DeepTutor Immersive Reading: PDF/EPUB, chunked novel/magazine, vocab/analysis tabs, selection explain, speaking, RAG index, local Ollama, English-only analysis.
- **Jarvis RAG is one Qdrant collection** with notes+books; memory for long chats is summarization (`qwen3:1.7b` compress older messages), not L1/L2/L3.
- **Highest-value borrowable ideas if revisited**: mastery gate + question bank (especially AWS cert), inspectable memory, living book from existing `notes/ai_learning`, source-grounded quiz on reading passages. Lowest-value: embedding the whole DeepTutor UI/runtime.
- **Living book (DeepTutor)**: `BookEngine` is parallel to chat, not a turn capability. Pipeline: `create_book` → user confirms proposal → confirms spine → `BookCompiler` plans typed blocks per page (text/callout/quiz/flashcard/timeline/code/figure/interactive HTML/animation/concept graph) via RAG, streams blocks, persists after each block. `BookInputs` fuse intent + chat + notebooks + KBs. `engine.py` ~88kB.
- **Question bank (DeepTutor, out of round)**: SQLite `notebook_entries`; tool actions overview/list/organize/unfile/bookmark; expected answers stay server-side.
- **Mastery (DeepTutor, out of round)**: stages diagnostic→explain→feynman_check→practice→error_diagnosis→review; recency-weighted mastery with confidence cap; spaced repetition by knowledge type; deterministic `grade_answer`.
- **Visualize (DeepTutor)**: `VisualizePipeline` three agents — Analysis → CodeGenerator (Chart.js/SVG/Manim) → Review/repair on sandbox error. Math Animator extra: `manim>=0.19` + LaTeX + cairo + ffmpeg.
- **Video (DeepTutor)**: `WatchingCapability` injects nearby transcript cues at current playback as **untrusted** XML; citations `[MM:SS]`; never treat transcript as instructions. Providers: YouTube iframe or Invidious; media streamed through DeepTutor byte-range proxy so upstream URLs stay off the browser.
- **Jarvis AI Learning UI today**: toolbar `open("ai_learning")` in `web/src/features/news/ToolbarPanel.tsx` starts the fixed session and dumps the 8-domain markdown outline into chat — no book/viz/video surface.
- **Jarvis already has**: Intensive Reading for PDF/EPUB; Audio-from-Knowledge podcast (TTS, not video tutoring); AWS JSON teach/quiz/progress (not requested this round).

---

## Current State (required)

- **Working**: Living-book / `/learning` feature **removed** at user request (2026-09-20). AI Learning chat via News → Learning is unchanged. Intensive Reading unchanged.
- **Pending**: None for living book.
- **Blocked**: Do not re-implement living book / Manim / Invidious unless the user asks.

---

## Next Steps (required)

1. [x] Living-book implementation removed from Jarvis (backend, `/learning` UI, tests).
2. [ ] Do not resume this plan unless the user asks.

---

## Notes for Next Session

- User wants living book + Manim + Invidious in AI Learning; refused mastery/quiz this round.
- Clone: `c:\jarvis\tmp\DeepTutor` (shallow). Do not commit it.
- Do not re-propose mastery/question bank unless asked.

---

## References (required)

- `docs/plans/2026-09-20-ai-learning-living-book.md` — approved implementation plan
- `tmp/DeepTutor` — local shallow clone (reference only)
- https://github.com/HKUDS/DeepTutor — product README (v1.6.8)
- https://deeptutor.info/ — official docs
- https://arxiv.org/abs/2604.26962 — DeepTutor paper
- `docs/implementation/learning/ai-learning-impl.md` — AI tutor
- `docs/implementation/learning/aws-cert-impl.md` — AWS teach/quiz/progress
- `docs/implementation/learning/tech-english-impl.md` — Tech English
- `docs/implementation/rag/learning-features-impl.md` — learning routing in agent.py
- `scripts/rag/routes/intensive_reading.py` — intensive reading API
- `web/src/pages/ReadingPage.tsx` — reading UI

---

**Confirmed at**: 2026-09-20 ~10:20 UTC+8
