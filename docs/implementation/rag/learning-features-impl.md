# Learning Features — Implementation Guide

> **Purpose:** Per-feature reference for modifying Jarvis learning features.
> Each section covers: what it does, where the code lives, how to change it.
>
> **Main file:** `scripts/rag/agent.py` (all learning logic is in this single file)

---

## Table of Contents

1. [Session Management](#1-session-management)
2. [System Prompts](#2-system-prompts)
3. [Welcome Messages](#3-welcome-messages)
4. [Topic Resolution](#4-topic-resolution)
5. [Article Content Fetching](#5-article-content-fetching)
6. [Web Search References](#6-web-search-references)
7. [Topic Refresh](#7-topic-refresh)
8. [Summarization Memory](#8-summarization-memory)
9. [Context Window & Token Limits](#9-context-window--token-limits)
10. [Continue Button](#10-continue-button)
11. [Learning Notes](#11-learning-notes)

---

## 1. Session Management

### What it does
Four fixed-ID sessions. AI Learning and AWS AIF-C01 are persistent (keep history). Tech English and Casual English start fresh each time (session cleared on open).

### Where the code lives

| Component | Location in `agent.py` | Search for |
|-----------|----------------------|------------|
| Session IDs | Python constant | `_LEARNING_SESSION_IDS` |
| Session detection | `api_agent()` | `if session_id == _LEARNING_SESSION_IDS` |
| Fresh-start logic | Client JS `_openLearning()` | `const freshStart =` |
| Clear endpoint | Flask route | `@app.route("/api/sessions/<session_id>/clear"` |

### How to modify

**To make AI Learning also start fresh:**
In the JS function `_openLearning()`, change:
```javascript
const freshStart = (type === 'english_learning' || type === 'casual_english');
```
to:
```javascript
const freshStart = true;  // all learning sessions start fresh
```

**To add a new learning mode:**
1. Add entry to `_LEARNING_SESSION_IDS` dict (use next UUID: `...000005`)
2. Create a new `SYSTEM_PROMPT_*` constant
3. Add `elif` branch in `api_agent()` to detect the session ID
4. Add a new `async function open*()` in the client JS
5. Add a toolbar button in the HTML

---

## 2. System Prompts

### What they do
Each learning mode has a system prompt that controls the LLM's teaching behavior. The prompt is injected as the first message in the conversation.

### Where the code lives

| Prompt | Search for |
|--------|------------|
| AI Learning | `SYSTEM_PROMPT_AI_LEARNING` |
| Tech English | `SYSTEM_PROMPT_ENGLISH_LEARNING` |
| Casual English | `SYSTEM_PROMPT_CASUAL_ENGLISH` |
| AWS AIF-C01 | `SYSTEM_PROMPT_AWS_CERT` |

### Current prompt designs

**AI Learning** — Fundamentals-first teaching:
```
1. FIRST: Explain the fundamental concept from zero
2. THEN: Go deeper — theory, algorithms, trade-offs
3. ONLY AFTER: Connect to the student's Jarvis project
```
Knowledge source priority: RAG → own knowledge → web references.

**Tech English** — Article analysis flow:
```
1. Brief summary of the article
2. Analyze: key phrases, pronunciation, presentation patterns
3. Show how a native speaker would present this
4. AFTER analysis: invite questions
```

**Casual English** — Article analysis flow:
```
1. Brief summary in everyday English
2. Analyze: casual phrases, idioms, vocabulary
3. Cultural context + example conversations
4. AFTER analysis: invite questions
```

**AWS AIF-C01** — Two independent modes:
```
TEACH mode: "teach me <topic>" or "teach Domain N"
  1. Present topic using study notes from knowledge/notes/aws_ai_p1/
  2. Structured lesson with concepts, examples, exam tips
  3. Track progress per domain

QUIZ mode: "quiz me on <topic>"
  1. Generate exam-style multiple-choice questions
  2. Evaluate answers, explain correct option
  3. Track quiz scores per domain
```

### How to modify

**To change teaching behavior:** Edit the system prompt string directly. The LLM follows the numbered instructions in order.

**To add quiz functionality back:** Add a step like `5. Quiz the student on vocabulary` to the prompt's numbered list.

**To change the student profile:** Edit the opening line (e.g., "Java developer in healthcare IT" → "Python developer in fintech").

---

## 3. Welcome Messages

### What they do
When a learning session opens, a welcome message is generated client-side showing available topics. Tech/Casual English show a clean topic list without instruction bullets.

### Where the code lives

| Mode | JS function | Search for |
|------|-------------|------------|
| AI Learning | `openAILearning()` | `async function openAILearning` |
| Tech English | `openEnglishLearning()` | `async function openEnglishLearning` |
| Casual English | `openCasualEnglish()` | `async function openCasualEnglish` |
| AWS AIF-C01 | `openAWSCert()` | `async function openAWSCert` |

### How to modify

**To change the welcome text:** Edit the `msg` string construction in the relevant function. Current format:
- Tech English: `"Pick a topic and I will analyze the article for you — highlighting key phrases..."`
- Casual English: `"Pick a topic and I will analyze the article for you — teaching everyday phrases..."`

**To change the number of topics shown:** Change `Math.min(titles.length, 20)` to a different number.

**To add category grouping (like Casual English has):** Use the pattern from `openCasualEnglish()` which groups by `it.category`.

---

## 4. Topic Resolution

### What it does
When a user types a number (e.g., "16", "topic 16", "#16"), the system finds the corresponding topic title from the most recent numbered list in conversation history.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Resolution function | `def _resolve_topic_from_history` |
| Call site | `resolved = _resolve_topic_from_history(query, history)` in `api_agent()` |

### How it works
1. Regex matches input like `16`, `topic 16`, `#16`
2. Scans conversation history in reverse for assistant messages containing topic markers ("pick a topic", "type a number", etc.)
3. Extracts numbered items from that message
4. Filters out bold-prefixed items (e.g., "1. **Correct** your grammar")
5. Returns the matching topic title

### How to modify

**To add more topic markers:** Edit the `_topic_markers` tuple inside the function.

**To support different input formats:** Edit the regex pattern `r"^(?:topic\s*)?#?\s*(\d{1,2})\s*$"`.

---

## 5. Article Content Fetching

### What it does
When a topic is resolved, the system fetches the full article content from the raw data files and injects it into the LLM prompt. This ensures the LLM teaches from the actual article, not just RAG snippets.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Fetch function | `def _fetch_article_content` |
| Call site | `article_content = _fetch_article_content(resolved, session_id)` |
| Effective query construction | `if article_content:` block in `api_agent()` |

### Data sources by mode

| Mode | Data file | Fields used |
|------|-----------|-------------|
| AI Learning | `ch8-learning-roadmap.md` + `docs/*.md` | Section text matching topic |
| Tech English | `briefing-data-filtered.json` | `title`, `source`, `url`, `summary`, `body` |
| Casual English | `world-news-data.json` | `title`, `source`, `url`, `summary`, `key_points` |
| AWS AIF-C01 | `aws-cert-learning-roadmap.md` + `knowledge/notes/aws_ai_p1/*.md` | Domain-mapped study notes (5 files for 5 domains). Uses `KNOWLEDGE_ROOT` from `config.py`. |

### How the LLM prompt differs by mode

**AI Learning** (topic selected):
```
"The student selected topic: '{title}'.
Here is the full article content: {content}
Teach them about this topic using the article above."
```

**Tech/Casual English** (topic selected):
```
"The student selected topic: '{title}'.
Here is the full article content: {content}
Analyze this article NOW. Do NOT ask the student questions first.
Start by summarizing, then extract key phrases, expressions, vocabulary."
```

### How to modify

**To add a new data source:** Add a new `elif` branch in `_fetch_article_content()` checking the `session_id`.

**To change what fields are extracted:** Edit the `parts.append()` calls inside the function.

---

## 6. Web Search References

### What it does
For AI Learning only, the system searches DuckDuckGo for real web references related to the user's question and appends them as clickable links at the end of the answer.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Search function | `def _web_search_references` |
| Proxy config | `_WEB_SEARCH_PROXY` |
| Trigger (topic selected) | `web_refs = _web_search_references(f"{resolved} tutorial guide"` |
| Trigger (free question) | `web_refs = _web_search_references(f"{query} AI machine learning tutorial"` |
| Prompt injection | `if web_refs:` block before `def generate()` |
| SSE append | `if web_refs:` inside `generate()` |

### How it works
1. Sends GET request to `https://html.duckduckgo.com/html/` via SOCKS proxy
2. Custom `HTMLParser` extracts links with class `result__a`
3. Decodes `uddg=` redirect URLs to get real URLs
4. Formats as markdown: `📚 Learn more:\n- [Title](URL)`
5. Injected into LLM prompt AND appended as extra SSE `answer_chunk`

### How to modify

**To enable web search for English learning too:** Add `web_refs = _web_search_references(...)` calls in the English learning branches of `api_agent()`.

**To change the search query format:** Edit the f-string in the `_web_search_references()` call.

**To change the proxy:** Set `BRIEFING_PROXY` environment variable, or edit `_WEB_SEARCH_PROXY` default.

**To increase/decrease results:** Change the `num_results` parameter (default: 5).

---

## 7. Topic Refresh

### What it does
When a user says "more topics", "other topics", "new topics", etc., the system fetches fresh topics that haven't been shown yet.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Intent detection | `def _wants_more_topics` |
| Fresh topic fetching | `def _fetch_fresh_topics` |
| Call site | `elif _wants_more_topics(query)` in `api_agent()` |

### How to modify

**To add more trigger phrases:** Edit the `_PHRASES` list inside `_wants_more_topics()`.

**To change the max topics returned:** Edit `fresh[:20]` in `_fetch_fresh_topics()`.

**Note:** AI Learning is explicitly excluded from topic refresh (it uses the roadmap instead).

---

## 8. Summarization Memory

### What it does
For long conversations (>8 messages), older messages are summarized by a fast LLM into a memory block, keeping the last 6 messages in full.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Summary function | `def _summarize_history` |
| Constants | `_SUMMARY_CACHE`, `_RECENT_KEEP = 6`, `_SUMMARIZE_THRESHOLD = 8` |
| Integration | `if n > _SUMMARIZE_THRESHOLD:` in `run_agent()` |

### How to modify

**To keep more recent messages:** Change `_RECENT_KEEP` (default: 6).

**To trigger summarization earlier/later:** Change `_SUMMARIZE_THRESHOLD` (default: 8).

**To use a different model for summarization:** Change `OLLAMA_MODEL_FAST` reference in `_summarize_history()`.

---

## 9. Context Window & Token Limits

### What it does
Learning sessions get larger context windows and response token budgets than regular chat.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Context sizing | `if system_prompt_override:` in `run_agent()` |
| Token limit | `"num_predict": 4096` (all sessions) |

### Current settings

| Session type | num_ctx (small) | num_ctx (large) | num_predict |
|-------------|-----------------|-----------------|-------------|
| Regular chat | 2048–16384 (4 tiers) | — | 4,096 |
| Learning | 8,192 | 16,384 | 4,096 |

### How to modify

**To increase max response length:** Change `4096` in the `num_predict` value in `run_agent()`.

**Warning:** Higher `num_predict` means slower responses. `qwen3.5:4b` generates ~20-30 tokens/sec, so 4096 tokens ≈ 2-3 minutes.

---

## 10. Continue Button

### What it does
A "▶ Continue" button appears on **every** assistant message (global design pattern), allowing the user to extend any truncated response.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Button creation | `contBtn` in the `answer_done` handler (no session check — always shown) |
| Click handler | `contBtn.onclick` |

### How it works
1. Created next to the 📎 Save to Notes button on every assistant message
2. On click: removes itself, constructs a context-aware prompt with the last 300 chars of the previous response, clicks send

### How to modify

**To change the continue prompt:** Edit the template string in the `contBtn.onclick` handler. It currently includes the last 300 chars of the response for context.

**To limit to learning sessions only:** Wrap the button creation in `if (currentSessionId && currentSessionId.startsWith('00000000-'))`.

---

## 11. Learning Notes

### What it does
Users can save any assistant message to persistent notes. Notes panel shows title-only cards that expand on click. Full edit and delete support.

### Where the code lives

| Component | Search for |
|-----------|------------|
| Storage file | `NOTES_FILE` constant |
| List API | `@app.route("/api/notes", methods=["GET"])` |
| Create API | `@app.route("/api/notes", methods=["POST"])` |
| Update API | `@app.route("/api/notes/<note_id>", methods=["PUT"])` |
| Delete API | `@app.route("/api/notes/<note_id>", methods=["DELETE"])` |
| Save button (streaming) | `noteBtn` in `answer_done` handler |
| Notes panel HTML | `<div class="notes-panel"` |
| Panel toggle | `function toggleNotesPanel()` |
| Load/render | `async function loadNotes()` |
| Edit mode | `function startEditNote()` |

### UI Design

Notes panel uses a collapsible card pattern:
- **Collapsed:** Shows arrow + title (first 80 chars) + date. Click to expand.
- **Expanded:** Shows full markdown content + tags + Edit/Delete buttons.
- **Edit mode:** Replaces content with a textarea. Save/Cancel buttons.

### API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/notes` | GET | List notes (optional `?tag=` filter) |
| `/api/notes` | POST | Create a note |
| `/api/notes/<id>` | PUT | Update note content (also regenerates title) |
| `/api/notes/<id>` | DELETE | Delete a note |

### Storage format
File: `C:/reports/ai/.learning-notes.json`
```json
[{
  "id": "uuid",
  "content": "markdown text",
  "title": "auto-generated from first 80 chars",
  "tags": ["ai_learning"],
  "session_id": "00000000-...",
  "session_type": "ai_learning",
  "created_at": "2026-04-11T...",
  "updated_at": "2026-04-11T..."
}]
```

### How to modify

**To add a new tag category:** Edit the auto-tagging logic in `api_notes_create()`.

**To change the notes panel layout:** Edit the `.note-card`, `.note-header`, `.note-body` CSS classes and the `loadNotes()` JS function.

**To change the edit UI:** Modify `startEditNote()` — it creates a textarea and Save/Cancel buttons dynamically.

---

## 12. AWS AIF-C01 Cert Learning

### What it does
Prepares the student for the AWS Certified AI Practitioner (AIF-C01) exam with two independent modes: TEACH (structured lessons) and QUIZ (exam-style practice questions). Tracks progress per domain with a persistent progress file.

### Where the code lives

| Component | Search for |
|-----------|------------|
| System prompt | `SYSTEM_PROMPT_AWS_CERT` |
| Session ID | `"aws_cert"` in `_LEARNING_SESSION_IDS` |
| Roadmap file | `docs/aws-cert-learning-roadmap.md` |
| Study notes (5 domains) | `C:/reports/ai/knowledge/notes/aws_ai_p1/` |
| Progress file | `.aws-cert-progress.json` in `REPORTS_ROOT` |
| Progress functions | `_load_aws_cert_progress`, `_save_aws_cert_progress`, `_update_aws_cert_progress`, `_format_aws_cert_progress` |
| Roadmap loader | `_load_aws_cert_roadmap` |
| Agent route logic | `is_aws_cert` block in `api_agent()` |
| Article fetching | `aws_cert` branch in `_fetch_article_content` |
| Learning context API | `aws_cert` branch in `api_learning_context` |
| Toolbar button | `openAWSCert()` in HTML |
| JS welcome function | `async function openAWSCert()` |

### User commands

| Command | Mode | Example |
|---------|------|---------|
| `teach me <topic>` | TEACH | "teach me Amazon Bedrock" |
| `teach Domain N` | TEACH | "teach me Domain 2" |
| `quiz me on <topic>` | QUIZ | "quiz me on Domain 3" |
| `progress` | PROGRESS | "show progress" |
| Free question | TEACH | "What's the difference between Bedrock and SageMaker?" |

### How to modify

**To add more domains or topics:** Edit `docs/aws-cert-learning-roadmap.md`.

**To change the progress tracking algorithm:** Edit `_update_aws_cert_progress()` — domain detection uses keyword matching.

**To change quiz format:** Edit the QUIZ MODE section in `SYSTEM_PROMPT_AWS_CERT`.

---

## Quick Reference: File Locations

All learning feature code is in `scripts/rag/agent.py`. Here's a quick map:

| Feature | Approx. line range | Key identifiers |
|---------|-------------------|-----------------|
| System prompts | 1004–1120 | `SYSTEM_PROMPT_AI_LEARNING`, `SYSTEM_PROMPT_ENGLISH_LEARNING`, `SYSTEM_PROMPT_CASUAL_ENGLISH`, `SYSTEM_PROMPT_AWS_CERT` |
| Topic resolution | ~1120–1160 | `_resolve_topic_from_history` |
| Topic refresh | ~1160–1190 | `_wants_more_topics`, `_fetch_fresh_topics` |
| Web search | ~1190–1250 | `_web_search_references`, `_WEB_SEARCH_PROXY` |
| Article fetching | ~1250–1400 | `_fetch_article_content` |
| Agent route (learning logic) | ~1400–1550 | `api_agent`, `effective_query`, `web_refs`, `is_aws_cert` |
| Session IDs | search `_LEARNING_SESSION_IDS` | includes `aws_cert` |
| AWS cert progress | search `_load_aws_cert_progress` | `_AWS_CERT_PROGRESS_PATH`, `_update_aws_cert_progress`, `_format_aws_cert_progress` |
| Learning session API | search `api_learning_session` | `api_toolbar_learning_session` |
| Learning context API | search `api_learning_context` | `api_toolbar_learning_context` |
| Welcome messages (JS) | search `openAILearning` | `openAILearning`, `openEnglishLearning`, `openCasualEnglish`, `openAWSCert` |
| Continue button (JS) | search `contBtn` | `contBtn` in `answer_done` handler |
| Notes panel (HTML/JS) | search `toggleNotesPanel` | `toggleNotesPanel`, `loadNotes`, `saveToNotes` |

> **Tip:** Line numbers shift as the file grows. Use the "Key identifiers" column to search instead.
