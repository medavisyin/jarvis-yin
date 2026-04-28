# Daily Fetch Enhancements — Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next. There are two independent features — Task 1-2 cover wiki change summaries, Task 3-5 cover the Learning Guide deep dive.

**Goal:** Two enhancements to the Daily Fetch feature: (1) Wiki fetch shows real change summaries by diffing current vs previous page version for existing pages, and (2) Learning Guide items get a "Deep Dive" button that creates a Jarvis chat session, fetching the source URL live and teaching the content interactively.

**Architecture:** Enhancement 1 adds a previous-version fetch to `index_confluence_user.py` (Confluence REST API `?status=historical&version=N-1`) and changes the AI summary prompt in `agent.py` to focus on what changed when a diff is available. Enhancement 2 adds a new API endpoint `/api/toolbar/deep-dive` that fetches the source URL content, creates a chat session pre-seeded with a teaching system prompt + live content, and a JS button in the report preview renderer that triggers it.

**Tech Stack:** Python (requests for Confluence API, difflib for text diff), existing Ollama infra (qwen3:1.7b for wiki summaries, main model for deep dive), Flask API, embedded JS UI.

---

## Task 1: Add version number + previous-version body fetch to `index_confluence_user.py`

**Files:**
- Modify: `scripts/rag/index_confluence_user.py:218-229` — capture `version.number` in page_metas
- Modify: `scripts/rag/index_confluence_user.py:245-285` — fetch previous version body when version > 1, compute diff summary
- Modify: `scripts/rag/index_confluence_user.py:525-537` — include `version_number` and `change_summary` in REPORT_JSON

**Step 1: Add `version_number` to page_metas**

In `scripts/rag/index_confluence_user.py`, the CQL search loop at line 218 already has access to the `version` dict. Add the version number to `page_metas`:

```python
        for page in results:
            version = page.get("version", {})
            space = page.get("space", {})
            modified = version.get("when", "")
            page_metas.append({
                "title": page.get("title", ""),
                "page_id": page.get("id", ""),
                "space_name": space.get("name", ""),
                "space_key": space.get("key", ""),
                "url": f"https://{SITE}/wiki{page.get('_links', {}).get('webui', '')}",
                "modified_at": modified.split("T")[0] if modified else "",
                "version_number": version.get("number", 1),
            })
```

**Step 2: Add `_fetch_previous_version_text` helper function**

Add this function after `_get_headings` (around line 149), before `_safe_print`:

```python
def _fetch_previous_version_text(page_id: str, current_version: int) -> str:
    """Fetch the plain text of the previous version of a page.
    Returns empty string if version <= 1 or fetch fails."""
    if current_version <= 1:
        return ""
    prev_version = current_version - 1
    try:
        import requests
        url = (f"https://{SITE}/wiki/rest/api/content/{page_id}"
               f"?expand=body.storage&status=historical&version={prev_version}")
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        body_data = r.json()
        storage_html = body_data.get("body", {}).get("storage", {}).get("value", "")
        return _strip_html(storage_html)
    except Exception:
        return ""
```

**Step 3: Compute change summary in the body-fetch loop**

In the body-fetch loop (line 245-285), after fetching the current body, also fetch the previous version and compute a concise diff. Modify the loop body:

