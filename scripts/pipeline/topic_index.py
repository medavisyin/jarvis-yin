"""
Topic Index Manager — tracks topics across daily AI briefings.

Maintains a persistent JSON index at C:/reports/ai/topic-index.json that records
every topic seen across briefing runs. Used by filter-topics.py to deduplicate
items that appear for multiple consecutive days without new information.

Usage as library:
    from topic_index import TopicIndex
    idx = TopicIndex()
    classification = idx.classify("HI-MoE: Hierarchical...", "MoE for object detection...")
    idx.update("topic-hash", "2026-04-08", "Applied MoE to vision", "Arxiv ML")
    idx.save()

Usage as CLI (for testing):
    python topic-index.py --test
    python topic-index.py --dump          # Print current index
    python topic-index.py --stats         # Print summary statistics
"""
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import TOPIC_INDEX_PATH

INDEX_PATH = TOPIC_INDEX_PATH
SIMILARITY_THRESHOLD = 0.55
STALE_DAYS = 1


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for comparison."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_keywords(text: str) -> set:
    """Extract significant words (>3 chars) for keyword overlap matching."""
    stop = {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'they',
            'their', 'what', 'when', 'where', 'which', 'about', 'into',
            'more', 'than', 'also', 'just', 'only', 'very', 'some', 'each',
            'most', 'other', 'such', 'these', 'those', 'both', 'does', 'were',
            'being', 'would', 'could', 'should', 'after', 'before', 'between',
            'under', 'over', 'through', 'during', 'paper', 'model', 'models',
            'using', 'based', 'approach', 'method', 'system', 'systems',
            'learning', 'data', 'new', 'first', 'show', 'propose', 'proposed'}
    words = set(_normalize(text).split())
    return {w for w in words if len(w) > 3 and w not in stop}


def _topic_hash(title: str) -> str:
    """Generate a stable hash for a topic title."""
    normalized = _normalize(title)
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


