"""
Confluence User Wiki Indexer — fetches all wiki pages from a specific user
and indexes them into the RAG store.

Usage:
  python index_confluence_user.py "Jan Loeffler"
  python index_confluence_user.py "Jan Loeffler" --limit 200

Dependencies: pip install qdrant-client sentence-transformers requests
"""
import json
import os
import re
import sys
import uuid
import base64
import time
from datetime import date
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import SNAPSHOT_PATH

COLLECTION = "ai_briefings"
VECTOR_SIZE = 384

SITE = os.environ.get("ATLASSIAN_SITE", "")
EMAIL = os.environ.get("ATLASSIAN_EMAIL", "")
TOKEN = os.environ.get("ATLASSIAN_API_TOKEN", "")

if not SITE or not EMAIL or not TOKEN:
    print("ERROR: Set ATLASSIAN_SITE, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN env vars")
    sys.exit(1)

_AUTH = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
_HEADERS = {"Authorization": f"Basic {_AUTH}", "Accept": "application/json"}

KNOWN_ACCOUNTS = {
    "raymond shen": "712020:369e5fbe-a6fa-41c4-b613-627278451b0c",
    "charlotte jiang": "712020:1d619c3c-b980-4bac-9966-ee62b9f7bd11",
    "christoph scheben": "712020:f85eabdc-dd64-43d1-afa6-72c9c6b65f11",
    "tobias troesch": "712020:4babc3e7-a282-4e31-a84b-233078fdd451",
    "jan loeffler": "712020:afcd5f1a-f4d5-40c2-a255-f62c7e484cb6",
    "belen liu": "712020:a39aa165-843d-4631-85fe-b6c094da726f",
    "bin si": "712020:b81b3b34-ef7d-41ba-a9c7-0784ea6f0d45",
    "deniz erginos": "712020:85afed05-bd1c-4c36-9c54-63fec91cfcd2",
    "djilija vranic": "712020:24e32160-837f-4275-a513-792cfd1bee31",
    "dominik kowalski": "712020:2179fd11-51f5-4c43-a9d2-c4adb282f331",
    "eatin yang": "712020:4455d3c6-cba9-4eba-86a9-0715bbee4805",
    "ehsan esmaili": "712020:e209de68-b37d-4910-8299-ae28f8dab1cf",
    "emrys macinally": "712020:db12f928-04d9-4a01-bf0d-12a7d7097202",
    "erik zweier": "615d8c4c64ff01007162a78c",
    "holger pflüger": "557058:0464ed0d-6aee-4c55-8a52-074b1ffccd4e",
    "martin leim": "712020:0b0f52b7-346a-4578-bb12-f7625de19a36",
    "mathias stümpert": "712020:a7b18c84-36a1-4898-af5c-09e412d36c82",
    "michael mauer": "557058:8a64c2d5-6504-45cf-9e3e-156f75e0fe9c",
    "patrick höhle": "712020:2a38f88d-415d-4cf8-9943-ecea8c0ee966",
    "quan cheng": "712020:7caeb6c9-a491-439e-95f1-078fb8e451a0",
    "samer abdalla": "712020:e5513810-b722-4261-846c-8f6614b81688",
    "steffen eitelmann": "712020:c3653d9a-da23-48e7-b662-0f111e99689e",
    "tamino fischer": "712020:f9b7c699-b9b3-49e3-a3a7-c120ebe2fe58",
    "thomas freier": "557058:2139f1e3-be15-4ab2-99f7-ddaf1514ca28",
    "thomas simon": "712020:c7b9dda3-d167-4b07-b31f-6ddc49c3705f",
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
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=True, with_vectors=True,
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
    print(f"  Loaded {len(points)} existing points from snapshot")


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


def _strip_html(html: str) -> str:
    if not html:
        return ""
    import html as html_mod
    text = html_mod.unescape(html)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_headings(html: str, max_count: int = 8) -> List[str]:
    if not html:
        return []
    headings = []
    for m in re.finditer(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.IGNORECASE | re.DOTALL):
        h = _strip_html(m.group(1))
        if h and h not in headings:
            headings.append(h)
            if len(headings) >= max_count:
                break
    return headings


def _fetch_previous_version_text(page_id: str, current_version: int) -> str:
    """Fetch the plain text of the previous version of a page.
    Returns empty string if version <= 1 or fetch fails."""
    if current_version <= 1:
        return ""
    prev_version = current_version - 1
    try:
        import requests
        url = (f"https://{SITE}/wiki/rest/api/content/{page_id}"
               f"?expand=body.storage&status=historical&version={prev_version}")
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        body_data = r.json()
        storage_html = body_data.get("body", {}).get("storage", {}).get("value", "")
        return _strip_html(storage_html)
    except Exception:
        return ""


def _compute_change_summary(current_text: str, previous_text: str) -> str:
    """Compute a concise text diff summary between previous and current page versions."""
    import difflib

    prev_lines = previous_text.splitlines()
    curr_lines = current_text.splitlines()
    diff = list(difflib.unified_diff(prev_lines, curr_lines, n=0))

    added_lines = [line[1:].strip() for line in diff
                   if line.startswith("+") and not line.startswith("+++")]
    removed_lines = [line[1:].strip() for line in diff
                     if line.startswith("-") and not line.startswith("---")]
    added_lines = [l for l in added_lines if l]
    removed_lines = [l for l in removed_lines if l]

    if not added_lines and not removed_lines:
        return ""

    parts = []
    if added_lines:
        added_preview = " | ".join(added_lines[:5])
        if len(added_preview) > 500:
            added_preview = added_preview[:500] + "..."
        parts.append(f"Added ({len(added_lines)} lines): {added_preview}")
    if removed_lines:
        removed_preview = " | ".join(removed_lines[:3])
        if len(removed_preview) > 300:
            removed_preview = removed_preview[:300] + "..."
        parts.append(f"Removed ({len(removed_lines)} lines): {removed_preview}")

    return "\n".join(parts)


def _safe_print(text: str):
    """Print text safely, replacing non-ASCII chars for Windows console."""
    print(text.encode("ascii", "replace").decode())


def _search_user(display_name: str) -> str:
    """Search for a Confluence user by display name, return accountId."""
    import requests

    url = f"https://{SITE}/rest/api/3/user/search?query={display_name.replace(' ', '+')}&maxResults=10"
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        for u in r.json():
            name = u.get("displayName", "")
            if display_name.lower() in name.lower():
                return u.get("accountId", "")
    except Exception:
        pass
    return ""


def fetch_user_pages_cql(display_name: str, limit: int = 200,
                         date_from: str = "", date_to: str = "") -> List[dict]:
    """Fast CQL-based fetch of Confluence pages by a user, with optional date range."""
    import requests

    name_lower = display_name.lower()
    account_id = KNOWN_ACCOUNTS.get(name_lower, "")
    if not account_id:
        print(f"  Searching for user: {display_name}")
        account_id = _search_user(display_name)
    if not account_id:
        print(f"  ERROR: Could not find account for '{display_name}'")
        return []
    print(f"  Account: {account_id}")

    cql_parts = [f'creator = "{account_id}"', 'type = "page"']
    if date_from:
        cql_parts.append(f'lastModified >= "{date_from}"')
    if date_to:
        cql_parts.append(f'lastModified <= "{date_to}"')
    cql = " AND ".join(cql_parts) + " ORDER BY lastModified DESC"
    _safe_print(f"  CQL: {cql}")

    page_metas = []
    start = 0
    batch = 50
    for _ in range(100):
        url = f"https://{SITE}/wiki/rest/api/content/search"
        params = {"cql": cql, "limit": batch, "start": start,
                  "expand": "space,version"}
        try:
            r = requests.get(url, headers=_HEADERS, params=params, timeout=30)
            if r.status_code != 200:
                print(f"    CQL search returned {r.status_code}, stopping")
                break
            data = r.json()
        except Exception as e:
            print(f"    CQL search error: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for page in results:
            version = page.get("version", {})
            space = page.get("space", {})
            modified = version.get("when", "")
            page_metas.append({
                "title": page.get("title", ""),
                "page_id": page.get("id", ""),
                "space_name": space.get("name", ""),
                "space_key": space.get("key", ""),
                "url": f"https://{SITE}/wiki{page.get('_links', {}).get('webui', '')}",
                "modified_at": modified.split("T")[0] if modified else "",
                "version_number": version.get("number", 1),
            })

        if len(page_metas) >= limit:
            page_metas = page_metas[:limit]
            break
        size = data.get("size", len(results))
        total_size = data.get("totalSize", 0)
        start += size
        if start >= total_size or size < batch:
            break
        time.sleep(0.2)

    print(f"  Found {len(page_metas)} pages via CQL")
    if not page_metas:
        return []

    print(f"  Fetching body content for {len(page_metas)} pages...")
    all_pages = []
    for i, meta in enumerate(page_metas):
        page_id = meta["page_id"]
        if not page_id:
            continue
        try:
            body_url = f"https://{SITE}/wiki/rest/api/content/{page_id}?expand=body.storage"
            r = requests.get(body_url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            body_data = r.json()
            storage_html = body_data.get("body", {}).get("storage", {}).get("value", "")
        except Exception as e:
            _safe_print(f"    [{i+1}] Body fetch failed for '{meta['title']}': {e}")
            storage_html = ""

        body_text = _strip_html(storage_html)
        headings = _get_headings(storage_html)

        version_num = meta.get("version_number", 1)
        change_summary = ""
        if version_num > 1 and body_text:
            prev_text = _fetch_previous_version_text(page_id, version_num)
            if prev_text:
                change_summary = _compute_change_summary(body_text, prev_text)

        full_text = f"{meta['title']}\n\n"
        if meta["space_name"]:
            full_text += f"Space: {meta['space_name']}\n"
        full_text += f"Creator: {display_name}\n"
        if meta["modified_at"]:
            full_text += f"Last modified: {meta['modified_at']}\n"
        full_text += f"\n{body_text}"
        if headings:
            full_text += "\n\nKey sections:\n" + "\n".join(f"- {h}" for h in headings)

        all_pages.append({
            "title": meta["title"],
            "page_id": page_id,
            "url": meta["url"],
            "space": meta["space_name"],
            "space_key": meta["space_key"],
            "creator": display_name,
            "updated_when": meta["modified_at"],
            "text": full_text,
            "headings": headings,
            "summary": (body_text[:500] + "...") if len(body_text) > 500 else body_text,
            "version_number": version_num,
            "change_summary": change_summary,
        })

        if (i + 1) % 10 == 0:
            _safe_print(f"    Fetched {i+1}/{len(page_metas)} page bodies...")
            time.sleep(0.5)
        else:
            time.sleep(0.15)

    return all_pages


def fetch_user_pages(display_name: str, limit: int = 200) -> List[dict]:
    """Fetch Confluence pages authored by a user via V2 API (authorId/ownerId)."""
    import requests

    print(f"  Searching for user: {display_name}")
    account_id = _search_user(display_name)
    if not account_id:
        print(f"  ERROR: Could not find account for '{display_name}'")
        return []
    print(f"  Found account: {account_id}")

    # Phase 1: Scan V2 pages for authorId/ownerId match
    print(f"  Phase 1: Scanning pages via V2 API (target: {limit} pages)...")
    page_metas = []
    cursor = None
    pages_scanned = 0

    for batch_num in range(200):
        url = f"https://{SITE}/wiki/api/v2/pages"
        params = {"limit": 250, "status": "current", "sort": "-modified-date"}
        if cursor:
            params["cursor"] = cursor
        try:
            r = requests.get(url, headers=_HEADERS, params=params, timeout=30)
            if r.status_code != 200:
                print(f"    V2 API returned {r.status_code}, stopping scan")
                break
            data = r.json()
        except Exception as e:
            print(f"    V2 API error: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        pages_scanned += len(results)
        for page in results:
            author_id = page.get("authorId", "")
            owner_id = page.get("ownerId", "")
            last_owner_id = page.get("lastOwnerId", "")
            if account_id in (author_id, owner_id, last_owner_id):
                created_at = page.get("createdAt", "")
                version = page.get("version", {})
                modified_at = version.get("createdAt", created_at)
                page_metas.append({
                    "title": page.get("title", ""),
                    "page_id": page.get("id", ""),
                    "spaceId": page.get("spaceId", ""),
                    "url": f"https://{SITE}/wiki{page.get('_links', {}).get('webui', '')}",
                    "created_at": created_at.split("T")[0] if created_at else "",
                    "modified_at": modified_at.split("T")[0] if modified_at else "",
                })

        if len(page_metas) >= limit:
            page_metas = page_metas[:limit]
            break

        next_link = data.get("_links", {}).get("next", "")
        if not next_link:
            break
        m = re.search(r'cursor=([^&]+)', next_link)
        cursor = m.group(1) if m else None
        if not cursor:
            break

        if pages_scanned % 2500 == 0:
            _safe_print(f"    Scanned {pages_scanned} pages, found {len(page_metas)} by {display_name}...")
        time.sleep(0.3)

    _safe_print(f"  Phase 1 done: scanned {pages_scanned} pages, found {len(page_metas)} by {display_name}")

    if not page_metas:
        return []

    # Phase 2: Fetch body content for each page individually
    print(f"  Phase 2: Fetching body content for {len(page_metas)} pages...")
    all_pages = []
    for i, meta in enumerate(page_metas):
        page_id = meta["page_id"]
        if not page_id:
            continue

        try:
            body_url = f"https://{SITE}/wiki/rest/api/content/{page_id}?expand=body.storage,space"
            r = requests.get(body_url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            body_data = r.json()
            storage_html = body_data.get("body", {}).get("storage", {}).get("value", "")
            space_name = body_data.get("space", {}).get("name", "")
            space_key = body_data.get("space", {}).get("key", "")
        except Exception as e:
            _safe_print(f"    [{i+1}] Body fetch failed for '{meta['title']}': {e}")
            storage_html = ""
            space_name = ""
            space_key = ""

        body_text = _strip_html(storage_html)
        headings = _get_headings(storage_html)
        summary = (body_text[:500] + "...") if len(body_text) > 500 else body_text

        full_text = f"{meta['title']}\n\n"
        if space_name:
            full_text += f"Space: {space_name}\n"
        full_text += f"Creator: {display_name}\n"
        if meta["modified_at"]:
            full_text += f"Last modified: {meta['modified_at']}\n"
        full_text += f"\n{body_text}"
        if headings:
            full_text += "\n\nKey sections:\n" + "\n".join(f"- {h}" for h in headings)

        all_pages.append({
            "title": meta["title"],
            "page_id": page_id,
            "url": meta["url"],
            "space": space_name,
            "space_key": space_key,
            "creator": display_name,
            "updated_when": meta["modified_at"],
            "text": full_text,
            "headings": headings,
            "summary": summary,
        })

        if (i + 1) % 10 == 0:
            _safe_print(f"    Fetched {i+1}/{len(page_metas)} page bodies...")
            time.sleep(1)
        else:
            time.sleep(0.3)

    return all_pages


def index_pages(pages: List[dict], client, model) -> int:
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
                    "date": page.get("updated_when", date.today().isoformat()),
                    "source": "confluence",
                    "title": page["title"] if len(chunks) == 1 else f"{page['title']} (part {i+1})",
                    "item_type": "wiki_page",
                    "difficulty": "intermediate",
                    "url": page.get("url", ""),
                    "filename": "",
                    "parent_title": page["title"],
                    "tags": page.get("headings", []),
                    "space": page.get("space", ""),
                    "author": page.get("creator", ""),
                }
            })

    print(f"  Encoding {len(all_items)} chunks...")
    texts = [item["text"] for item in all_items]
    embeddings = model.encode(texts, show_progress_bar=len(texts) > 20)

    points = []
    for i, (item, embedding) in enumerate(zip(all_items, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"confluence-user:{item['metadata']['parent_title']}:{i}"))
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
    if len(sys.argv) < 2:
        print("Usage: python index_confluence_user.py <display-name> [--limit N] [--date-from YYYY-MM-DD] [--date-to YYYY-MM-DD] [--report-json]")
        print('Example: python index_confluence_user.py "Jan Loeffler" --date-from 2026-01-01')
        sys.exit(1)

    display_name = sys.argv[1]
    limit = 200
    date_from = ""
    date_to = ""
    report_json = "--report-json" in sys.argv
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    if "--date-from" in sys.argv:
        idx = sys.argv.index("--date-from")
        if idx + 1 < len(sys.argv):
            date_from = sys.argv[idx + 1]
    if "--date-to" in sys.argv:
        idx = sys.argv.index("--date-to")
        if idx + 1 < len(sys.argv):
            date_to = sys.argv[idx + 1]

    date_info = ""
    if date_from or date_to:
        date_info = f" (range: {date_from or '...'} to {date_to or '...'})"

    print(f"Fetching Confluence pages by '{display_name}' (limit: {limit}){date_info}...")
    t0 = time.monotonic()
    if date_from or date_to:
        pages = fetch_user_pages_cql(display_name, limit, date_from, date_to)
    else:
        pages = fetch_user_pages_cql(display_name, limit)
    fetch_seconds = round(time.monotonic() - t0, 1)
    print(f"  Found {len(pages)} pages in {fetch_seconds}s")

    if not pages:
        print("  Nothing to index")
        return

    for i, p in enumerate(pages[:5]):
        _safe_print(f"    {i+1}. {p['title']} [{p['space_key']}]")
    if len(pages) > 5:
        print(f"    ... and {len(pages) - 5} more")

    if report_json:
        import json as _json
        page_details = []
        for p in pages:
            page_details.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "space": p.get("space", "") or p.get("space_name", ""),
                "summary": p.get("summary", "")[:300],
                "headings": p.get("headings", [])[:8],
                "modified_at": p.get("updated_when", "") or p.get("modified_at", ""),
                "version_number": p.get("version_number", 1),
                "change_summary": p.get("change_summary", "")[:600],
            })
        print(f"REPORT_JSON:{_json.dumps(page_details, ensure_ascii=True)}")

    print("  Loading model and RAG store...")
    client = _get_client()
    model = _get_model()

    t1 = time.monotonic()
    count = index_pages(pages, client, model)
    index_seconds = round(time.monotonic() - t1, 1)
    _save_snapshot(client)
    print(f"\nDone: Indexed {count} chunks from {len(pages)} wiki pages by '{display_name}' in {index_seconds}s")


if __name__ == "__main__":
    main()