```python
    print(f"  Fetching body content for {len(page_metas)} pages...")
    all_pages = []
    for i, meta in enumerate(page_metas):
        page_id = meta["page_id"]
        if not page_id:
            continue
        try:
            body_url = f"https://{SITE}/wiki/rest/api/content/{page_id}?expand=body.storage"
            r = requests.get(body_url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            body_data = r.json()
            storage_html = body_data.get("body", {}).get("storage", {}).get("value", "")
        except Exception as e:
            _safe_print(f"    [{i+1}] Body fetch failed for '{meta['title']}': {e}")
            storage_html = ""

        body_text = _strip_html(storage_html)
        headings = _get_headings(storage_html)

        version_num = meta.get("version_number", 1)
        change_summary = ""
        if version_num > 1 and body_text:
            prev_text = _fetch_previous_version_text(page_id, version_num)
            if prev_text:
                change_summary = _compute_change_summary(body_text, prev_text)

        full_text = f"{meta['title']}\n\n"
        if meta["space_name"]:
            full_text += f"Space: {meta['space_name']}\n"
        full_text += f"Creator: {display_name}\n"
        if meta["modified_at"]:
            full_text += f"Last modified: {meta['modified_at']}\n"
        full_text += f"\n{body_text}"
        if headings:
            full_text += "\n\nKey sections:\n" + "\n".join(f"- {h}" for h in headings)

        all_pages.append({
            "title": meta["title"],
            "page_id": page_id,
            "url": meta["url"],
            "space": meta["space_name"],
            "space_key": meta["space_key"],
            "creator": display_name,
            "updated_when": meta["modified_at"],
            "text": full_text,
            "headings": headings,
            "summary": (body_text[:500] + "...") if len(body_text) > 500 else body_text,
            "version_number": version_num,
            "change_summary": change_summary,
        })

        if (i + 1) % 10 == 0:
            _safe_print(f"    Fetched {i+1}/{len(page_metas)} page bodies...")
            time.sleep(0.5)
        else:
            time.sleep(0.15)

    return all_pages
```

**Step 4: Add `_compute_change_summary` helper function**

Add this function right after `_fetch_previous_version_text`:

```python
def _compute_change_summary(current_text: str, previous_text: str) -> str:
    """Compute a concise text diff summary between previous and current page versions.
    Returns a short description of what was added/removed/changed."""
    import difflib

    prev_lines = previous_text.splitlines()
    curr_lines = current_text.splitlines()
    diff = list(difflib.unified_diff(prev_lines, curr_lines, n=0))

    added_lines = []
    removed_lines = []
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            removed_lines.append(line[1:].strip())

    added_lines = [l for l in added_lines if l]
    removed_lines = [l for l in removed_lines if l]

    if not added_lines and not removed_lines:
        return ""

    parts = []
    if added_lines:
        added_preview = " | ".join(added_lines[:5])
        if len(added_preview) > 500:
            added_preview = added_preview[:500] + "..."
        parts.append(f"Added ({len(added_lines)} lines): {added_preview}")
    if removed_lines:
        removed_preview = " | ".join(removed_lines[:3])
        if len(removed_preview) > 300:
            removed_preview = removed_preview[:300] + "..."
        parts.append(f"Removed ({len(removed_lines)} lines): {removed_preview}")

    return "\n".join(parts)
```

**Step 5: Include `version_number` and `change_summary` in REPORT_JSON**

In the `report_json` output section (line 525-537), add the new fields:

```python
    if report_json:
        import json as _json
        page_details = []
        for p in pages:
            page_details.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "space": p.get("space", "") or p.get("space_name", ""),
                "summary": p.get("summary", "")[:300],
                "headings": p.get("headings", [])[:8],
                "modified_at": p.get("updated_when", "") or p.get("modified_at", ""),
                "version_number": p.get("version_number", 1),
                "change_summary": p.get("change_summary", "")[:600],
            })
        print(f"REPORT_JSON:{_json.dumps(page_details, ensure_ascii=False)}")
```

**Verify:** Run the script manually for a known user with a recently edited page:
```bash
python scripts/rag/index_confluence_user.py "Rong Yin" --date-from 2026-04-27 --report-json 2>&1 | findstr "REPORT_JSON"
```
Expected: JSON output now contains `version_number` (integer > 1 for existing pages) and `change_summary` (non-empty string with added/removed lines).

---

## Task 2: Update AI summary prompt in `agent.py` to use change diff

**Files:**
- Modify: `scripts/rag/agent.py:3731-3769` — update `_wiki_ai_summary` to use `change_summary` when available

**Step 1: Modify `_wiki_ai_summary` to prefer diff-based summarization**

Replace the `_wiki_ai_summary` function (lines 3731-3769) with a version that uses `change_summary` for existing pages:

