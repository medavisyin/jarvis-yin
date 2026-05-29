"""
AI Briefing RAG Indexer — indexes daily briefing content into a local vector store.

Uses Qdrant in-memory mode with JSON persistence to avoid Windows file-locking issues.

Usage:
  python index_briefing.py <date-folder>
  e.g.: python index_briefing.py C:/reports/ai/2026-04-08

  python index_briefing.py --backfill
  Indexes all existing briefings in C:/reports/ai/

Dependencies: pip install qdrant-client sentence-transformers pypdf
"""
import json
import os
import re
import sys
import uuid
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import REPORTS_ROOT, SNAPSHOT_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384


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
    """Persist all points to a JSON file."""
    from qdrant_client.models import ScrollRequest
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
    _tmp = f"{SNAPSHOT_PATH}.tmp-{os.getpid()}"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump({"points": all_points, "count": len(all_points)}, f)
    os.replace(_tmp, SNAPSHOT_PATH)
    print(f"  Saved {len(all_points)} points to snapshot")


def _load_snapshot(client):
    """Restore points from JSON snapshot."""
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


def _extract_json_items(date_folder: str) -> List[dict]:
    """Extract news items from briefing-data JSON when PDF/raw files are absent.

    Prefers ``briefing-data-filtered.json``; falls back to ``briefing-data.json``.
    Each news item becomes one chunk with its title, summary, source, and URL.
    """
    data_file = os.path.join(date_folder, "briefing-data-filtered.json")
    if not os.path.isfile(data_file):
        data_file = os.path.join(date_folder, "briefing-data.json")
    if not os.path.isfile(data_file):
        return []

    try:
        with open(data_file, "r", encoding="utf-8") as f:
            bdata = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    folder_date = os.path.basename(date_folder)
    items: List[dict] = []

    for src_block in bdata.get("per_source_data", []):
        src_name = src_block.get("source_name") or src_block.get("name") or "Unknown"
        for it in src_block.get("items", []):
            title = (it.get("title") or "").strip()
            if not title:
                continue

            summary = (it.get("summary") or it.get("description") or "").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            commentary = (it.get("commentary") or "").strip()
            prediction = (it.get("prediction") or "").strip()
            points = it.get("points") or []

            text_parts = [title]
            if summary:
                text_parts.append(summary)
            if points:
                text_parts.append(" | ".join(str(p) for p in points[:10]))
            if commentary:
                text_parts.append(f"Commentary: {commentary}")
            if prediction:
                text_parts.append(f"Prediction: {prediction}")
            text = "\n\n".join(text_parts)

            for chunk in _chunk_text(text):
                items.append({
                    "text": chunk,
                    "metadata": {
                        "date": folder_date,
                        "source": src_name,
                        "title": title,
                        "item_type": "news_item",
                        "difficulty": "intermediate",
                        "url": url,
                    },
                })

    return items


def _extract_pdf_items(date_folder: str) -> List[dict]:
    pdf_path = os.path.join(date_folder, "ai-briefing.pdf")
    if not os.path.exists(pdf_path):
        return []

    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() + "\n"
    except ImportError:
        print("  Warning: pypdf not installed, skipping PDF extraction")
        return []

    sections = re.split(r'\n(?=\d+\.\s)', full_text)
    items = []
    folder_date = os.path.basename(date_folder)

    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < 50:
            continue

        title_match = re.match(r'\d+\.\s*(.+?)(?:\n|$)', section)
        title = title_match.group(1).strip() if title_match else f"Section {i}"

        items.append({
            "text": section[:1500],
            "metadata": {
                "date": folder_date,
                "source": "PDF Briefing",
                "title": title,
                "item_type": "news_item",
                "difficulty": "intermediate",
                "url": "",
            }
        })

    return items


