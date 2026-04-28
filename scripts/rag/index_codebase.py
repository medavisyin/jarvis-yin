"""
Codebase Indexer — indexes project source code and docs into the RAG vector store.

Walks configured project directories, extracts meaningful chunks from:
- README/docs (Markdown files)
- Java source files (class/interface signatures, method summaries, package info)
- Configuration files (pom.xml dependencies, application.yml, persistence.xml)

Stores in the same Qdrant collection as other RAG content, searchable together.

Project directories come from two sources in .rag-projects.json:
  - base_dirs: root folders auto-discovered (each immediate subdirectory = project)
  - explicit_projects: manually listed {name, path} entries

Content-hash deduplication: files with identical content across different projects
are indexed only once (first occurrence wins).

Usage:
  python index_codebase.py                   Index all configured projects
  python index_codebase.py <project-path>    Index a specific project directory

Dependencies: pip install qdrant-client sentence-transformers
"""
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import date
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import SNAPSHOT_PATH, PROJECT_DIRS_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384

SKIP_DIRS = {
    "node_modules", ".git", "target", "build", ".idea", ".vscode",
    ".gradle", "__pycache__", ".mvn", "bin", ".settings",
}

JAVA_EXTENSIONS = {".java"}
DOC_EXTENSIONS = {".md", ".adoc", ".txt", ".rst"}
CONFIG_FILES = {
    "pom.xml", "build.gradle", "application.yml", "application.yaml",
    "application.properties", "persistence.xml", "docker-compose.yml",
    "Dockerfile", "README.md", "CHANGELOG.md",
}

MAX_CHUNK_CHARS = 600

def load_project_dirs() -> list[dict]:
    """Load project directories from .rag-projects.json.

    Config format:
      {
        "base_dirs": ["D:/projects", ...],
        "explicit_projects": [{"name": "Foo", "path": "D:/other/foo"}, ...]
      }

    base_dirs: each immediate subdirectory becomes a project (name = folder name).
    explicit_projects: manually specified projects with custom names.
    Returns empty list if config file is missing or invalid.
    """
    if not os.path.isfile(PROJECT_DIRS_PATH):
        print(f"  Config not found: {PROJECT_DIRS_PATH}")
        print(f"  Create it with base_dirs and/or explicit_projects to index projects.")
        return []

    try:
        with open(PROJECT_DIRS_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"  Error reading {PROJECT_DIRS_PATH}: {e}")
        return []

    projects: list[dict] = []
    seen_paths: set[str] = set()

    for base_dir in cfg.get("base_dirs", []):
        base_dir = os.path.normpath(base_dir)
        if not os.path.isdir(base_dir):
            print(f"  Base dir not found, skipping: {base_dir}")
            continue
        for entry in sorted(os.listdir(base_dir)):
            entry_path = os.path.join(base_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry.startswith("."):
                continue
            norm = os.path.normcase(os.path.normpath(entry_path))
            if norm in seen_paths:
                continue
            seen_paths.add(norm)
            projects.append({"name": entry, "path": entry_path})

    for proj in cfg.get("explicit_projects", []):
        name = proj.get("name", "")
        path = proj.get("path", "")
        if not name or not path:
            continue
        norm = os.path.normcase(os.path.normpath(path))
        if norm in seen_paths:
            continue
        seen_paths.add(norm)
        projects.append({"name": name, "path": os.path.normpath(path)})

    if not projects:
        print("  No projects resolved from config (check base_dirs and explicit_projects)")

    return projects


def _get_model():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def _get_client():
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    if os.path.exists(SNAPSHOT_PATH):
        _load_snapshot(client)
    return client


def _load_snapshot(client):
    from qdrant_client.models import PointStruct
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = data.get("points", [])
    for i in range(0, len(points), 100):
        batch = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points[i:i + 100]
        ]
        client.upsert(collection_name=COLLECTION, points=batch)
    print(f"  Loaded {len(points)} existing points from snapshot")


def _save_snapshot(client):
    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points, next_offset = result
        for p in points:
            all_points.append({
                "id": p.id,
                "vector": p.vector if isinstance(p.vector, list) else list(p.vector),
                "payload": p.payload,
            })
        if next_offset is None:
            break
        offset = next_offset

    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump({"points": all_points, "count": len(all_points)}, f)
    print(f"  Saved {len(all_points)} total points to snapshot")


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = 100) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    prev_tail = ""
    for para in paragraphs:
        if not current:
            current = (prev_tail + "\n\n" + para).strip() if prev_tail else para
            continue
        if len(current) + len(para) > max_chars:
            chunks.append(current.strip())
            prev_tail = current[-overlap:] if len(current) > overlap else current
            current = prev_tail + "\n\n" + para
        else:
            current = current + "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text[:max_chars]]


def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