```python
                def _wiki_ai_summary(page_detail: dict) -> str:
                    """Use Ollama to summarize what changed on a wiki page."""
                    title = page_detail.get("title", "")
                    raw_summary = page_detail.get("summary", "").strip()
                    headings = page_detail.get("headings", [])
                    change_summary = page_detail.get("change_summary", "").strip()
                    version_number = page_detail.get("version_number", 1)
                    if not raw_summary and not change_summary:
                        return ""

                    is_update = version_number > 1 and change_summary
                    context_parts = [f"Page title: {title}"]
                    if headings:
                        context_parts.append(f"Sections: {', '.join(headings[:8])}")

                    if is_update:
                        context_parts.append(f"Changes in this update:\n{change_summary}")
                        system_prompt = (
                            "You are a concise technical writer. Given a Confluence wiki page's "
                            "change diff, write a 1-2 sentence summary of what was actually "
                            "changed or updated. Focus on what was added, modified, or removed. "
                            "Be specific and factual. Output only the summary, no labels or prefixes."
                        )
                    else:
                        context_parts.append(f"Content excerpt:\n{raw_summary}")
                        system_prompt = (
                            "You are a concise technical writer. Given a new Confluence wiki page's content, "
                            "write a 1-2 sentence summary of what this page covers. "
                            "Be specific and factual. Output only the summary, no labels or prefixes."
                        )

                    context = "\n".join(context_parts)
                    try:
                        import requests as _req
                        resp = _req.post(
                            f"{OLLAMA_HOST}/api/chat",
                            json={
                                "model": OLLAMA_MODEL_FAST,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": context},
                                ],
                                "stream": False,
                                "think": False,
                                "options": {"temperature": 0.3, "num_predict": 200},
                            },
                            timeout=30,
                        )
                        resp.raise_for_status()
                        result = resp.json().get("message", {}).get("content", "").strip()
                        result = re.sub(r"</?think>", "", result).strip()
                        return result
                    except Exception:
                        return ""
```

**Step 2: Update the wiki report markdown to indicate new vs updated pages**

In the wiki report writing section (lines 3790-3815), add a label to distinguish new pages from updates:

```python
                        for user, details in all_user_pages_detail.items():
                            wf.write(f"### {user}\n\n")
                            for pg in details:
                                title = pg.get("title", "Untitled")
                                url = pg.get("url", "")
                                space = pg.get("space", "")
                                modified = pg.get("modified_at", "")
                                headings = pg.get("headings", [])
                                ai_summary = pg.get("ai_summary", "")
                                version_number = pg.get("version_number", 1)
                                is_new = version_number <= 1

                                if url:
                                    wf.write(f"- **[{title}]({url})**")
                                else:
                                    wf.write(f"- **{title}**")
                                if space:
                                    wf.write(f" — *{space}*")
                                if modified:
                                    wf.write(f" (modified: {modified})")
                                if is_new:
                                    wf.write(" 🆕")
                                wf.write("\n")
                                if ai_summary:
                                    label = "Summary" if is_new else "Changes"
                                    wf.write(f"  > **{label}:** {ai_summary}\n")
                                elif pg.get("summary", "").strip():
                                    brief = pg["summary"].strip()[:200] + ("..." if len(pg["summary"].strip()) > 200 else "")
                                    wf.write(f"  > {brief}\n")
                                if headings:
                                    wf.write(f"  > Sections: {', '.join(headings[:5])}\n")
                                if url:
                                    wf.write(f"  > [Open in Confluence]({url})\n")
                                wf.write("\n")
```

**Verify:** Run a full Daily Fetch or just the `wiki_fetch` continue step. Check the generated `wiki-fetch-{date}.md` report:
- Existing pages (version > 1) should show "**Changes:** Added section about X, updated Y" style summaries
- Brand new pages (version = 1) should show "**Summary:** This page covers Z" style summaries and a 🆕 label

---

## Task 3: Add Deep Dive backend endpoint

**Files:**
- Modify: `scripts/rag/agent.py` — add new endpoint `/api/toolbar/deep-dive` (near the other toolbar endpoints, around line 2210)

**Step 1: Add the `/api/toolbar/deep-dive` endpoint**

