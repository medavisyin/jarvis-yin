# Implementation Guide: index_codebase.py

## Overview

This script indexes project source code and documentation into the same RAG vector store used for AI briefings. It lives at `scripts/rag/index_codebase.py` (approximately 421 lines). It walks configured repositories, extracts structured chunks from Java, prose docs, and key config files, embeds them, and upserts with a `project:{name}` source tag so each project can be refreshed independently.

## Technologies

The stack matches `index_briefing.py` for embeddings and storage:

- **sentence-transformers** — `SentenceTransformer("all-MiniLM-L6-v2")`, 384-dimensional vectors, offline Hub mode.
- **qdrant-client** — In-memory client, cosine distance, same `ai_briefings` collection and `.rag-store.json` snapshot path.

**pypdf** is not used; there are no PDF inputs in this indexer.

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  ENTRY                                                                  │
│  python index_codebase.py  |  python index_codebase.py <project-path>   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LOAD STORE                                                             │
│  In-memory Qdrant + COLLECTION ← .rag-store.json (if exists)           │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PROJECTS FROM .rag-projects.json                                       │
│  base_dirs → one project per subfolder │ explicit_projects {name, path} │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  index_project (seen_hashes shared across projects)                     │
│  1. Delete points with payload source == project:{name}                  │
│  2. os.walk tree (prune SKIP_DIRS)                                       │
│  3. Route: .java → _extract_java_summary │ docs → _process_markdown      │
│            CONFIG_FILES basename → _process_config                        │
│  4. Per file: MD5 content hash skip if duplicate (first project wins)   │
│  5. model.encode batches → upsert PointStruct (source project:{name})   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                ▼
                        _save_snapshot → .rag-store.json
```

1. **Snapshot load** — Same pattern as other indexers: create in-memory collection, load `C:/reports/ai/.rag-store.json` if present.
2. **Project walk** — For each project from `load_project_dirs()` (`PROJECT_DIRS_PATH` / `.rag-projects.json`), `os.walk` traverses the tree while pruning skip-listed directory names.
3. **File-type routing** — `.java` files go through Java-specific extraction; `.md`, `.adoc`, `.txt`, `.rst` through Markdown-style chunking; known config filenames through config handling.
4. **Project refresh** — Before adding new chunks for a project, the script deletes existing points whose `source` payload equals `project:{project_name}`.
5. **Embed and upsert** — Same embedding model and batch upsert pattern as the briefing indexer.
6. **Chunk size** — `MAX_CHUNK_CHARS = 600`, slightly larger than the briefing indexer’s 500, to accommodate class summaries and method blocks.

## Key Functions

### `_extract_java_summary(content, filepath)`

The most specialized logic in this script. It uses regular expressions over the full file text to build searchable chunks:

1. **Package** — Scans lines for `package name;` and records the package identifier.
2. **Type declaration** — A composite regex captures optional leading Javadoc, annotations, visibility/`abstract`/`final` modifiers, and whether the type is a `class`, `interface`, `enum`, or `record`, plus the simple name, optional `extends`, and optional `implements` list.
3. **Class-level chunk** — Javadoc is stripped of comment delimiters and block tags for readability. A summary chunk lists package (if any), kind and name, extends/implements, cleaned class Javadoc, and up to 20 method names discovered by a broad signature pattern (used as a quick index of the type’s surface area).
4. **Method-level chunks** — A second pass finds `public` methods with optional Javadoc and annotation blocks. **Only methods that have Javadoc or recognizable REST-style annotations** (`@GET`, `@POST`, `@PUT`, `@DELETE`, `@Path`, `@RequestMapping`) are emitted as separate chunks, keeping noise down.
5. **Noise filter** — Constructors (same name as class) and `toString`, `hashCode`, and `equals` are excluded from method-level indexing.
6. **Chunk text shape** — Each method chunk is shaped as `ClassName.methodName(params) -> returnType`, prefixed by annotations and optional cleaned Javadoc, truncated to `MAX_CHUNK_CHARS`.

### `_process_markdown(content, filepath)`

Uses paragraph-style `_chunk_text` on the full document. Title defaults to the filename or the first `#` heading. Each chunk gets a disambiguating “(part N)” suffix in the title.

### `_process_config(content, filepath)`

For large files, content may be capped before chunking. Otherwise splits with the same paragraph chunker as Markdown, producing one or more parts.

### `index_project(project_name, project_path, model, client)`

Orchestrates deletion of old `project:{name}` points, directory walk with `SKIP_DIRS` filtering, dispatch to the three processors, embedding, point construction, and upsert.

## Configuration

### `PROJECT_DIRS`

List of `{ "name", "path" }` objects. Default entries (paths are environment-specific and may need editing):

- P4M Next  
- Admin App  
- Core Framework  
- Vaadin UI  
- AWS Infrastructure  
- RIS Dashboard  

### `SKIP_DIRS`

Directory names excluded from recursion, including: `node_modules`, `.git`, `target`, `build`, `.idea`, `.vscode`, `.gradle`, `__pycache__`, `.mvn`, `bin`, `.settings`.

### File classification

- **`JAVA_EXTENSIONS`** — `{".java"}`
- **`DOC_EXTENSIONS`** — `{".md", ".adoc", ".txt", ".rst"}`
- **`CONFIG_FILES`** — Basenames such as `pom.xml`, `build.gradle`, `application.yml` / `application.yaml`, `application.properties`, `persistence.xml`, `docker-compose.yml`, `Dockerfile`, `README.md`, `CHANGELOG.md`

Constants `SNAPSHOT_PATH`, `COLLECTION`, and `VECTOR_SIZE` align with other RAG scripts.

## Usage

```text
python index_codebase.py                   # Index all configured projects
python index_codebase.py <project-path>    # Index a specific project directory
```

## Design Decisions

- **Regex-based Java parsing** — Fast and dependency-free; suitable for navigation and search, not a full AST substitute.
- **Selective method indexing** — Requiring Javadoc or REST annotations avoids flooding the store with boilerplate accessors.
- **Per-project replace** — Deleting by `source=project:{name}` keeps re-runs idempotent at the project level without touching briefing or custom content.
- **Slightly larger chunks (600)** — Balances signature + Javadoc + annotations in one retrievable unit for backend code.
