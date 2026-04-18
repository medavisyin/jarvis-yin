import sys, json
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\reports\ai\2026-04-16\world-news\world-news-data.json'
d = json.load(open(path, 'r', encoding='utf-8'))

CHINA_TAG = "中国新闻"

def pick_text(it, prefer_zh):
    if prefer_zh:
        title = it.get("title_zh") or it.get("title", "")
        summary = it.get("summary_zh") or it.get("summary", "")
    else:
        title = it.get("title", "")
        summary = it.get("summary", "")
    return title, summary

def build_segments(categories, source_filter, prefer_zh, max_per_cat=4):
    segs = []
    for cat_block in categories:
        cat_name = cat_block.get("label", "")
        parts = []
        for it in (cat_block.get("items") or []):
            src = it.get("source", "")
            if not source_filter(src):
                continue
            title, summary = pick_text(it, prefer_zh)
            if title:
                parts.append(f"{title}\n{summary}")
            if len(parts) >= max_per_cat:
                break
        if parts:
            segs.append({"name": cat_name, "content_len": sum(len(p) for p in parts), "count": len(parts)})
    return segs

categories = d.get("categories", [])

print("=== World News (international only) ===")
wn_segs = build_segments(categories, lambda s: CHINA_TAG not in s, True)
for s in wn_segs:
    print(f"  {s['name']}: {s['count']} items, {s['content_len']} chars")
total_wn = sum(s['content_len'] for s in wn_segs)
print(f"  Total content: {total_wn} chars")

print("\n=== China News only ===")
cn_segs = build_segments(categories, lambda s: CHINA_TAG in s, True, max_per_cat=6)
for s in cn_segs:
    print(f"  {s['name']}: {s['count']} items, {s['content_len']} chars")
total_cn = sum(s['content_len'] for s in cn_segs)
print(f"  Total content: {total_cn} chars")
