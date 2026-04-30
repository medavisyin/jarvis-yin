---
tags:
  - implementation
  - usage-tool
  - rag-agent
category: usage-tool
status: stub
last-updated: 2026-04-30
canonical: ../rag/agent-impl.md
---

# RAG Agent (Core Chat Engine)

> **Category**: USAGE TOOL | **Source**: `scripts/rag/` (modular package)

## Summary

The RAG agent is a Flask-served chat engine (~1,405 lines orchestrator) that streams answers over Server-Sent Events (SSE). It uses a multi-stage pipeline (`pipeline.py`) for intent classification, query enhancement, RAG confidence assessment, conversation memory injection, and query decomposition before generation via `agent_loop.run_agent`. Supports tool calling, vision, learning sessions, and modular route Blueprints.

**This document is a navigation stub.** For the full implementation guide (architecture, data flow, API reference, design decisions), see:

> **Canonical doc**: [`docs/implementation/rag/agent-impl.md`](../rag/agent-impl.md)

## Quick Links

| Aspect | Location |
|--------|----------|
| Architecture & pipeline flow | [agent-impl.md → Overview](../rag/agent-impl.md) |
| Modular layout & file map | [agent-impl.md → Modular layout](../rag/agent-impl.md#modular-layout) |
| API reference (routes) | [agent-impl.md → API reference](../rag/agent-impl.md#api-reference) |
| Conversation memory (Phase 5) | [agent-impl.md → Conversation memory](../rag/agent-impl.md#conversation-memory-phase-5) |
| Tool system & schemas | [agent-impl.md → Tool system](../rag/agent-impl.md#tool-system) |
| Config & environment | [agent-impl.md → Technologies](../rag/agent-impl.md#technologies) |

## Key Facts (at a glance)

- **Entry point**: `scripts/rag/agent.py` (~1,405 lines)
- **Default port**: 18889
- **Pipeline**: `pipeline.py` → `intent.py` → `decomposer.py` → `agent_loop.py`
- **Route blueprints**: `routes/stock.py`, `routes/toolbar.py`, `routes/ai_news.py`, `routes/daily_fetch.py`, `routes/donor.py`
- **Memory**: `memory/` package (store, extractor, patterns, retriever)
- **UI template**: `templates/index.html` (4,333 lines)
- **Tests**: `tests/test_pipeline.py` (27 tests) — `python -m pytest tests/test_pipeline.py -v`
