import sys, os
sys.path.insert(0, r"C:\jarvis\scripts\rag")
os.chdir(r"C:\jarvis\scripts\rag")

from routes.ai_news import _generate_segmented_narrations

test_segments = [{
    "name": "OpenAI Developer Blog",
    "content": (
        "GPT-5.5 Instant System Card\n"
        "GPT-5.5 Instant is the latest model with improved safety mitigations and faster inference.\n\n"
        "Introducing ChatGPT Futures: Class of 2026\n"
        "A new program training the next generation of AI researchers and builders.\n\n"
        "How frontier enterprises are building an AI advantage\n"
        "Enterprise adoption of AI is accelerating with new deployment patterns."
    ),
}]

print("Generating narration with MANDATORY vocabulary teaching (lang=en)...")
print("=" * 60)
narrations = _generate_segmented_narrations(test_segments, "ai", lang="en")
if narrations:
    text = narrations[0]
    print(text[:3000])
    print("=" * 60)
    print(f"Total: {len(text)} chars")

    # Count vocabulary explanations (word — explanation — pattern)
    import re
    dash_explanations = re.findall(r'[\u2014\u2013—–-]{1,3}\s*(?:meaning|that is|an idiom|in other words|which means|refers to|essentially|the act of|a term|i\.e\.|that means|to put it simply)', text, re.IGNORECASE)
    simple_dashes = re.findall(r'\w+\s*[\u2014\u2013—–-]{1,3}\s*\w+', text)
    print(f"\nVocab explanations with keywords: {len(dash_explanations)}")
    print(f"Dash patterns total: {len(simple_dashes)}")
    for d in dash_explanations:
        print(f"  Found: ...{d.strip()[:60]}...")
else:
    print("ERROR: No narration generated!")
