# DevOps & Tooling — Git, PowerShell & Atlassian Integration

> Learning track for the development tools and integrations used alongside
> the Jarvis project: version control, scripting, and team collaboration.

---

## What This Covers

- **Git** (branching, conventional commits, interactive rebase, worktrees)
- **PowerShell** (scripting for Windows, API calls, report generation)
- **Atlassian integration** (Confluence REST API, Jira queries, automated reporting)
- **Development workflow** (code review, CI patterns, project organization)

## How Jarvis Uses These

| Component | Tool | Script |
|-----------|------|--------|
| Confluence indexing | REST API + CQL queries | `scripts/rag/index_confluence.py` |
| Confluence publishing | PowerShell report upload | `scripts/tools/atlassian-report.ps1` |
| Jira reporting | PowerShell + Jira REST API | Jira skill integration |
| Codebase indexing | Git repo scanning for RAG | `scripts/rag/index_codebase.py` |

## Related Jarvis Docs

- [Confluence Indexing](../../implementation/rag/index-confluence-impl.md) — REST API, CQL, PowerShell bridge
- [Codebase Indexing](../../implementation/rag/index-codebase-impl.md) — repo scanning patterns

## Suggested Learning Path

1. **Beginner:** Git fundamentals (branch, merge, rebase), write a PowerShell script
2. **Intermediate:** Confluence/Jira REST APIs, automated reporting, conventional commits
3. **Advanced:** CI/CD pipelines, git hooks, multi-repo workflows

---

*Part of the [Jarvis Learning Series](../). See also: [Python Web](../python-web/), [Data Acquisition](../data-acquisition/)*
