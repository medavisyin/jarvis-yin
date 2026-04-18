"""
Custom Content Indexer — indexes personal knowledge into the RAG vector store.

Supports Markdown (.md) and PDF (.pdf) files. Content is stored in the same
Qdrant collection as AI briefings, searchable together.

Usage:
  python index_custom.py add <file-or-folder>     Index a file or folder
  python index_custom.py scan                      Index all content in knowledge/
  python index_custom.py list                      Show indexed custom content
  python index_custom.py remove <pattern>          Remove indexed content by title pattern

Folder structure (auto-categorized):
  C:/reports/ai/knowledge/
    books/      -> item_type: book_chapter
    projects/   -> item_type: project_doc
    notes/      -> item_type: personal_note
    tasks/      -> item_type: task

Optional YAML frontmatter in Markdown files:
  ---
  title: My Custom Title
  tags: [architecture, medavis]
  difficulty: intermediate
  ---

Dependencies: pip install qdrant-client sentence-transformers pypdf pyyaml
"""
import json
import os
import re
import sys
import uuid
from datetime import date
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import KNOWLEDGE_ROOT, SNAPSHOT_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384

FOLDER_TYPE_MAP = {
    "books": "book_chapter",
    "projects": "project_doc",
    "notes": "personal_note",
    "tasks": "task",
}

DEFAULT_DIFFICULTY = {
    "book_chapter": "intermediate",
    "project_doc": "intermediate",
    "personal_note": "beginner",
    "task": "beginner",
}


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
    print(f"  Saved {len(all_points)} points to snapshot")


def _load_snapshot(client):
    from qdrant_client.models import PointStruct
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    points = data.get("points", [])
    if not points:
        return

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points[i:i + batch_size]
        ]
        client.upsert(collection_name=COLLECTION, points=batch)
    print(f"  Loaded {len(points)} points from snapshot")


def _chunk_text(text: str, max_chars: int = 500, overlap: int = 100) -> List[str]:
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


def _chunk_by_sections(text: str, max_chars: int = 500) -> List[str]:
    """Split by headings first, then by paragraph if sections are too long."""
    sections = re.split(r'\n(?=#{1,3}\s)', text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            chunks.extend(_chunk_text(section, max_chars))
    return chunks if chunks else _chunk_text(text, max_chars)


def _parse_frontmatter(content: str) -> tuple:
    """Extract YAML frontmatter and body from Markdown content."""
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_str = content[3:end].strip()
    body = content[end + 4:].strip()

    meta = {}
    try:
        import yaml
        meta = yaml.safe_load(yaml_str) or {}
    except ImportError:
        for line in yaml_str.split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                val = val.strip().strip('"').strip("'")
                if val.startswith("[") and val.endswith("]"):
                    val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
                meta[key.strip()] = val
    except Exception:
        pass

    return meta, body


def _infer_item_type(filepath: str) -> str:
    """Infer item_type from folder location."""
    rel = os.path.relpath(filepath, KNOWLEDGE_ROOT).replace("\\", "/")
    folder = rel.split("/")[0] if "/" in rel else ""
    return FOLDER_TYPE_MAP.get(folder, "personal_note")


def _extract_pdf_sections(filepath: str) -> List[dict]:
    """Extract sections from a PDF file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
    except ImportError:
        print("  Warning: pypdf not installed, skipping PDF")
        return []

    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    if not full_text.strip():
        print(f"  Warning: no text extracted from {filepath}")
        return []

    title = os.path.splitext(os.path.basename(filepath))[0]
    item_type = _infer_item_type(filepath)
    difficulty = DEFAULT_DIFFICULTY.get(item_type, "intermediate")

    chunks = _chunk_by_sections(full_text)
    items = []
    for i, chunk in enumerate(chunks):
        heading_match = re.match(r'(?:Chapter\s+\d+[:\s]*|#{1,3}\s*)(.+?)(?:\n|$)', chunk)
        chunk_title = heading_match.group(1).strip() if heading_match else f"{title} (part {i+1})"

        items.append({
            "text": chunk,
            "metadata": {
                "date": date.today().isoformat(),
                "source": "custom",
                "title": chunk_title,
                "item_type": item_type,
                "difficulty": difficulty,
                "url": "",
                "filename": os.path.basename(filepath),
                "parent_title": title,
                "tags": [],
            }
        })

    return items


def _extract_markdown(filepath: str) -> List[dict]:
    """Extract chunks from a Markdown file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    meta, body = _parse_frontmatter(content)
    if not body.strip():
        return []

    title = meta.get("title", "")
    if not title:
        for line in body.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = os.path.splitext(os.path.basename(filepath))[0]

    item_type = _infer_item_type(filepath)
    difficulty = meta.get("difficulty", DEFAULT_DIFFICULTY.get(item_type, "intermediate"))
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    chunks = _chunk_by_sections(body)
    items = []
    for i, chunk in enumerate(chunks):
        heading_match = re.match(r'#{1,3}\s*(.+?)(?:\n|$)', chunk)
        chunk_title = heading_match.group(1).strip() if heading_match else title
        if len(chunks) > 1 and chunk_title == title:
            chunk_title = f"{title} (part {i+1})"

        items.append({
            "text": chunk,
            "metadata": {
                "date": date.today().isoformat(),
                "source": "custom",
                "title": chunk_title,
                "item_type": item_type,
                "difficulty": difficulty,
                "url": meta.get("url", ""),
                "filename": os.path.basename(filepath),
                "parent_title": title,
                "tags": tags,
            }
        })

    return items


def index_file(filepath: str, client, model) -> int:
    """Index a single file. Returns number of chunks indexed."""
    from qdrant_client.models import PointStruct

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        items = _extract_pdf_sections(filepath)
    elif ext in (".md", ".markdown", ".txt"):
        items = _extract_markdown(filepath)
    else:
        print(f"  Skipping unsupported file type: {filepath}")
        return 0

    if not items:
        return 0

    texts = [item["text"] for item in items]
    embeddings = model.encode(texts, show_progress_bar=False)

    points = []
    for i, (item, embedding) in enumerate(zip(items, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"custom:{item['metadata']['filename']}:{i}"))
        points.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload={**item["metadata"], "text": item["text"]},
        ))

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=COLLECTION, points=batch)

    return len(points)