def _extract_raw_files(date_folder: str) -> List[dict]:
    raw_dir = os.path.join(date_folder, "raw")
    if not os.path.isdir(raw_dir):
        return []

    items = []
    folder_date = os.path.basename(date_folder)

    for md_file in sorted(os.listdir(raw_dir)):
        if not md_file.endswith(".md"):
            continue
        filepath = os.path.join(raw_dir, md_file)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        title = ""
        source_url = ""
        difficulty = "intermediate"
        for line in content.split("\n"):
            if line.startswith("# ") and not title:
                title = line[2:].strip()
            elif line.startswith("**Source:**"):
                source_url = line.replace("**Source:**", "").strip()
            elif line.startswith("**Difficulty:**"):
                difficulty = line.replace("**Difficulty:**", "").strip().lower()

        source_name = md_file.split("-")[0] if "-" in md_file else "unknown"

        for chunk in _chunk_text(content):
            items.append({
                "text": chunk,
                "metadata": {
                    "date": folder_date,
                    "source": source_name,
                    "title": title,
                    "item_type": "raw_content",
                    "difficulty": difficulty,
                    "url": source_url,
                    "filename": md_file,
                }
            })

    return items


def _extract_learning_guide(date_folder: str) -> List[dict]:
    guide_path = os.path.join(date_folder, "learning-guide.md")
    if not os.path.exists(guide_path):
        return []

    with open(guide_path, "r", encoding="utf-8") as f:
        content = f.read()

    folder_date = os.path.basename(date_folder)
    return [{
        "text": content[:2000],
        "metadata": {
            "date": folder_date,
            "source": "learning-guide",
            "title": f"Learning Guide {folder_date}",
            "item_type": "learning_guide",
            "difficulty": "beginner",
            "url": "",
        }
    }]


def index_date_folder(date_folder: str, client, model):
    """Index all content from a single date folder."""
    from qdrant_client.models import PointStruct

    folder_date = os.path.basename(date_folder)
    print(f"\n  Indexing {folder_date}...")

    all_items = []
    all_items.extend(_extract_pdf_items(date_folder))
    all_items.extend(_extract_raw_files(date_folder))
    all_items.extend(_extract_learning_guide(date_folder))
    if not all_items:
        all_items.extend(_extract_json_items(date_folder))

    if not all_items:
        print(f"  No content found in {date_folder}")
        return 0

    texts = [item["text"] for item in all_items]
    embeddings = model.encode(texts, show_progress_bar=False)

    points = []
    for i, (item, embedding) in enumerate(zip(all_items, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"{folder_date}:{item['metadata']['title']}:{i}"))
        points.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload={**item["metadata"], "text": item["text"]},
        ))

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=COLLECTION, points=batch)

    print(f"  Indexed {len(points)} chunks from {folder_date}")
    return len(points)


def main():
    if "--backfill" in sys.argv:
        print("Starting backfill...")
        client = _get_client()
        model = _get_model()
        total = 0
        date_folders = sorted(
            d for d in os.listdir(REPORTS_ROOT)
            if os.path.isdir(os.path.join(REPORTS_ROOT, d))
            and re.match(r'\d{4}-\d{2}-\d{2}', d)
        )
        print(f"Found {len(date_folders)} briefing folders")
        for folder_name in date_folders:
            folder_path = os.path.join(REPORTS_ROOT, folder_name)
            count = index_date_folder(folder_path, client, model)
            total += count
        _save_snapshot(client)
        print(f"\nBackfill complete: {total} total chunks from {len(date_folders)} briefings")
        return

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python index_briefing.py <date-folder>   Index a single day")
        print("  python index_briefing.py --backfill       Index all existing briefings")
        sys.exit(1)

    date_folder = sys.argv[1]
    if not os.path.isdir(date_folder):
        print(f"Error: {date_folder} is not a directory")
        sys.exit(1)

    client = _get_client()
    model = _get_model()
    index_date_folder(date_folder, client, model)
    _save_snapshot(client)


if __name__ == "__main__":
    main()
