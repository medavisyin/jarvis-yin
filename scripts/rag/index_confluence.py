"""
Confluence Wiki Indexer — fetches team wiki updates and indexes into RAG store.

Runs the atlassian-report.ps1 script to generate a Confluence report,
then parses individual wiki pages and indexes each as a separate item.

Usage:
  python index_confluence.py                    Run report + index
  python index_confluence.py --report-only      Only generate the report
  python index_confluence.py --index-only <md>  Only index an existing report file

Dependencies: pip install qdrant-client sentence-transformers
"""
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import JIRA_REPORT_SCRIPT, REPORTS_ROOT, SNAPSHOT_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384
REPORT_SCRIPT = JIRA_REPORT_SCRIPT


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
    _tmp = f"{SNAPSHOT_PATH}.tmp-{os.getpid()}"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump({"points": all_points, "count": len(all_points)}, f)
    os.replace(_tmp, SNAPSHOT_PATH)
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


def run_confluence_report(report_dir: str) -> str:
    """Run atlassian-report.ps1 and return the path to the generated report."""
    os.makedirs(report_dir, exist_ok=True)

    print(f"  Running Confluence report script...")
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", REPORT_SCRIPT,
         "-ReportDir", report_dir],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        print(f"  Warning: Report script exited with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:500]}")

    today = date.today().strftime("%Y%m%d")
    report_path = os.path.join(report_dir, f"atlassian-daily-report-{today}.md")
    if os.path.exists(report_path):
        print(f"  Report generated: {report_path}")
        return report_path

    for f in sorted(os.listdir(report_dir), reverse=True):
        if f.startswith("atlassian-daily-report-") and f.endswith(".md"):
            report_path = os.path.join(report_dir, f)
            print(f"  Found report: {report_path}")
            return report_path

    print("  Error: No report file generated")
    return ""


def parse_confluence_pages(report_path: str) -> List[dict]:
    """Parse the Confluence section of the report into individual wiki pages."""
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    confluence_match = re.search(
        r'## Team Confluence Updates.*?\n(.*?)(?=\n## |\Z)',
        content,
        re.DOTALL
    )
    if not confluence_match:
        print("  No Confluence section found in report")
        return []

    confluence_text = confluence_match.group(1)

    page_blocks = re.split(r'\n(?=### \[)', confluence_text)
    pages = []

    for block in page_blocks:
        block = block.strip()
        if not block.startswith("### ["):
            continue

        title_match = re.match(r'### \[(.+?)\]\((.+?)\)', block)
        if not title_match:
            continue

        title = title_match.group(1)
        url = title_match.group(2)

        space = ""
        updated = ""
        author = ""
        space_match = re.search(r'\*\*Space:\*\*\s*(.+?)\s*\|', block)
        if space_match:
            space = space_match.group(1).strip()
        updated_match = re.search(r'\*\*Updated:\*\*\s*(.+?)\s*\|', block)
        if updated_match:
            updated = updated_match.group(1).strip()
        author_match = re.search(r'\*\*By:\*\*\s*(.+?)\s*\|', block)
        if author_match:
            author = author_match.group(1).strip()

        summary = ""
        summary_match = re.search(r'\*\*Summary:\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)', block, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        topics = []
        topics_match = re.search(r'\*\*Key topics.*?\*\*\n((?:- .+\n?)+)', block)
        if topics_match:
            topics = [line.lstrip("- ").strip() for line in topics_match.group(1).strip().split("\n")]

        full_text = f"{title}\n\n"
        if space:
            full_text += f"Space: {space}\n"
        if author:
            full_text += f"Author: {author}\n"
        if updated:
            full_text += f"Updated: {updated}\n"
        full_text += f"\n{summary}"
        if topics:
            full_text += "\n\nKey topics:\n" + "\n".join(f"- {t}" for t in topics)

        pages.append({
            "title": title,
            "url": url,
            "space": space,
            "author": author,
            "updated": updated,
            "summary": summary,
            "topics": topics,
            "text": full_text,
        })

    return pages


def index_confluence_pages(pages: List[dict], client, model) -> int:
    """Index parsed Confluence pages into the RAG store."""
    from qdrant_client.models import PointStruct

    if not pages:
        return 0

    all_items = []
    for page in pages:
        chunks = _chunk_text(page["text"])
        for i, chunk in enumerate(chunks):
            all_items.append({
                "text": chunk,
                "metadata": {
                    "date": page.get("updated", date.today().isoformat()),
                    "source": "confluence",
                    "title": page["title"] if len(chunks) == 1 else f"{page['title']} (part {i+1})",
                    "item_type": "wiki_page",
                    "difficulty": "intermediate",
                    "url": page.get("url", ""),
                    "filename": "",
                    "parent_title": page["title"],
                    "tags": page.get("topics", []),
                    "space": page.get("space", ""),
                    "author": page.get("author", ""),
                }
            })

    texts = [item["text"] for item in all_items]
    embeddings = model.encode(texts, show_progress_bar=False)

    points = []
    for i, (item, embedding) in enumerate(zip(all_items, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"confluence:{item['metadata']['parent_title']}:{i}"))
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


def main():
    report_dir = os.path.join(REPORTS_ROOT, date.today().isoformat())

    if "--report-only" in sys.argv:
        report_path = run_confluence_report(report_dir)
        if report_path:
            pages = parse_confluence_pages(report_path)
            print(f"  Found {len(pages)} wiki pages in report")
        return

    if "--index-only" in sys.argv:
        idx = sys.argv.index("--index-only")
        if idx + 1 >= len(sys.argv):
            print("Usage: python index_confluence.py --index-only <report.md>")
            sys.exit(1)
        report_path = sys.argv[idx + 1]
    else:
        report_path = run_confluence_report(report_dir)

    if not report_path or not os.path.exists(report_path):
        print("  No report file to index")
        sys.exit(1)

    pages = parse_confluence_pages(report_path)
    print(f"  Found {len(pages)} wiki pages")

    if not pages:
        print("  Nothing to index")
        return

    client = _get_client()
    model = _get_model()
    count = index_confluence_pages(pages, client, model)
    _save_snapshot(client)
    print(f"  Indexed {count} chunks from {len(pages)} wiki pages")


if __name__ == "__main__":
    main()