class TopicIndex:
    def __init__(self, path: str = INDEX_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": 1, "last_updated": "", "topics": {}}

    def save(self):
        self.data["last_updated"] = date.today().isoformat()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @property
    def topics(self) -> Dict[str, dict]:
        return self.data.get("topics", {})

    def match_topic(self, title: str, summary: str = "") -> Tuple[Optional[str], bool]:
        """
        Find a matching topic in the index.
        Returns (topic_id, is_new). If no match, topic_id is a new hash and is_new=True.
        """
        norm_title = _normalize(title)
        new_keywords = _extract_keywords(title + " " + (summary or ""))

        best_id = None
        best_score = 0.0

        for tid, topic in self.topics.items():
            canon = _normalize(topic["canonical_title"])
            title_sim = difflib.SequenceMatcher(None, norm_title, canon).ratio()

            for alias in topic.get("aliases", []):
                alias_sim = difflib.SequenceMatcher(None, norm_title, _normalize(alias)).ratio()
                title_sim = max(title_sim, alias_sim)

            existing_keywords = set()
            for alias in [topic["canonical_title"]] + topic.get("aliases", []):
                existing_keywords |= _extract_keywords(alias)
            if new_keywords and existing_keywords:
                overlap = len(new_keywords & existing_keywords)
                total = min(len(new_keywords), len(existing_keywords))
                keyword_sim = overlap / total if total > 0 else 0
            else:
                keyword_sim = 0

            combined = 0.6 * title_sim + 0.4 * keyword_sim

            if combined > best_score:
                best_score = combined
                best_id = tid

        if best_score >= SIMILARITY_THRESHOLD and best_id:
            return best_id, False

        new_id = _topic_hash(title)
        return new_id, True

    def update_topic(self, topic_id: str, title: str, today: str,
                     delta: str, source: str):
        """Add or update a topic entry."""
        if topic_id in self.topics:
            topic = self.topics[topic_id]
            topic["last_seen"] = today
            topic["mention_count"] += 1
            if today not in topic["mention_dates"]:
                topic["mention_dates"].append(today)
            if source not in topic["sources"]:
                topic["sources"].append(source)
            if not any(a.lower() == _normalize(title) for a in
                       [topic["canonical_title"]] + topic.get("aliases", [])):
                topic.setdefault("aliases", []).append(title)
            topic["summary_evolution"].append({"date": today, "delta": delta})
            if delta and delta.lower() not in ("no significant new information",
                                                "no new info", "stale", ""):
                topic["last_significant_update"] = today
                topic["status"] = "updated"
            else:
                topic["status"] = "continuing"
        else:
            self.topics[topic_id] = {
                "id": topic_id,
                "canonical_title": title,
                "aliases": [],
                "first_seen": today,
                "last_seen": today,
                "mention_count": 1,
                "mention_dates": [today],
                "sources": [source],
                "summary_evolution": [{"date": today, "delta": delta}],
                "status": "new",
                "last_significant_update": today,
            }

    def classify(self, title: str, summary: str = "",
                 today: str = None) -> dict:
        """
        Classify an item as new, updated, or stale.

        Returns dict with:
          topic_id, is_new, classification ("new"|"updated"|"stale"),
          days_since_first, mention_count, tag (for display)
        """
        today = today or date.today().isoformat()
        topic_id, is_new = self.match_topic(title, summary)

        if is_new:
            return {
                "topic_id": topic_id,
                "is_new": True,
                "classification": "new",
                "days_since_first": 0,
                "mention_count": 0,
                "tag": "[NEW]",
            }

        topic = self.topics[topic_id]
        first = topic["first_seen"]
        days = (datetime.fromisoformat(today) - datetime.fromisoformat(first)).days
        count = topic["mention_count"]

        last_sig = topic.get("last_significant_update", first)
        days_since_sig = (datetime.fromisoformat(today) - datetime.fromisoformat(last_sig)).days

        last_seen = topic["last_seen"]
        gap = (datetime.fromisoformat(today) - datetime.fromisoformat(last_seen)).days

        if gap > 3:
            return {
                "topic_id": topic_id,
                "is_new": False,
                "classification": "updated",
                "days_since_first": days,
                "mention_count": count,
                "tag": f"[RETURNING after {gap} days]",
            }

        if self._has_new_info(title, summary, topic):
            return {
                "topic_id": topic_id,
                "is_new": False,
                "classification": "updated",
                "days_since_first": days,
                "mention_count": count,
                "tag": f"[UPDATED \u2014 day {days + 1}]",
            }

        return {
            "topic_id": topic_id,
            "is_new": False,
            "classification": "stale",
            "days_since_first": days,
            "mention_count": count,
            "tag": f"[Still trending \u2014 day {days + 1}, no new info]",
        }

    def _has_new_info(self, title: str, summary: str, topic: dict) -> bool:
        """
        Heuristic: does this mention contain genuinely new information?
        Compares keywords in the new title+summary against all previous deltas.
        """
        if not summary:
            return False

        new_kw = _extract_keywords(title + " " + summary)
        old_kw = set()
        for ev in topic.get("summary_evolution", []):
            old_kw |= _extract_keywords(ev.get("delta", ""))
        old_kw |= _extract_keywords(topic["canonical_title"])
        for alias in topic.get("aliases", []):
            old_kw |= _extract_keywords(alias)

        if not new_kw:
            return False

        novel = new_kw - old_kw
        novelty_ratio = len(novel) / len(new_kw) if new_kw else 0
        return novelty_ratio > 0.3

    def get_stale_topics(self, today: str = None, days: int = STALE_DAYS) -> List[dict]:
        today = today or date.today().isoformat()
        stale = []
        for tid, topic in self.topics.items():
            last = topic["last_seen"]
            gap = (datetime.fromisoformat(today) - datetime.fromisoformat(last)).days
            if gap >= days:
                stale.append(topic)
        return stale

    def stats(self) -> dict:
        topics = self.topics
        if not topics:
            return {"total": 0}
        today = date.today().isoformat()
        active = sum(1 for t in topics.values()
                     if (datetime.fromisoformat(today) -
                         datetime.fromisoformat(t["last_seen"])).days <= 3)
        return {
            "total": len(topics),
            "active_last_3_days": active,
            "oldest": min(t["first_seen"] for t in topics.values()),
            "newest": max(t["last_seen"] for t in topics.values()),
        }


def _run_tests():
    """Self-test suite."""
    import tempfile
    print("=== Topic Index Tests ===\n")
    passed = 0
    failed = 0

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp_path = f.name
        json.dump({"version": 1, "last_updated": "", "topics": {}}, f)

    try:
        idx = TopicIndex(path=tmp_path)

        # Test 1: New topic classification
        result = idx.classify("HI-MoE: Hierarchical Instance-Conditioned MoE",
                              "MoE for object detection", "2026-04-07")
        assert result["classification"] == "new", f"Expected 'new', got '{result['classification']}'"
        print(f"  [PASS] Test 1: New topic classified as 'new'")
        passed += 1

        # Register the topic
        idx.update_topic(result["topic_id"],
                         "HI-MoE: Hierarchical Instance-Conditioned MoE",
                         "2026-04-07", "Introduced MoE for object detection", "Arxiv ML")

        # Test 2: Same topic next day, same info → stale
        result2 = idx.classify("HI-MoE: Hierarchical Instance-Conditioned MoE",
                               "MoE for object detection with two-level routing",
                               "2026-04-08")
        assert result2["classification"] == "stale", f"Expected 'stale', got '{result2['classification']}'"
        assert not result2["is_new"]
        print(f"  [PASS] Test 2: Same topic, same info -> 'stale'")
        passed += 1

        # Test 3: Same topic with genuinely new information -> updated
        # Use same core title but with new content about benchmark results
        idx.update_topic(result["topic_id"],
                         "HI-MoE: Hierarchical Instance-Conditioned MoE",
                         "2026-04-07", "Introduced MoE for object detection", "Arxiv ML")
        result3 = idx.classify(
            "HI-MoE: Hierarchical Instance-Conditioned Mixture-of-Experts Achieves SOTA",
            "HI-MoE achieves state-of-the-art results on COCO benchmark with 47.3 mAP, "
            "outperforming previous dense models by 2.1 points while using 40% fewer FLOPs. "
            "New ablation study reveals scene router contributes 60% of the performance gain. "
            "Released pretrained weights and inference code on GitHub.",
            "2026-04-08")
        assert result3["classification"] == "updated", f"Expected 'updated', got '{result3['classification']}'"
        print(f"  [PASS] Test 3: Same topic, new info -> 'updated'")
        passed += 1

        # Test 4: Completely different topic → new
        result4 = idx.classify("Quantum Computing for Drug Discovery",
                               "Using quantum algorithms for molecular simulation",
                               "2026-04-08")
        assert result4["classification"] == "new", f"Expected 'new', got '{result4['classification']}'"
        print(f"  [PASS] Test 4: Different topic -> 'new'")
        passed += 1

        # Test 5: Fuzzy matching with different wording
        idx.update_topic("test-qed", "QED-Nano: Teaching a Tiny Model to Prove Theorems",
                         "2026-04-07", "4B model for math proofs", "Arxiv AI")
        result5 = idx.classify("QED-Nano: A Small 4B Model Proves Hard Theorems",
                               "4B parameter model achieves olympiad reasoning",
                               "2026-04-08")
        assert not result5["is_new"], "Expected fuzzy match to find existing topic"
        print(f"  [PASS] Test 5: Fuzzy title matching works")
        passed += 1

        # Test 6: Topic returning after gap
        idx.update_topic("test-gap", "AlphaFold Protein Structure Prediction",
                         "2026-03-20", "Initial release", "DeepMind")
        result6 = idx.classify("AlphaFold Protein Structure Prediction",
                               "Major update to protein folding model",
                               "2026-04-08")
        assert result6["classification"] == "updated", f"Expected 'updated' (returning), got '{result6['classification']}'"
        assert "RETURNING" in result6["tag"]
        print(f"  [PASS] Test 6: Topic returning after gap -> 'updated' with RETURNING tag")
        passed += 1

        # Test 7: Save and reload
        idx.save()
        idx2 = TopicIndex(path=tmp_path)
        assert len(idx2.topics) == len(idx.topics)
        print(f"  [PASS] Test 7: Save and reload preserves data")
        passed += 1

        # Test 8: Stats
        stats = idx.stats()
        assert stats["total"] > 0
        print(f"  [PASS] Test 8: Stats returns valid data (total={stats['total']})")
        passed += 1

    finally:
        os.unlink(tmp_path)

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return failed == 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        success = _run_tests()
        sys.exit(0 if success else 1)
    elif "--dump" in sys.argv:
        idx = TopicIndex()
        print(json.dumps(idx.data, indent=2, ensure_ascii=False))
    elif "--stats" in sys.argv:
        idx = TopicIndex()
        stats = idx.stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")
    else:
        print("Usage:")
        print("  python topic-index.py --test   Run self-tests")
        print("  python topic-index.py --dump   Print current index")
        print("  python topic-index.py --stats  Print summary statistics")