# ===================================================================
# JAVA FILE PROCESSING
# ===================================================================

def _extract_java_summary(content: str, filepath: str) -> list[dict]:
    """Extract meaningful chunks from a Java source file."""
    chunks = []
    lines = content.split("\n")

    package = ""
    for line in lines:
        m = re.match(r'package\s+([\w.]+)\s*;', line)
        if m:
            package = m.group(1)
            break

    class_match = re.search(
        r'(/\*\*[\s\S]*?\*/\s*)?'
        r'(?:@\w+(?:\([^)]*\))?\s*)*'
        r'(public\s+)?(?:abstract\s+)?(?:final\s+)?'
        r'(class|interface|enum|record)\s+'
        r'(\w+)(?:\s*<[^>]+>)?'
        r'(?:\s+extends\s+(\w+))?'
        r'(?:\s+implements\s+([\w,\s]+))?',
        content
    )

    if not class_match:
        return chunks

    javadoc = class_match.group(1) or ""
    kind = class_match.group(3)
    class_name = class_match.group(4)
    extends = class_match.group(5) or ""
    implements = class_match.group(6) or ""

    javadoc_clean = re.sub(r'/\*\*|\*/|\*\s?', '', javadoc).strip()
    javadoc_clean = re.sub(r'@\w+.*', '', javadoc_clean).strip()

    method_pattern = re.compile(
        r'(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?'
        r'(?:[\w<>\[\],\s]+)\s+(\w+)\s*\([^)]*\)',
    )
    methods = method_pattern.findall(content)
    methods = [m for m in methods if m != class_name and m not in ("toString", "hashCode", "equals")]

    summary_parts = [f"{kind} {class_name}"]
    if package:
        summary_parts.insert(0, f"package {package}")
    if extends:
        summary_parts.append(f"extends {extends}")
    if implements:
        summary_parts.append(f"implements {implements.strip()}")
    if javadoc_clean:
        summary_parts.append(f"\n{javadoc_clean}")
    if methods:
        summary_parts.append(f"\nMethods: {', '.join(methods[:20])}")

    summary = "\n".join(summary_parts)
    rel_path = os.path.basename(filepath)

    chunks.append({
        "text": summary[:MAX_CHUNK_CHARS],
        "title": f"{class_name} ({kind})",
        "filename": rel_path,
    })

    api_pattern = re.compile(
        r'(/\*\*[\s\S]*?\*/\s*)?'
        r'((?:@\w+(?:\([^)]*\))?\s*)+)?'
        r'(?:public)\s+(?:static\s+)?(?:final\s+)?'
        r'([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)',
    )
    for m in api_pattern.finditer(content):
        method_doc = m.group(1) or ""
        annotations = m.group(2) or ""
        return_type = m.group(3).strip()
        method_name = m.group(4)
        params = m.group(5).strip()

        if method_name in ("toString", "hashCode", "equals", class_name):
            continue

        has_rest = any(a in annotations for a in ("@GET", "@POST", "@PUT", "@DELETE", "@Path", "@RequestMapping"))
        has_doc = bool(method_doc.strip())
        if not has_rest and not has_doc:
            continue

        doc_clean = re.sub(r'/\*\*|\*/|\*\s?', '', method_doc).strip()
        doc_clean = re.sub(r'@\w+.*', '', doc_clean).strip()

        method_text = f"{class_name}.{method_name}({params}) -> {return_type}"
        if annotations.strip():
            method_text = annotations.strip() + "\n" + method_text
        if doc_clean:
            method_text += f"\n{doc_clean}"

        chunks.append({
            "text": method_text[:MAX_CHUNK_CHARS],
            "title": f"{class_name}.{method_name}()",
            "filename": rel_path,
        })

    return chunks


# ===================================================================
# DOC / CONFIG FILE PROCESSING
# ===================================================================

def _process_markdown(content: str, filepath: str) -> list[dict]:
    """Chunk a Markdown file into sections."""
    filename = os.path.basename(filepath)
    title = filename
    m = re.match(r'^#\s+(.+)', content)
    if m:
        title = m.group(1).strip()

    text_chunks = _chunk_text(content)
    return [
        {"text": chunk, "title": f"{title} (part {i+1})", "filename": filename}
        for i, chunk in enumerate(text_chunks)
    ]


def _process_config(content: str, filepath: str) -> list[dict]:
    """Index a config file as a single chunk (or split if large)."""
    filename = os.path.basename(filepath)
    if len(content) > MAX_CHUNK_CHARS * 2:
        content = content[:MAX_CHUNK_CHARS * 2]
    text_chunks = _chunk_text(content)
    return [
        {"text": chunk, "title": f"{filename} (part {i+1})", "filename": filename}
        for i, chunk in enumerate(text_chunks)
    ]


