"""
Parse donor profiles from a saved Cryos International HTML page.
Uses BeautifulSoup to extract donor cards and their properties.
Saves structured JSON and indexes into RAG.

Usage: python parse-cryos-donors.py [path-to-html]
"""

import json, os, re, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import REPORTS_ROOT, SNAPSHOT_PATH as _SNAPSHOT_PATH_STR

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HTML_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(
        REPORTS_ROOT,
        "cryos",
        "Find a sperm donor \u2192 Free donor search _ Cryos.html",
    )
)
REPORTS_ROOT_PATH = Path(REPORTS_ROOT)
TODAY = datetime.now().strftime("%Y-%m-%d")
OUTPUT_DIR = REPORTS_ROOT_PATH / TODAY
OUTPUT_FILE = OUTPUT_DIR / "cryos-donors.json"
SNAPSHOT_PATH = Path(_SNAPSHOT_PATH_STR)
COLLECTION = "jarvis_docs"
VECTOR_SIZE = 384

KNOWN_KEYS = {
    "shipped from", "cryos face matching", "adult photo", "genetic matching",
    "race", "hair colour", "eye colour", "ethnicity", "height (cm)", "blood type",
    "cmv status", "rep. pregnancy", "motility", "weight (kg)", "skin tone",
    "education", "profession", "id release", "id option",
}


def parse_donor_card(card_el) -> dict | None:
    """Extract donor properties from a card element."""
    from bs4 import NavigableString

    text_parts = card_el.get_text(separator="|", strip=True).split("|")
    text_parts = [p.strip() for p in text_parts if p.strip()]

    if len(text_parts) < 5:
        return None

    donor = {}

    profile_type = text_parts[0] if text_parts[0] in ("Basic", "Extended") else "Unknown"
    donor["profile_type"] = profile_type

    donor_id = text_parts[1] if len(text_parts) > 1 else ""
    if donor_id == "ID Release":
        donor_id = text_parts[1] if text_parts[0] not in ("Basic", "Extended") else ""
    donor["donor_id"] = ""

    for i, part in enumerate(text_parts):
        if part not in ("Basic", "Extended", "ID Release", "View more on profile",
                        "Buy now", "Reserve for later", "Price coming soon",
                        "There are quotas available in your country",
                        "Yes", "No", "ICI/IUI", "IUI-ready"):
            if i > 0 and i < len(text_parts) - 1:
                continue
        low = part.lower()
        if low in KNOWN_KEYS and i + 1 < len(text_parts):
            key = re.sub(r'[^a-z0-9_]', '_', low).strip('_')
            val = text_parts[i + 1]
            if val.lower() not in KNOWN_KEYS and val not in ("Buy now", "Reserve for later"):
                donor[key] = val

    i = 0
    while i < len(text_parts):
        low = text_parts[i].lower()
        if low in KNOWN_KEYS and i + 1 < len(text_parts):
            key = re.sub(r'[^a-z0-9_]', '_', low).strip('_')
            val = text_parts[i + 1]
            if val.lower() not in KNOWN_KEYS:
                donor[key] = val
            i += 2
        else:
            i += 1

    link = card_el.find("a", href=re.compile(r"donor-profile"))
    if link:
        href = link.get("href", "")
        donor["url"] = href
        name_match = re.search(r'[?&]name=([^&]+)', href)
        if name_match:
            donor["donor_id"] = name_match.group(1)

    if not donor.get("donor_id"):
        for part in text_parts[1:5]:
            if part and part not in ("Basic", "Extended", "ID Release") and len(part) < 20:
                donor["donor_id"] = part
                break

    if not donor.get("donor_id") and not donor.get("race"):
        return None

    return donor