def cmd_add(path: str):
    """Index a single file or all supported files in a folder."""
    client = _get_client()
    model = _get_model()
    total = 0

    if os.path.isfile(path):
        count = index_file(path, client, model)
        print(f"  Indexed {count} chunks from {os.path.basename(path)}")
        total = count
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".md", ".markdown", ".txt", ".pdf"):
                    continue
                fpath = os.path.join(root, fname)
                count = index_file(fpath, client, model)
                if count > 0:
                    print(f"  Indexed {count} chunks from {fname}")
                total += count
    else:
        print(f"Error: {path} not found")
        sys.exit(1)

    if total > 0:
        _save_snapshot(client)
    print(f"\nTotal: {total} chunks indexed")


def cmd_scan():
    """Scan and index all content in the knowledge/ folder."""
    if not os.path.isdir(KNOWLEDGE_ROOT):
        print(f"Knowledge folder not found: {KNOWLEDGE_ROOT}")
        print("Create it with subfolders: books/, projects/, notes/, tasks/")
        sys.exit(1)

    print(f"Scanning {KNOWLEDGE_ROOT}...")
    cmd_add(KNOWLEDGE_ROOT)


def cmd_list():
    """List all indexed custom content."""
    if not os.path.exists(SNAPSHOT_PATH):
        print("No indexed data. Run 'index_custom.py scan' first.")
        return

    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    custom_points = [p for p in data["points"] if p["payload"].get("source") == "custom"]
    if not custom_points:
        print("No custom content indexed yet.")
        return

    by_type = {}
    for p in custom_points:
        t = p["payload"].get("item_type", "unknown")
        by_type.setdefault(t, []).append(p)

    print(f"Custom content: {len(custom_points)} chunks\n")
    for item_type, points in sorted(by_type.items()):
        titles = set(p["payload"].get("parent_title", p["payload"].get("title", "")) for p in points)
        print(f"  [{item_type}] {len(points)} chunks from {len(titles)} files:")
        for title in sorted(titles):
            count = sum(1 for p in points if p["payload"].get("parent_title", p["payload"].get("title", "")) == title)
            print(f"    - {title} ({count} chunks)")
    print()


def cmd_remove(pattern: str):
    """Remove custom content matching a title pattern."""
    if not os.path.exists(SNAPSHOT_PATH):
        print("No indexed data.")
        return

    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    before = len(data["points"])
    pattern_lower = pattern.lower()
    data["points"] = [
        p for p in data["points"]
        if not (p["payload"].get("source") == "custom"
                and pattern_lower in (p["payload"].get("parent_title", "") + p["payload"].get("title", "")).lower())
    ]
    after = len(data["points"])
    removed = before - after

    if removed == 0:
        print(f"No custom content matching '{pattern}' found.")
        return

    data["count"] = after
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"Removed {removed} chunks matching '{pattern}' ({after} points remaining)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "add":
        if len(sys.argv) < 3:
            print("Usage: python index_custom.py add <file-or-folder>")
            sys.exit(1)
        cmd_add(sys.argv[2])
    elif command == "scan":
        cmd_scan()
    elif command == "list":
        cmd_list()
    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python index_custom.py remove <title-pattern>")
            sys.exit(1)
        cmd_remove(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print("Commands: add, scan, list, remove")
        sys.exit(1)


if __name__ == "__main__":
    main()
