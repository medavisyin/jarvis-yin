# Memory: Reading UX Polish

**Generated**: 2026-09-15
**Last updated**: 2026-09-15 (follow-up: Explain panel flips above near viewport bottom)
**Project**: c:\jarvis
**Focus**: Reading Explain: save to My Notes; TTS clip; panel placement near page bottom

---

## Goal & Scope (required)

Follow-up on Reading Explain after Focus/TTS/legend already shipped.

In scope:
1. **Save to My Notes** — add a button on the Explain popover; persist selected word/phrase + explanation + book/chapter via existing `POST /api/notes`.
2. **TTS leading clip** — Edge TTS path is used (`生成语音…` then audio), but words are truncated at the start (e.g. `congressman` → only `man`), even at 慢.

Out of scope: rewriting My Notes / Chat save-note; replacing the TTS engine; changing 慢/中/快.

---

## Key Decisions (required)

1. **Process**: Design first (brainstorming), then implement after approval — not “just do it” and not advice-only.
2. **Reading pain**: All of typography, chrome distraction, navigation rhythm, and missing Passage overlays; **prioritize immersion mode + typography**.
3. **Analysis colors**: Existing multi-color treatment (headings / quotes / highlights) is unexplained and fatiguing — add a legend and reduce noise (not “Passage overlays only”, not merely theme contrast).
4. **Scrollbars**: Overlay/auto-hide thin bars (hover or scroll to reveal), not a full-app restyle as the primary ask.
5. **Memory**: User asked to write `docs/memory/memory-20260915-reading-ux-polish.md` at clarification complete.
6. **Approach C (approved)**: Kindle-like Focus layer (not a separate app); Edge TTS for Explain; Analysis 3-style legend; overlay thin scrollbars (not wrapping every panel in ScrollArea).
7. **Architecture (approved 2026-09-15)**: Focus hides sidebar + minimal chrome; Analysis is a right drawer (closed by default); Explain speak = POST `/api/intensive-reading/speak` Edge TTS of the **selection only**, rate ~`-20%`, fallback `speechSynthesis`; Analysis styles = heading weight / quote left-border / one warm highlight + legend; Passage overlays deferred.
8. **UI (approved)**: Focus toolbar = exit, title, progress, font 18/20/22, Analysis toggle; Esc exits; prefs in `jarvis-reading-prefs`; Analysis drawer ~28rem, closed each Focus entry; Explain 慢/中/快 default 慢; overlay 6px scrollbars via CSS not ScrollArea wrap.
9. **Data flow (approved)**: Edge rates slow=-25% / medium=-10% / fast=+0%; browser fallback 0.68 / 0.82 / 0.95; voice from Settings `audio_voice_en`; analysis reuses chat markdown + `.reading-analysis` CSS; no prompt/cache format change.
10. **Next step (prior round)**: Execute directly in this session (no written plan).
11. **Follow-up 2026-09-15**: User confirmed Explain → My Notes saves **selected text + explanation + book/chapter**; TTS symptom is Edge path (`生成语音…`) then incomplete playback, not the `改用系统朗读` fallback.
12. **Process this follow-up**: clarify confirmed; user asked to update this memory file and trigger `brainstorming`.
13. **Rejected: diagnose TTS first**: User chose skip `systematic-debugging` and design a padding workaround.
14. **Approved design (2026-09-15)**: 「加入笔记」inside Explain panel; each save is a new `POST /api/notes`; TTS prepend ~500ms ffmpeg silence (text `. ` pause if no ffmpeg). Execute directly, no written plan.
15. **Explain panel placement (2026-09-15)**: Restore old `irPlaceFixedNearRect` behavior. Measure real panel height; prefer below the selection; if it would overflow the viewport bottom, flip above the word; ResizeObserver re-runs as streamed content grows. User approved this approach.

---

## Confirmed Assumptions (required)

