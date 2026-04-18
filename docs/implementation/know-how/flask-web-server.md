# Know-How: Flask Web Server

A short introduction to **Flask** and how **Jarvis** uses it to expose search and chat over HTTP.

## What is Flask?

**Flask** is a **lightweight Python web framework**.

- Often called a **“micro-framework”**: a small core (routing, requests, responses) and you add libraries as needed.
- Fits **APIs** and **small web apps** well when you do not need a heavy, batteries-included stack.

Official documentation:

- [Flask documentation](https://flask.palletsprojects.com/)

## How Jarvis uses Flask

Jarvis runs **two** Flask applications:

| App | Port | Role |
|-----|------|------|
| `search_ui.py` | **18888** | Search UI: library browsing, chunk inspection, search |
| `agent.py` | **18889** | RAG chat agent backed by a local LLM |

**Single-file deployment style:**

- Both apps use **`render_template_string()`** with **embedded HTML** strings (no separate `templates/` tree required for that pattern).
- JSON APIs use **`jsonify()`** for structured responses.

This keeps deployment simple: fewer files to copy, one process per app.

## Key Flask concepts used in Jarvis

### 1. Routes

Map URLs to Python functions with decorators:

```python
@app.route("/api/search", methods=["POST"])
def search():
    ...
```

### 2. Request handling

- **`request.json`** — parsed JSON body for `POST`/`PUT` with `Content-Type: application/json`.
- **`request.args`** — query string parameters (`?q=hello`).

### 3. JSON responses

```python
return jsonify({"results": [...]})
```

### 4. SSE streaming (`agent.py`)

**Server-Sent Events (SSE)** stream partial results over a single long-lived HTTP response.

- Server sets MIME type **`text/event-stream`**.
- Server yields chunks like **`data: {...}\n\n`** as they become available.
- Clients typically use **`EventSource`** or **`fetch()`** with a **ReadableStream** reader.

In Jarvis, this supports **token-by-token** (or chunk-by-chunk) output from the LLM.

**Event types** (conceptual): `model`, `thinking`, `token`, `answer_done`, `error` — the client can branch on the payload to update the UI progressively.

```text
Browser                         Flask (agent.py)
   |                                  |
   |-------- GET /stream (SSE) ------->|
   |<------- data: {token} -----------|
   |<------- data: {token} -----------|
   |<------- data: {answer_done} -----|
```

### 5. Template rendering

`render_template_string(HTML_CONSTANT)` renders HTML defined in the same module (or imported string) instead of loading `.html` files from disk.

## Example route pattern

```python
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route("/api/search", methods=["POST"])
def search():
    query = request.json.get("query", "")
    results = do_search(query)
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=18888)
```

Replace `do_search` with Jarvis’s retrieval pipeline.

## Single-file deployment pattern

**Why embed HTML in Python?**

- One **entry file** per service (`search_ui.py`, `agent.py`).
- Easy to **copy/run** without forgetting template paths.
- Trade-off: large strings in code; some teams prefer splitting templates later as the UI grows.

## Installation

```bash
pip install flask
```

## Further reading

- [Flask Quickstart](https://flask.palletsprojects.com/en/stable/quickstart/)
- [Flask `jsonify`](https://flask.palletsprojects.com/en/stable/api/#flask.json.jsonify)
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
