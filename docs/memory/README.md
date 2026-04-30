# Session Memory Files

AI agent session memory — persistent context that survives across chat sessions.

## Purpose

Memory files prevent the next session from wasting time rediscovering decisions, discoveries, and state that a previous session already established. They are the AI agent's notebook.

## Conventions

- **Naming**: `memory-YYYYMMDD-<topic>.md` (date + kebab-case topic slug)
- **Location**: `docs/memory/`
- **Companion folders**: `memory-YYYYMMDD-<topic>/` (for large artifacts like diagrams)
- **Loading**: On new chat start, the 3 most recent files are offered for loading
- **Updates**: Event-based (decisions, task completions, transitions, discoveries)

## Retention Policy

- Memory files are **disposable session artifacts**, not long-term specifications
- Keep the last **5** memory files for context continuity
- Older files may be deleted manually when no longer relevant
- Completed projects should have their key knowledge captured in `docs/implementation/` (the permanent record), not only in memory files
- The filter question: *"If the next AI session doesn't have this, how many tokens/minutes will it waste rediscovering it?"*

## Current Files

| File | Focus | Created |
|------|-------|---------|
| `memory-20260430-chat-pipeline-final.md` | RAG pipeline improvement (Phases 1–6) | 2026-04-30 |
| `memory-20260427-stock-module-docs.md` | Stock module documentation | 2026-04-27 |
| `memory-20260414-stock-review-and-docs.md` | Stock review session | 2026-04-14 |

## Relationship to Other Docs

- Memory files ≠ implementation docs. Don't duplicate full designs here.
- Memory files → link to implementation docs when the design is captured elsewhere
- Implementation docs in `docs/implementation/` are the **permanent record**
- Plans in `docs/plans/` are the **design-time record**
- Memory files are the **session-time record** (ephemeral, agent-focused)
