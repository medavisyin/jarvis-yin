# Implementation Guide: Confluence Indexers

## Overview

Two scripts add Confluence wiki content to the shared Jarvis RAG store:

1. **`scripts/rag/index_confluence.py`** (approximately 313 lines) — Team-oriented flow: runs a PowerShell report generator, parses the resulting Markdown into per-page records, then chunks and indexes them.
2. **`scripts/rag/index_confluence_user.py`** — User-oriented flow: calls the Atlassian REST API with CQL to find pages authored or touched by a named user, strips HTML to text, preserves heading structure, then chunks and indexes.

Both reuse the same Qdrant collection, embedding model, and `C:/reports/ai/.rag-store.json` snapshot as the other RAG indexers.

## Technologies

| Library / module | Used by | Role |
|------------------|---------|------|
| **sentence-transformers** | Both | `all-MiniLM-L6-v2`, 384-d vectors, offline mode. |
| **qdrant-client** | Both | In-memory client, cosine, shared collection. |
| **subprocess** | `index_confluence.py` | Invokes PowerShell to produce the wiki report. |
| **requests** | `index_confluence_user.py` | REST calls to Confluence (search, page body, etc.). |
| **base64** | `index_confluence_user.py` | Builds Basic auth header from credentials. |
| **Standard library** | Both | `json`, `os`, `re`, `sys`, `uuid`, dates as needed. |

## Architecture: index_confluence.py

1. **Report generation** — Executes `atlassian-report.ps1` from the Atlassian Jira skill directory (`JIRA_SKILL_DIR` + `REPORT_SCRIPT`), producing a Markdown report file.
2. **Parsing** — The report body is split into blocks; wiki pages are recognized when a block starts with the Markdown link pattern `### [title](url)` (and related structure).
3. **Metadata** — For each page, the parser extracts fields such as space, author, updated date, summary, and key topics from the surrounding report text.
4. **Chunking and embedding** — Page text is split into embedding-sized chunks, encoded with the shared model, and upserted with appropriate payloads.
5. **Modes** — Supports full pipeline, report-only, or index-only from an existing Markdown file (see script docstring).

### Key functions (conceptual)

- PowerShell invocation wrapper for `atlassian-report.ps1`.
- Markdown block iterator and regex-driven extraction of `### [title](url)` sections.
- Metadata line parsing for space, author, dates, and topics.
- Shared snapshot load/save and Qdrant upsert helpers (same pattern as other indexers).

## Architecture: index_confluence_user.py

1. **Authentication** — Prepares HTTP headers for Confluence Cloud (site host, Basic auth from email + API token).
2. **User resolution** — Maps a display name to an Atlassian account identifier when possible (known-account map or search API).
3. **CQL search** — Runs Confluence Query Language to list pages associated with the target user.
4. **Content fetch** — Retrieves page storage or body representation, then **strips HTML to plain text** for embedding.
5. **Structure** — Uses headings to preserve document outline in chunk text where applicable.
6. **Chunking and indexing** — Same embedding and Qdrant persistence as the team report path.

### Key functions (conceptual)

- Account ID lookup and CQL query construction.
- HTML-to-text conversion and heading extraction.
- Chunk loop, `PointStruct` creation with stable IDs, batch upsert, snapshot save.

## Configuration

### index_confluence.py

- **`JIRA_SKILL_DIR`** — Path to the Cursor Atlassian Jira skill (contains `atlassian-report.ps1`).
- **`REPORT_SCRIPT`** — Joined path to that script.
- **`SNAPSHOT_PATH`**, **`COLLECTION`**, **`VECTOR_SIZE`** — Aligned with the rest of the RAG stack.

### index_confluence_user.py

- **`SITE`** — Confluence Cloud hostname (e.g. `your-domain.atlassian.net`).
- **`EMAIL`** / **`TOKEN`** — Should be supplied via environment variables in production (see Security Notes).
- **`KNOWN_ACCOUNTS`** — Optional map from lowercase display names to Atlassian account IDs to avoid ambiguous search.

## Usage

Typical invocations (see each script’s module docstring for exact flags):

```text
python index_confluence.py                      # Generate report and index
python index_confluence.py --report-only        # Only run PowerShell report
python index_confluence.py --index-only <path>  # Index existing report Markdown

python index_confluence_user.py "Display Name"
python index_confluence_user.py "Display Name" --limit 200
```

## Security Notes

- **API tokens and passwords must not be committed or shared.** Prefer environment variables (e.g. `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`) and read them at startup rather than hardcoding values in source.
- **Least privilege** — Use an API token scoped to what indexing requires; rotate if exposed.
- **PowerShell report** — Ensure the report script runs under credentials that are allowed to read the intended spaces; audit what the script writes to disk.
- **Snapshots** — `.rag-store.json` contains embedded text payloads; protect the file like any other store of internal wiki excerpts.