# ===================================================================
# MAIN INDEXING LOGIC
# ===================================================================

def index_project(
    project_name: str,
    project_path: str,
    model,
    client,
    seen_hashes: set[str] | None = None,
) -> tuple[int, int]:
    """Walk a project directory and index relevant files.

    Returns (chunk_count, files_deduped).
    seen_hashes: shared set of content hashes for cross-project deduplication.
    If a file's content hash is already in the set, it is skipped.
    """
    from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

    if seen_hashes is None:
        seen_hashes = set()

    try:
        delete_filter = Filter(must=[
            FieldCondition(key="source", match=MatchValue(value=f"project:{project_name}")),
        ])
        old_ids = []
        offset = None
        while True:
            result = client.scroll(
                collection_name=COLLECTION,
                scroll_filter=delete_filter,
                limit=500,
                offset=offset,
                with_payload=False,
            )
            points, next_offset = result
            old_ids.extend(p.id for p in points)
            if next_offset is None:
                break
            offset = next_offset
        if old_ids:
            client.delete(collection_name=COLLECTION, points_selector=old_ids)
            print(f"  Removed {len(old_ids)} old chunks for {project_name}")
    except Exception as e:
        print(f"  Warning: failed to remove old chunks for {project_name}: {e}")

    all_chunks = []
    files_processed = 0
    files_deduped = 0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        rel_root = os.path.relpath(root, project_path).replace("\\", "/")

        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()

            try:
                if ext in JAVA_EXTENSIONS:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if len(content) < 50:
                        continue
                    ch = _content_hash(content)
                    if ch in seen_hashes:
                        files_deduped += 1
                        continue
                    seen_hashes.add(ch)
                    chunks = _extract_java_summary(content, fpath)
                    for c in chunks:
                        c["rel_path"] = f"{rel_root}/{fname}"
                    all_chunks.extend(chunks)
                    files_processed += 1

                elif ext in DOC_EXTENSIONS or fname in CONFIG_FILES:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if len(content) < 20:
                        continue
                    ch = _content_hash(content)
                    if ch in seen_hashes:
                        files_deduped += 1
                        continue
                    seen_hashes.add(ch)
                    if ext in DOC_EXTENSIONS:
                        chunks = _process_markdown(content, fpath)
                    else:
                        chunks = _process_config(content, fpath)
                    for c in chunks:
                        c["rel_path"] = f"{rel_root}/{fname}"
                    all_chunks.extend(chunks)
                    files_processed += 1

            except Exception:
                continue

    if not all_chunks:
        print(f"  No indexable content found in {project_name}")
        if files_deduped:
            print(f"  ({files_deduped} files skipped as duplicates)")
        return 0, files_deduped

    print(f"  Processed {files_processed} files -> {len(all_chunks)} chunks" +
          (f" ({files_deduped} deduped)" if files_deduped else ""))
    print(f"  Generating embeddings...", end=" ", flush=True)

    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    print("done")

    today = date.today().isoformat()
    points = []
    for chunk, emb in zip(all_chunks, embeddings):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "date": today,
                "source": f"project:{project_name}",
                "title": chunk["title"],
                "item_type": "code_doc",
                "difficulty": "intermediate",
                "url": "",
                "filename": chunk.get("rel_path", chunk.get("filename", "")),
                "parent_title": project_name,
                "tags": [],
                "text": chunk["text"],
            },
        ))

    for i in range(0, len(points), 100):
        client.upsert(collection_name=COLLECTION, points=points[i:i + 100])

    print(f"  Indexed {len(points)} chunks for {project_name}")
    return len(points), files_deduped


def main():
    projects = load_project_dirs()

    if len(sys.argv) > 1:
        custom_path = sys.argv[1]
        if os.path.isdir(custom_path):
            name = os.path.basename(os.path.normpath(custom_path))
            projects = [{"name": name, "path": custom_path}]
        else:
            print(f"Error: {custom_path} is not a directory")
            sys.exit(1)

    print("Codebase Indexer — indexing project source code and docs")
    print(f"Projects: {len(projects)}")
    print()

    model = _get_model()
    client = _get_client()
    total = 0
    seen_hashes: set[str] = set()

    for proj in projects:
        name = proj["name"]
        path = proj["path"]
        if not os.path.isdir(path):
            print(f"  SKIP {name}: {path} not found")
            continue
        print(f"Indexing {name} ({path})...")
        count, _deduped = index_project(name, path, model, client, seen_hashes)
        total += count
        print()

    if total > 0:
        print(f"Saving snapshot ({total} new chunks)...")
        _save_snapshot(client)

    print(f"\nDone! Indexed {total} chunks across {len(projects)} projects.")
    print(f"Deduplication: {len(seen_hashes)} unique file hashes tracked.")


if __name__ == "__main__":
    main()
