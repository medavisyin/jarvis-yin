"""World-news geopolitics catalog: defaults, no social heat lists, merge dedup."""

from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
for _p in (_SCRIPTS, _PIPELINE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import importlib.util

from world_sources import (  # noqa: E402
    CATEGORIES,
    load_catalog,
    load_previous_day_title_keys,
    merge_source_jsons,
    resolve_enabled,
    world_history_missing_steps,
    world_title_key,
)


def test_catalog_default_sources_are_geocodable_wires():
    catalog = load_catalog()
    default_on = {s["id"] for s in catalog if s.get("default_enabled")}
    assert default_on == {
        "bbc-news",
        "reuters",
        "ap-news",
        "dw-news",
        "guardian",
        "peoples-daily",
        "xinhua",
        "al-jazeera",
        "the-diplomat",
        "kyiv-independent",
    }
    by_id = {s["id"]: s for s in catalog}
    assert by_id["bbc-news"]["fetcher"].endswith("fetch-bbc-news.py")
    assert by_id["peoples-daily"]["fetcher"].endswith("fetch-world-rss.py")
    assert by_id["xinhua"]["fetcher"].endswith("fetch-world-rss.py")
    for sid in ("al-jazeera", "the-diplomat", "kyiv-independent"):
        assert by_id[sid]["fetcher"].endswith("fetch-world-rss.py")
        assert by_id[sid]["feeds"]


def test_catalog_excludes_weibo_toutiao_sina_cls():
    blob = json.dumps(load_catalog()).lower()
    ids = {s["id"] for s in load_catalog()}
    assert "weibo" not in ids
    assert "toutiao" not in ids
    assert "weibo" not in blob
    assert "toutiao" not in blob
    assert "cls" not in ids
    assert "sina" not in ids


def test_categories_are_map_relevant():
    assert [c["id"] for c in CATEGORIES] == [
        "politics",
        "economics",
        "technology",
        "science",
    ]


def test_resolve_enabled_uses_world_sources_enabled():
    catalog = load_catalog()
    enabled = resolve_enabled(catalog, settings={})
    assert "bbc-news" in enabled
    enabled2 = resolve_enabled(
        catalog,
        settings={"world_sources_enabled": {"bbc-news": False, "xinhua": True}},
    )
    assert "bbc-news" not in enabled2
    assert "xinhua" in enabled2


def test_merge_dedupes_title_keeps_unavailable(tmp_path):
    (tmp_path / "bbc-news.json").write_text(
        json.dumps({
            "items": [
                {"title": "NATO meets in Brussels", "summary": "Summit", "category": "politics"},
                {"title": "NATO meets in Brussels", "summary": "dup", "category": "politics"},
            ]
        }),
        encoding="utf-8",
    )
    merged = merge_source_jsons(str(tmp_path), "2026-09-20", enabled_ids=["bbc-news", "reuters"])
    assert merged["total_items"] == 1
    assert "BBC World News" in merged["sources_used"]
    assert "Reuters" in merged["sources_unavailable"]
    assert merged["categories"][0]["category"] == "politics"


def test_merge_drops_yesterday_titles(tmp_path):
    today = tmp_path / "2026-09-20" / "world-news"
    yday = tmp_path / "2026-09-19" / "world-news"
    today.mkdir(parents=True)
    yday.mkdir(parents=True)
    (yday / "world-news-data.json").write_text(
        json.dumps({
            "categories": [{"category": "politics", "items": [{"title": "Old Brussels summit"}]}]
        }),
        encoding="utf-8",
    )
    (today / "bbc-news.json").write_text(
        json.dumps({
            "items": [
                {"title": "Old Brussels summit", "category": "politics"},
                {"title": "New Kyiv strike", "category": "politics"},
            ]
        }),
        encoding="utf-8",
    )
    keys = load_previous_day_title_keys(str(today), "2026-09-20")
    assert world_title_key("Old Brussels summit") in keys
    merged = merge_source_jsons(str(today), "2026-09-20", enabled_ids=["bbc-news"])
    titles = [it["title"] for cat in merged["categories"] for it in cat["items"]]
    assert titles == ["New Kyiv strike"]


def test_run_world_news_merge_news_accepts_report_date(tmp_path):
    (tmp_path / "bbc-news.json").write_text(
        json.dumps({"items": [{"title": "Kyiv", "category": "politics"}]}),
        encoding="utf-8",
    )
    script = os.path.join(_PIPELINE, "run-world-news.py")
    spec = importlib.util.spec_from_file_location("run_world_news", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    merged = mod.merge_news(str(tmp_path), report_date="2026-09-20")
    assert merged["total_items"] == 1
    assert merged["report_date"] == "2026-09-20"


def test_run_all_sources_has_world_news_phase():
    path = os.path.join(_PIPELINE, "run-all-sources.py")
    src = open(path, encoding="utf-8").read()
    assert "run-world-news.py" in src
    assert "world-news" in src
    assert "--no-translate" in src


def test_daily_fetch_wires_world_news_steps_and_api():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    for token in (
        "world_news_merge",
        "world_news_translate",
        "refetch_world",
        "/api/toolbar/world-sources",
        "world_sources_enabled",
        "world_news_items",
        "run-world-news.py",
        "world_history_missing_steps",
    ):
        assert token in src, f"missing {token} in daily_fetch.py"


def test_fetch_sources_timeout_covers_world_phase_6():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    marker = 'run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")'
    idx = src.find(marker)
    assert idx != -1
    chunk = src[idx:idx + 900]
    assert "timeout=2400" in chunk


def test_world_merge_already_done_not_registered():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert '"world_news_merge": lambda' not in src
    assert '_already_done("world_news_merge")' not in src


def test_regional_rss_use_publisher_hosts_not_worldmonitor():
    catalog = {s["id"]: s for s in load_catalog()}
    expected_hosts = {
        "al-jazeera": "aljazeera.com",
        "the-diplomat": "thediplomat.com",
        "kyiv-independent": "kyivindependent.com",
    }
    blob = json.dumps(load_catalog()).lower()
    assert "worldmonitor.app" not in blob
    assert "_feeds.ts" not in blob
    for sid, host in expected_hosts.items():
        urls = [u for _c, u in catalog[sid].get("feeds") or []]
        assert urls, sid
        assert all(host in u.lower() for u in urls), (sid, urls)
        assert all("news.google.com" not in u.lower() for u in urls)


def test_xinhua_rss_feeds_are_not_dead_world_xml():
    xinhua = next(s for s in load_catalog() if s["id"] == "xinhua")
    urls = [u for _c, u in xinhua.get("feeds") or []]
    assert urls
    assert all("/rss/world.xml" not in u for u in urls)
    blob = " ".join(urls)
    assert "news_politics.xml" in blob
    assert "worldrss.xml" in blob


def test_world_missing_steps_old_date_without_dir(tmp_path):
    date_dir = tmp_path / "2026-08-01"
    date_dir.mkdir()
    assert world_history_missing_steps(str(date_dir), "2026-08-01", today="2026-09-20") == []


def test_world_missing_steps_today_without_merge(tmp_path):
    date_dir = tmp_path / "2026-09-20"
    date_dir.mkdir()
    assert world_history_missing_steps(str(date_dir), "2026-09-20", today="2026-09-20") == [
        "world_news_merge"
    ]


def test_world_missing_steps_source_jsons_without_merge(tmp_path):
    wn = tmp_path / "2026-08-02" / "world-news"
    wn.mkdir(parents=True)
    (wn / "bbc-news.json").write_text("{}", encoding="utf-8")
    assert world_history_missing_steps(
        str(tmp_path / "2026-08-02"), "2026-08-02", today="2026-09-20"
    ) == ["world_news_merge"]


def test_world_missing_steps_translated_true(tmp_path):
    wn = tmp_path / "2026-09-20" / "world-news"
    wn.mkdir(parents=True)
    (wn / "world-news-data.json").write_text(
        json.dumps({"translated": True, "total_items": 1, "categories": []}),
        encoding="utf-8",
    )
    assert world_history_missing_steps(
        str(tmp_path / "2026-09-20"), "2026-09-20", today="2026-09-20"
    ) == []


def test_world_missing_steps_untranslated_merged(tmp_path):
    wn = tmp_path / "2026-09-20" / "world-news"
    wn.mkdir(parents=True)
    (wn / "world-news-data.json").write_text(
        json.dumps({"translated": False, "total_items": 1}),
        encoding="utf-8",
    )
    assert world_history_missing_steps(
        str(tmp_path / "2026-09-20"), "2026-09-20", today="2026-09-20"
    ) == ["world_news_translate"]