Add this endpoint after the existing toolbar endpoints (e.g., after the wiki-fetch endpoint block, around line 2290). The endpoint:
1. Receives a `source_url` and `title` from the Learning Guide item
2. Fetches the source URL content live
3. Creates a new chat session pre-seeded with a teaching system prompt
4. Returns the session ID so the UI can navigate to it

```python
@app.route("/api/toolbar/deep-dive", methods=["POST"])
def api_toolbar_deep_dive():
    """Create a deep-dive learning session from a Learning Guide source URL."""
    data = request.get_json(silent=True) or {}
    source_url = (data.get("source_url") or "").strip()
    title = (data.get("title") or "").strip()
    if not source_url and not title:
        return jsonify({"error": "source_url or title required"}), 400

    fetched_content = ""
    fetch_error = ""
    if source_url:
        fetched_content, fetch_error = _fetch_source_url_content(source_url)

    raw_file = (data.get("raw_file") or "").strip()
    raw_content = ""
    if raw_file and not fetched_content:
        raw_content = _read_raw_file_content(raw_file)

    content = fetched_content or raw_content
    if not content and not title:
        return jsonify({"error": "Could not fetch content and no title provided"}), 400

    _ensure_chat_sessions_dir()
    sid = str(uuid.uuid4())
    now = _now_iso()
    session_title = f"Deep Dive — {title}" if title else f"Deep Dive — {source_url[:60]}"

    teaching_context = f"Topic: {title}\n" if title else ""
    if source_url:
        teaching_context += f"Source: {source_url}\n"
    if content:
        max_content = 8000
        if len(content) > max_content:
            content = content[:max_content] + "\n\n[Content truncated for context window]"
        teaching_context += f"\n---\nSource content:\n{content}"

    initial_prompt = (
        f"I want to learn about this topic from my daily AI briefing. "
        f"Please provide a comprehensive explanation.\n\n{teaching_context}"
    )

    session_data = {
        "id": sid,
        "title": session_title,
        "created_at": now,
        "updated_at": now,
        "messages": [
            {"role": "user", "content": initial_prompt},
        ],
        "session_type": "deep_dive",
        "deep_dive_meta": {
            "source_url": source_url,
            "title": title,
            "raw_file": raw_file,
            "fetch_error": fetch_error,
        },
    }
    if not _save_session_file(session_data):
        return jsonify({"error": "Failed to create session"}), 500

    return jsonify({"session_id": sid, "title": session_title})
```

**Step 2: Add the `_fetch_source_url_content` helper**

Add this helper function near the other utility functions (e.g., near `_web_search_references` around line 1208):

```python
def _fetch_source_url_content(url: str, timeout: int = 20) -> tuple:
    """Fetch a URL and return (text_content, error_string).
    Uses the same proxy as the briefing fetcher scripts."""
    if not url:
        return "", "No URL provided"
    try:
        import httpx
        proxy = os.environ.get("BRIEFING_PROXY", "socks5://localhost:10808")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)",
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        }
        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=True) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            raw = r.text

        if "html" in content_type.lower() or raw.strip().startswith("<!") or raw.strip().startswith("<html"):
            text = _html_to_text(raw)
        else:
            text = raw

        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text, ""
    except Exception as e:
        return "", str(e)[:200]


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text, stripping tags and scripts."""
    import re as _re
    text = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<header[^>]*>.*?</header>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<br\s*/?>', '\n', text, flags=_re.IGNORECASE)
    text = _re.sub(r'</p>', '\n\n', text, flags=_re.IGNORECASE)
    text = _re.sub(r'</div>', '\n', text, flags=_re.IGNORECASE)
    text = _re.sub(r'</h[1-6]>', '\n\n', text, flags=_re.IGNORECASE)
    text = _re.sub(r'</li>', '\n', text, flags=_re.IGNORECASE)
    import html as html_mod
    text = html_mod.unescape(text)
    text = _re.sub(r'<[^>]+>', '', text)
    text = _re.sub(r'[ \t]+', ' ', text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _read_raw_file_content(raw_file_ref: str) -> str:
    """Read a raw/*.md file from the most recent reports directory."""
    for d_offset in range(7):
        dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        raw_path = os.path.join(REPORTS_ROOT, dt, raw_file_ref)
        if os.path.isfile(raw_path):
            try:
                with open(raw_path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                continue
    return ""
```

