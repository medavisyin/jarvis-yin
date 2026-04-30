---
tags:
  - hub
  - learning
  - implementation
category: hub
status: current
last-updated: 2026-04-30
---

# Learning Features — Implementation Docs

Documentation for Jarvis's **learning mode features** (interactive educational sessions in the chat agent).

> **Disambiguation**: This folder documents the **feature implementation** — how the agent handles learning sessions. For **tutorial/curriculum content** (concept explanations, beginner guides), see [`docs/learning/`](../../learning/).

## Documents

| Document | Feature |
|----------|---------|
| [casual-english-impl.md](./casual-english-impl.md) | Casual English conversation practice mode |
| [tech-english-impl.md](./tech-english-impl.md) | Technical English (IT vocabulary, reading comprehension) |
| [aws-cert-impl.md](./aws-cert-impl.md) | AWS certification study sessions |
| [deep-dive-notes-impl.md](./deep-dive-notes-impl.md) | Deep-dive note-taking and study sessions |
| [ai-learning-impl.md](./ai-learning-impl.md) | AI/ML concept learning sessions |

## Code Location

- Session routing: `scripts/rag/router.py`
- Learning constants: `scripts/rag/learning/constants.py`
- Learning helpers: `scripts/rag/learning/helpers.py`
- Main wiring: `scripts/rag/agent.py` (learning branch in `api_agent`)