def run():
    from bs4 import BeautifulSoup

    print(f"[1/4] Reading HTML...", flush=True)
    html = Path(HTML_PATH).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    print(f"  HTML loaded ({len(html):,} chars)", flush=True)

    print("[2/4] Extracting donor profiles...", flush=True)

    donor_links = soup.select("a[href*='donor-profile']")
    print(f"  Found {len(donor_links)} donor profile links", flush=True)

    cards = soup.select("[class*='filter-page-info-card']")
    print(f"  Found {len(cards)} card elements", flush=True)

    donors = []
    seen_ids = set()

    for card in cards:
        link = card.find("a", href=re.compile(r"donor-profile"))
        if not link:
            continue

        href = link.get("href", "")
        name_match = re.search(r'[?&]name=([^&]+)', href)
        donor_id = name_match.group(1) if name_match else ""

        if not donor_id or donor_id in seen_ids:
            continue
        seen_ids.add(donor_id)

        text_parts = card.get_text(separator="|", strip=True).split("|")
        text_parts = [p.strip() for p in text_parts if p.strip()]

        donor = {"donor_id": donor_id, "url": href}

        if text_parts and text_parts[0] in ("Basic", "Extended"):
            donor["profile_type"] = text_parts[0]

        i = 0
        while i < len(text_parts):
            low = text_parts[i].lower()
            if low in KNOWN_KEYS and i + 1 < len(text_parts):
                key = re.sub(r'[^a-z0-9_]', '_', low).strip('_')
                val = text_parts[i + 1]
                if val.lower() not in KNOWN_KEYS and val not in (
                    "Buy now", "Reserve for later", "Price coming soon",
                    "View more on profile"
                ):
                    donor[key] = val
                i += 2
            else:
                i += 1

        stock = []
        for i, part in enumerate(text_parts):
            if part.startswith("MOT"):
                mot_type = part
                details = text_parts[i+1:i+5] if i+4 < len(text_parts) else []
                stock.append({"type": mot_type, "details": " ".join(details)})
        if stock:
            donor["stock"] = stock

        donors.append(donor)

    print(f"  Extracted {len(donors)} unique donors", flush=True)

    if donors:
        sample = donors[0]
        print(f"  Sample: {json.dumps(sample, ensure_ascii=False)[:300]}", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(donors, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[3/4] Saved {len(donors)} donors to {OUTPUT_FILE}", flush=True)

    props_found = set()
    for d in donors:
        props_found.update(k for k in d.keys() if k not in ("donor_id", "url", "stock", "profile_type"))
    print(f"  Properties found: {sorted(props_found)}", flush=True)

    shipped_from = {}
    for d in donors:
        sf = d.get("shipped_from", "unknown")
        shipped_from[sf] = shipped_from.get(sf, 0) + 1
    print(f"  Shipped from distribution: {shipped_from}", flush=True)

    index_to_rag(donors)


def index_to_rag(donors: list[dict]):
    if not donors:
        return

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  RAG indexing skipped (sentence-transformers not installed)", flush=True)
        return

    print(f"[4/4] Indexing {len(donors)} donors into RAG...", flush=True)
    model = SentenceTransformer("all-MiniLM-L6-v2")

    if SNAPSHOT_PATH.exists():
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        existing_points = snapshot.get("points", [])
    else:
        existing_points = []
        snapshot = {"collection": COLLECTION, "vector_size": VECTOR_SIZE, "points": []}

    existing_titles = set()
    for pt in existing_points:
        if pt.get("payload", {}).get("item_type") == "donor_profile":
            existing_titles.add(pt["payload"].get("title", ""))

    numeric_ids = [p["id"] for p in existing_points if isinstance(p["id"], (int, float))]
    max_id = max(numeric_ids, default=0)
    new_points = []

    for donor in donors:
        did = donor.get("donor_id", "")
        title = f"Cryos Donor {did}"

        if title in existing_titles:
            continue

        props = []
        for k, v in donor.items():
            if k in ("url", "stock"):
                continue
            if v is not None and str(v).strip():
                label = k.replace("_", " ").title()
                props.append(f"{label}: {v}")

        if donor.get("stock"):
            stock_lines = []
            for s in donor["stock"]:
                stock_lines.append(f"{s['type']}: {s['details']}")
            props.append("Stock: " + "; ".join(stock_lines))

        text = "\n".join(props)
        embedding = model.encode(text).tolist()
        point_id = max_id + len(new_points) + 1

        new_points.append({
            "id": point_id,
            "vector": embedding,
            "payload": {
                "title": title,
                "text": text,
                "source": "cryos_international",
                "item_type": "donor_profile",
                "date": TODAY,
                "url": donor.get("url", ""),
                "donor_data": donor,
            }
        })

    if new_points:
        all_points = existing_points + new_points
        snapshot["points"] = all_points
        SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        print(f"  Indexed {len(new_points)} new donor profiles. Total RAG points: {len(all_points)}", flush=True)
    else:
        print("  All donors already indexed.", flush=True)


if __name__ == "__main__":
    run()
