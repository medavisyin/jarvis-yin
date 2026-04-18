import sys, json
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\reports\ai\2026-04-16\world-news\world-news-data.json'
d = json.load(open(path, 'r', encoding='utf-8'))

CHINA_TAG = "中国新闻"

intl_count = 0
china_count = 0
all_sources = set()

for cat in d.get('categories', []):
    label = cat['label']
    intl_items = []
    china_items = []
    for it in cat.get('items', []):
        src = it.get('source', '')
        all_sources.add(src)
        if CHINA_TAG in src:
            china_items.append(src)
        else:
            intl_items.append(src)
    intl_count += len(intl_items)
    china_count += len(china_items)
    print(f"{label}: intl={len(intl_items)}, china={len(china_items)}")

print(f"\nTotal: intl={intl_count}, china={china_count}")
print(f"All source values: {all_sources}")