**Verify:** Test the endpoint with curl:
```bash
curl -X POST http://localhost:18889/api/toolbar/deep-dive -H "Content-Type: application/json" -d "{\"source_url\": \"https://huggingface.co/blog\", \"title\": \"Test Article\"}"
```
Expected: JSON response with `session_id` (UUID) and `title` starting with "Deep Dive —".

---

## Task 4: Handle Deep Dive sessions in the chat endpoint

**Files:**
- Modify: `scripts/rag/agent.py:1439-1452` — add deep_dive session type detection in the chat endpoint

**Step 1: Add deep_dive system prompt constant**

Add this near the other `SYSTEM_PROMPT_*` constants (find them with a search for `SYSTEM_PROMPT_`):

```python
SYSTEM_PROMPT_DEEP_DIVE = (
    "You are an expert AI tutor. The user wants to learn about a specific topic from their "
    "daily AI briefing. You have been given the source content below.\n\n"
    "Your teaching approach:\n"
    "1. Start with a clear, structured overview of the key concepts\n"
    "2. Explain the significance — why this matters in the field\n"
    "3. Break down technical details into digestible pieces\n"
    "4. Provide concrete examples or analogies where helpful\n"
    "5. Highlight practical takeaways and implications\n"
    "6. Suggest related topics for further exploration\n\n"
    "Use clear headings, bullet points, and code examples where appropriate. "
    "Adapt your depth based on follow-up questions. "
    "Respond in the same language as the user's message."
)
```

**Step 2: Detect deep_dive sessions in the chat endpoint**

In the chat endpoint (around line 1439-1452), add detection for deep_dive sessions. After the existing learning session checks:

```python
    learning_prompt = None
    is_learning = False
    if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
        learning_prompt = SYSTEM_PROMPT_AI_LEARNING
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("english_learning"):
        learning_prompt = SYSTEM_PROMPT_ENGLISH_LEARNING
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
        learning_prompt = SYSTEM_PROMPT_CASUAL_ENGLISH
        is_learning = True
    elif session_id == _LEARNING_SESSION_IDS.get("aws_cert"):
        learning_prompt = SYSTEM_PROMPT_AWS_CERT
        is_learning = True
    else:
        session_data = _load_session_file(session_id) if session_id else None
        if session_data and session_data.get("session_type") == "deep_dive":
            learning_prompt = SYSTEM_PROMPT_DEEP_DIVE
            is_learning = True
```

**Verify:** Create a deep-dive session via the API, then send a chat message to it. The response should use the teaching style with structured overview, significance, etc.

---

## Task 5: Add "Deep Dive" button to Learning Guide items in the report preview

**Files:**
- Modify: `scripts/rag/agent.py:7333-7372` — update `loadDfReportContent` JS function to inject Deep Dive buttons

**Step 1: Add `startDeepDive` JS function**

Add this function right after `loadDfReportContent` (around line 7372):

```javascript
async function startDeepDive(title, sourceUrl, rawFile) {
  try {
    showToast('Creating deep dive session for: ' + title.substring(0, 50) + '...');
    var body = {title: title};
    if (sourceUrl) body.source_url = sourceUrl;
    if (rawFile) body.raw_file = rawFile;
    var resp = await fetch('/api/toolbar/deep-dive', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    var data = await resp.json();
    if (!resp.ok) { showToast('Deep dive error: ' + (data.error || 'unknown')); return; }
    showToast('Deep dive session created! Loading...');
    await refreshSessionList();
    await loadSession(data.session_id);
    closeDailyFetchModal();
    sendMessage(null);
  } catch (e) {
    showToast('Deep dive error: ' + e.message);
  }
}
```

**Step 2: Update the report markdown renderer to inject Deep Dive buttons**

In the `loadDfReportContent` function (around line 7347), after the existing markdown rendering pipeline, add a post-processing step that detects Learning Guide items and injects a "Deep Dive" button next to each source line.

Find this block (around line 7347-7362):

