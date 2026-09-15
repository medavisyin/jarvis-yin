"""Topic dedup matching must stay fast as the index grows."""
import json
import os
import sys
import tempfile

import pytest

_PIPELINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline")
)
if _PIPELINE not in sys.path:
    sys.path.insert(0, _PIPELINE)

from topic_index import TopicIndex  # noqa: E402


def _empty_index(tmp_path):
    path = str(tmp_path / "topic-index.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "last_updated": "", "topics": {}}, f)
    return TopicIndex(path=path)


def test_match_topic_does_not_sequence_match_every_topic(monkeypatch, tmp_path):
    """Incoming items must not SequenceMatcher all 300+ unrelated topics."""
    import difflib

    calls = {"n": 0}
    Real = difflib.SequenceMatcher

    class CountingMatcher(Real):
        def ratio(self, *a, **kw):
            calls["n"] += 1
            return super().ratio(*a, **kw)

    monkeypatch.setattr(difflib, "SequenceMatcher", CountingMatcher)

    idx = _empty_index(tmp_path)
    for i in range(300):
        idx.update_topic(
            f"noise-{i:04d}",
            f"Completely Unique Widget Framework Release {i} Protein",
            "2026-01-01",
            "initial",
            "Test",
        )

    result = idx.classify(
        "Quantum Protein Folding Breakthrough in CryoEM",
        "A new method maps atomic structures of membrane proteins.",
        "2026-09-10",
    )
    assert result["classification"] == "new"
    assert 1 <= calls["n"] <= 120, f"SequenceMatcher.ratio called {calls['n']} times"


def test_fuzzy_match_finds_needle_among_many_unrelated_topics(tmp_path):
    idx = _empty_index(tmp_path)
    for i in range(200):
        idx.update_topic(
            f"noise-{i:04d}",
            f"Unrelated Cloud Billing Dashboard Feature {i}",
            "2026-01-01",
            "initial",
            "Test",
        )
    idx.update_topic(
        "test-qed",
        "QED-Nano: Teaching a Tiny Model to Prove Theorems",
        "2026-04-07",
        "4B model for math proofs",
        "Arxiv AI",
    )
    result = idx.classify(
        "QED-Nano: A Small 4B Model Proves Hard Theorems",
        "4B parameter model achieves olympiad reasoning",
        "2026-04-08",
    )
    assert not result["is_new"], "Expected fuzzy match to find QED-Nano among noise"


def test_format_timeout_does_not_include_truncated_command_path():
    from topic_index import format_filter_subprocess_error

    class FakeTimeout(Exception):
        def __init__(self):
            self.timeout = 60
            self.cmd = [
                "python",
                r"C:\jarvis\scripts\pipeline\filter_topics.py",
                r"C:\reports\ai\2026-09-10\briefing-data.json",
            ]
            super().__init__(
                f"Command {self.cmd} timed out after {self.timeout} seconds"
            )

    msg = format_filter_subprocess_error(FakeTimeout(), stderr="still matching")
    assert "timed out after 60s" in msg
    assert "filter_topics.py" not in msg
    assert "C:\\reports" not in msg
    assert "still matching" in msg


def test_topic_dedup_timeout_constant_is_at_least_180():
    from topic_index import TOPIC_DEDUP_TIMEOUT_SECONDS

    assert TOPIC_DEDUP_TIMEOUT_SECONDS >= 180


def test_daily_fetch_uses_shared_dedup_timeout():
    src_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "scripts",
            "rag",
            "routes",
            "daily_fetch.py",
        )
    )
    src = open(src_path, encoding="utf-8").read()
    assert "TOPIC_DEDUP_TIMEOUT_SECONDS" in src
    assert src.count("timeout=TOPIC_DEDUP_TIMEOUT_SECONDS") >= 2


def test_fuzzy_match_uses_newest_aliases_not_oldest_eight(tmp_path):
    idx = _empty_index(tmp_path)
    idx.update_topic(
        "mega",
        "Zebra Unrelated Canonical Title About Banking",
        "2026-01-01",
        "initial",
        "Test",
    )
    for i in range(8):
        idx.update_topic(
            "mega",
            f"Old Alias Number {i} Completely Different Wording",
            "2026-01-02",
            "initial",
            "Test",
        )
    idx.update_topic(
        "mega",
        "Anthropic Ships New Constitutional Classifiers For Claude",
        "2026-01-03",
        "initial",
        "Test",
    )
    result = idx.classify(
        "Anthropic Ships Constitutional Classifiers Update For Claude",
        "",
        "2026-01-04",
    )
    assert not result["is_new"], "Expected match via newest alias, not oldest-eight cap"


def test_refetch_ai_block_formats_filter_errors():
    src_path = os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "scripts",
            "rag",
            "routes",
            "daily_fetch.py",
        )
    )
    src = open(src_path, encoding="utf-8").read()
    idx = src.find('if _should_run("refetch_ai")')
    assert idx != -1
    start = src.find("Running topic deduplication on fresh data", idx)
    assert start != -1
    inner_except = src.find("except Exception as e:", start)
    assert inner_except != -1
    outer_except = src.find("except Exception as e:", inner_except + 1)
    assert outer_except != -1
    block = src[start:outer_except]
    assert "format_filter_subprocess_error" in block
    assert '"step": "topic_dedup"' in block
    assert "format_filter_subprocess_error(e, err)" in block