- Work is the React SPA (`web/`), not the old `index.html` fallback as the product surface.
- Keep selection Explain, Analysis cache, Generate/Continue.
- Explain TTS today lives in `web/src/features/reading/ExplainPopover.tsx` (`SpeechSynthesisUtterance`, `lang=en-US`, `rate=0.92`).
- Analysis panel today in SPA is largely `whitespace-pre-wrap` of cached text; color treatment may come from markdown-ish model output or remaining HTML styling — inspect live before implementing.
- Passage already uses Literata ~18px / 1.72 / `max-width: 38em` and theme tokens (`Day` / `Night` / `Reading`).
- My Notes already exists: `POST /api/notes` in `scripts/rag/agent.py`; News `NotesPanel`; Chat “Save note”.
- Explain currently passes `bookId` + `chunk?.title` only — chunk index is on `ReadingPage` and must be added if notes include 章节.

---

## Constraints & Non-Goals (include when relevant)

- Do not rewrite intensive-reading backend prompts unless needed for Analysis color semantics.
- Do not change book upload, chunking, or analysis persistence contract unless the chosen design requires it.
- Mobile pack / Android reader is out of scope.

---

## Key Discoveries (required)

- `ReadingPage` split: Passage (`reading-passage`) + Analysis tabs; Explain via `ExplainPopover`.
- Explain speak uses Web Speech API only — no Edge TTS, no rate slider, no voice picker, toggle-cancel if already speaking.
- Analysis body is `whitespace-pre-wrap` of `active.text` (no markdown renderer in SPA as of 2026-09-15). If the user still sees colors, they may be from markdown markers, a live theme, or a different surface — verify in the browser before locking the legend design.
- Project already has Edge TTS for daily-fetch / knowledge audio (`edge_tts`) — a candidate for clearer Explain audio if we accept latency vs in-browser TTS.
- shadcn `ScrollArea` exists (`web/src/components/ui/scroll-area.tsx`) but Reading uses native `overflow-y-auto`.
- SPA Explain panel had been using `Math.min(btn.bottom + 8, innerHeight - 200)`, which never flipped above the word. Old HTML used `irPlaceFixedNearRect` (measure `offsetHeight`, flip if `top + h > vh - pad`).
- Live check on Vite `:5173`: bottom selection (`top≈1379` in `vh=1545`) placed the panel above (`popBottom=1371`); after content grew 110→150px it shifted up and stayed above. Top selection stayed below.

---

## Current State (required)

- **Working**: Focus mode; Explain Edge TTS + 慢/中/快; Analysis markdown + legend; overlay scrollbars; 「加入笔记」to My Notes; speak prepends 500ms silence; Explain panel/button flip above when the viewport bottom is short.
- **Pending**: None for placement (Minor-1/3/4 deferred).
- **Blocked**: None.

---

## Next Steps (required)

1. [x] RED tests for `formatExplainNote` and speak silence pad.
2. [x] Implement ExplainPopover button + `speak.py` pad.
3. [x] Browser-verify: save note in My Notes; live speak MP3 starts with silence.
4. [x] Restore Explain panel flip-above via `placeFixedNearRect` + ResizeObserver.
5. [x] Placement review: Minor-2 clamp assertion; Minor-1/3/4 deferred; follow-up review zero issues.

---

## Notes for Next Session (include when relevant)

- User language: Chinese.
- Question channel this session: `AskQuestion`.

---

## References (required)

- `web/src/pages/ReadingPage.tsx` — Reading layout, Passage + Analysis
- `web/src/features/reading/ExplainPopover.tsx` — selection explain + TTS + `useNearRect`
- `web/src/lib/placeFixedNearRect.ts` — viewport flip-above placement
- `web/src/lib/placeFixedNearRect.test.ts` — below / flip-up / clamp cases
- `web/src/index.css` — `.reading-passage`, Literata, theme tokens
- `web/src/components/ui/scroll-area.tsx` — unused by Reading today
- `web/src/lib/readingPrefs.ts` — font size / focus prefs
- `web/src/lib/speakRate.ts` — Edge and browser rate maps
- `web/src/lib/analysisMarkdown.ts` — legend + analysis HTML
- `web/src/lib/readingFocus.tsx` — Focus context for AppShell
- `scripts/rag/intensive_reading/speak.py` — validate + synthesize
- `POST /api/intensive-reading/speak` — Edge TTS mp3
- `POST /api/notes` — My Notes create (`scripts/rag/agent.py`)
- `web/src/features/news/NotesPanel.tsx` — My Notes UI
- `tests/test_intensive_reading_speak.py` — local pytest (gitignored tests/)

---

**Confirmed at**: 2026-09-15
