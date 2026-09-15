# Python Web & Application Patterns

> Learning track for Flask web development, async/concurrency patterns,
> and testing — the application backbone of the Jarvis project.

---

## What This Covers

- **Flask** (routing, templates, `render_template_string`, `jsonify`, static-free deployment)
- **Server-Sent Events (SSE)** (streaming responses, `text/event-stream`, chunked transfer)
- **Async & concurrency** (threading, `concurrent.futures`, background workers, `asyncio` basics)
- **REST API design** (JSON APIs, query parameters, polling patterns, error handling)
- **Testing** (pytest, mocking, test structure, CI patterns)

## How Jarvis Uses These

| Component | Pattern | Script |
|-----------|---------|--------|
| Search UI | Flask + HTML + JSON APIs | `scripts/rag/search_ui.py` |
| RAG Agent UI | React SPA + FastAPI `/api` + SSE | `web/` + `scripts/rag/agent.py` — **[Frontend track](../frontend/)** |
| RAG Agent HTTP | FastAPI (Flask-shaped `web_api.py`) + background threads | `scripts/rag/agent.py` |
| Background indexing | `threading.Thread(daemon=True)` + job polling | `search_ui.py`, `agent.py` |
| Pipeline orchestration | `concurrent.futures.ThreadPoolExecutor` | `scripts/pipeline/run-all-sources.py` |
| Fetcher scripts | Async patterns, retry logic, proxy handling | `scripts/fetchers/` |

## Related Jarvis Docs

- [Flask Web Server](flask-web-server.md) — routing, templates, deployment
- [Async & Concurrency](async-concurrency-python.md) — threading, futures, async
- [Testing Python Apps](testing-python-apps.md) — pytest patterns
- [Search UI Implementation](../../implementation/rag/search-ui-impl.md) — Flask API reference
- [Agent Implementation](../../implementation/rag/agent-impl.md) — SSE streaming, sessions
- [Frontend learning](../frontend/) — React, `apiJson`, Vite (Agent UI :18889)

## Suggested Learning Path

1. **Beginner:** Build a minimal Flask app, understand routes and JSON responses, write a pytest test
2. **Intermediate:** Add background threads, implement SSE streaming, use `concurrent.futures`
3. **Advanced:** Production patterns (error handling, graceful shutdown, health checks, load testing)

---

*Part of the [Jarvis Learning Series](../). See also: [RAG](../rag/), [Frontend](../frontend/), [Data Acquisition](../data-acquisition/)*