```javascript
    var md = data.content || '';
    var rendered = md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      ...
```

After the existing `rendered = ...` pipeline and before the `preview.innerHTML = ...` line, add:

```javascript
    var isLearningGuide = filename.startsWith('learning-guide');
    if (isLearningGuide) {
      rendered = rendered.replace(
        /(\d+)\.\s+<strong[^>]*>([^<]+)<\/strong>([\s\S]*?)(?=(?:\d+\.\s+<strong)|(?:<h[234])|(?:<hr)|$)/g,
        function(match, num, itemTitle, rest) {
          var sourceMatch = rest.match(/Source:\s*(<a[^>]+href="([^"]+)"[^>]*>[^<]*<\/a>|([^\s<][^\n<]*))/);
          var fileMatch = rest.match(/File:\s*<code>([^<]+)<\/code>/);
          var sourceUrl = '';
          if (sourceMatch) {
            sourceUrl = sourceMatch[2] || sourceMatch[3] || '';
          }
          var rawFile = '';
          if (fileMatch) rawFile = fileMatch[1];
          var btnHtml = ' <button onclick="startDeepDive(\'' +
            escHtml(itemTitle).replace(/'/g, "\\'") + '\',\'' +
            escHtml(sourceUrl).replace(/'/g, "\\'") + '\',\'' +
            escHtml(rawFile).replace(/'/g, "\\'") +
            '\')" style="background:#1a3a2e;border:1px solid #34d399;border-radius:4px;' +
            'padding:1px 8px;font-size:0.75em;color:#34d399;cursor:pointer;margin-left:6px;' +
            'vertical-align:middle" title="Start a deep-dive learning session for this topic">' +
            '&#128218; Deep Dive</button>';
          return num + '. <strong>' + itemTitle + '</strong>' + btnHtml + rest;
        }
      );
    }
```

**Verify:** Run the Daily Fetch, then open the history view and click the `learning-guide-*.md` report. Each numbered Learning Guide item should now have a green "Deep Dive" button. Clicking it should:
1. Show a toast "Creating deep dive session..."
2. Create a new session visible in the sidebar
3. Switch to that session
4. Auto-send the first teaching message

---

## Task 6: Manual integration test

**No files to modify.** This is a verification-only task.

**Step 1: Test wiki change summaries end-to-end**

1. Ensure at least one Confluence page was recently updated (not newly created)
2. Run the Daily Fetch (or just the `wiki_fetch` continue step)
3. Open the wiki-fetch report in the history view
4. Verify:
   - Existing pages show "**Changes:**" with a meaningful diff-based summary
   - New pages (if any) show "**Summary:**" with a content-based summary and 🆕 label
   - Pages with only minor formatting changes show appropriate brief summaries

**Step 2: Test Learning Guide deep dive end-to-end**

1. Ensure the Daily Fetch has a `learning-guide-*.md` report with items that have Source URLs
2. Open the report in the history view
3. Click "Deep Dive" on an item with a source URL
4. Verify:
   - A new session is created with "Deep Dive — {title}" as the name
   - The session auto-sends and the AI responds with a structured teaching overview
   - The content is from the live-fetched source (not just the title)
   - Follow-up questions in the session work normally
5. Click "Deep Dive" on an item without a source URL
6. Verify:
   - It falls back to using the `raw/*.md` file content
   - The teaching session still works

---

## Summary of all file changes

| File | Changes |
|------|---------|
| `scripts/rag/index_confluence_user.py` | Add `version_number` to page_metas; add `_fetch_previous_version_text` and `_compute_change_summary` helpers; include `version_number` and `change_summary` in body-fetch loop output and REPORT_JSON |
| `scripts/rag/agent.py` | Update `_wiki_ai_summary` to use diff for existing pages; update wiki report labels (new vs changes); add `SYSTEM_PROMPT_DEEP_DIVE` constant; add deep_dive session detection in chat endpoint; add `/api/toolbar/deep-dive` endpoint + helpers (`_fetch_source_url_content`, `_html_to_text`, `_read_raw_file_content`); add `startDeepDive` JS function; inject Deep Dive buttons in Learning Guide report preview |
