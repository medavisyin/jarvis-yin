# Plans Index

Status overview for all planning documents in this folder.

## Active Plans

| Plan | Status | Focus | Canonical Impl Doc |
|------|--------|-------|-------------------|
| [jarvis-next](2026-04-17-jarvis-next.md) | Active | Master roadmap — bug fixes, testing, features | — |
| [obsidian-docs-enhancement](2026-04-21-obsidian-docs-enhancement.md) | Active | Obsidian vault config, frontmatter, canvas | — |
| [long-term-scanner](2026-04-27-long-term-scanner.md) | Active | Long-term stock scanner + scanner rename | `implementation/stock/` |
| [daily-fetch-enhancements](2026-04-28-daily-fetch-enhancements.md) | Active | Confluence diff, deep dive endpoint | `implementation/rag/agent-impl.md` |
| [project-intelligence](2026-04-28-project-intelligence.md) | Active | Maven deps, project graph, knowledge graph tool | `implementation/rag/agent-impl.md` |
| [plan-ml-integration](plan-ml-integration.md) | Partial | ML feedback loop — tasks 1-2 done, 3-5 pending | `implementation/rag/search-ui-impl.md` |
| [hf-datasets-integration](2026-05-01-hf-datasets-integration.md) | Done | HF datasets lib for RAG evaluation + data mgmt | `implementation/rag/eval-datasets-impl.md` |

## Archived (Completed)

Moved to `archive/` when all tasks are done. Each archived plan links to the implementation docs that supersede it.

| Plan | Completed | Superseded By |
|------|-----------|---------------|
| [chat-pipeline-improvement-roadmap](archive/2026-04-30-chat-pipeline-improvement-roadmap.md) | 2026-04-30 | `implementation/rag/agent-impl.md` |
| [enhanced-conversation-memory](archive/2026-04-30-enhanced-conversation-memory.md) | 2026-04-30 | `implementation/rag/agent-impl.md` (memory section) |
| [plan-advanced-rag](archive/plan-advanced-rag.md) | 2026-04 | `implementation/rag/search-ui-impl.md`, `agent-impl.md` |
| [stock-prediction](archive/2026-04-12-stock-prediction.md) | 2026-04-12 | `implementation/stock/` |
| [china-market-adaptation](archive/2026-04-22-china-market-adaptation.md) | 2026-04-22 | `implementation/stock/china-market-impl.md` |

## Conventions

- **Naming**: `YYYY-MM-DD-<topic>.md` for dated plans, `plan-<topic>.md` for undated
- **Archival**: Move to `archive/` when all tasks are marked Done/Completed
- **Status tracking**: Use frontmatter `status:` field or a "## Status" section with a task table
- **Cross-links**: Each archived plan should note which implementation doc supersedes it
