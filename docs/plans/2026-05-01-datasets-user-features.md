# Datasets User-Facing Features Plan

> **For the implementing agent:** Four user-facing features that leverage the HF datasets integration to improve the search experience.

**Goal:** Add visible, user-facing value from the datasets integration into both Search UI (port 18888) and Agent chat (port 18889).

**Architecture:** All features use existing APIs + new lightweight endpoints. No framework changes — vanilla JS inline in templates.

**Tech Stack:** Flask (existing), vanilla JS (existing), `dataset_adapter.py`, `eval_metrics.py`

---

## Status

| Feature | Status | Target UI |
|---------|:------:|-----------|
| A. Search Quality Confidence Indicator | Done | Both |
| B. Similar Questions Suggestions | Done | Both |
| C. Data Explorer Page | Done | Search UI (merged into "Knowledge Explorer" tab) |
| D. Query Feedback Loop | Done | Both |

---

## Feature A: Search Quality Confidence Indicator

**What users see:** A colored badge next to each search result showing confidence level (High/Medium/Low) based on similarity score distribution.

**Backend:**
- Endpoint: `GET /api/search` already returns `score` per result + `pipeline.stages`
- New: Add `confidence` field to each result and overall `query_confidence` to response
- Logic: Per-result: score >= 0.55 = High, >= 0.35 = Medium, else Low
- Query-level: top score >= 0.55 AND avg >= 0.35 = High, top >= 0.35 = Medium, else Low

**Frontend changes:**
- Search UI (`search_ui.py` HTML_TEMPLATE): Add confidence badge in result card
- Agent (`templates/index.html`): Show confidence in the sources section after answer

**Files:**
- Modify: `scripts/rag/search_ui.py` (API response + HTML template)
- Modify: `scripts/rag/templates/index.html` (agent sources display)

---

## Feature B: Similar Questions Suggestions

**What users see:** When search returns low confidence or few results, suggest related queries that might work better.

**Backend:**
- New endpoint: `GET /api/suggest?query=...` 
- Logic: Embed the query, find nearest eval dataset queries OR find titles of top chunks and extract question-like phrases
- Fallback: Use BM25 against chunk titles to suggest related topics

**Frontend changes:**
- Search UI: Show "Try also:" suggestions below search bar on low confidence
- Agent: Include suggestions in the SSE stream when RAG confidence is low

**Files:**
- Modify: `scripts/rag/search_ui.py` (new endpoint + frontend)
- Modify: `scripts/rag/rag_engine.py` (suggestion logic)
- Modify: `scripts/rag/templates/index.html` (display suggestions)

---

## Feature C: Data Explorer Page

**What users see:** A new "Explorer" tab in Search UI showing visual overview of all indexed knowledge — chunk counts by source, item type, date range, with interactive filters.

**Backend:**
- Endpoint: `GET /api/chunk-analysis` already exists (returns source/type counts)
- New: `GET /api/explorer-stats` — enhanced stats with date distribution, top titles
- Uses: `dataset_adapter.py` for structured access

**Frontend changes:**
- Search UI: Add 4th tab "Explorer" with charts/stats display
- Visual: Bar charts (CSS-only), clickable filters, date range

**Files:**
- Modify: `scripts/rag/search_ui.py` (new endpoint + 4th tab HTML/JS)

---

## Feature D: Query Feedback Loop

**What users see:** After search results, a "Was this helpful?" prompt. Over time, feedback auto-generates eval examples.

**Backend:**
- `POST /api/feedback` already exists with thumbs up/down
- New: Map positive feedback (expand + copy + view_doc) to eval dataset candidates
- New endpoint: `POST /api/feedback/eval-candidate` — mark a query+result as ground truth

**Frontend changes:**
- Search UI: Add explicit "Did you find what you needed?" after results
- Agent: Add feedback buttons after RAG-sourced answers

**Files:**
- Modify: `scripts/rag/search_ui.py` (feedback UI)
- Modify: `scripts/rag/feedback_store.py` (eval candidate generation)
- Modify: `scripts/rag/templates/index.html` (agent feedback)

---

## Implementation Order

1. **Feature A** (Confidence Indicator) — quickest, most visible, foundation for B
2. **Feature C** (Data Explorer) — standalone tab, no dependencies
3. **Feature B** (Similar Questions) — uses confidence from A
4. **Feature D** (Feedback Loop) — builds on all above
