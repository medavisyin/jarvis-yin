"""Finance News source catalog, enabled-filter, merge categories, RAG payload."""

from __future__ import annotations

import json
import os
import re
import sys

import pytest

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
_RAG = os.path.join(_SCRIPTS, "rag")
for _p in (_SCRIPTS, _PIPELINE, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from finance_sources import (  # noqa: E402
    AUDIO_FILES,
    CATEGORIES,
    CHINA_DOMAIN_RE,
    catalog_by_id,
    drop_china_domain_items,
    drop_near_duplicates,
    extract_rag_items,
    filter_items_for_summary,
    load_catalog,
    merge_source_jsons,
    resolve_enabled,
    scripts_to_run,
    topic_category_for_source,
)


def test_six_categories_and_audio_filenames():
    ids = [c["id"] for c in CATEGORIES]
    assert ids == [
        "markets",
        "china-policy",
        "us-political",
        "crypto",
        "gold",
        "oil",
    ]
    assert AUDIO_FILES == {
        "markets": "finance-markets.mp3",
        "china-policy": "finance-china-policy.mp3",
        "us-political": "finance-us-political.mp3",
        "crypto": "finance-crypto.mp3",
        "gold": "finance-gold.mp3",
        "oil": "finance-oil.mp3",
    }
    assert "finance-news.mp3" not in AUDIO_FILES.values()


def test_catalog_default_on_sources():
    catalog = load_catalog()
    by_id = {s["id"]: s for s in catalog}
    default_on = {s["id"] for s in catalog if s.get("default_enabled")}
    assert default_on == {
        "reuters-markets",
        "cnbc-markets",
        "yahoo-finance",
        "pboc",
        "csrc",
        "cls",
        "yicai",
        "ap-news",
        "bls",
        "bea",
        "census",
        "ism",
        "adp",
        "fed",
        "cnbc-economy",
        "politico-economy",
        "marketwatch",
        "coindesk",
        "kitco",
        "mining-com",
        "eia",
        "oilprice",
    }
    assert by_id["ap-news"]["category"] == "us-political"
    assert by_id["cls"]["category"] == "china-policy"
    assert by_id["kitco"]["category"] == "gold"
    assert by_id["kitco"]["fetcher"].endswith("fetch-kitco.py")
    assert "KitcoNews.xml" not in json.dumps(by_id["kitco"])
    assert by_id["mining-com"]["category"] == "gold"
    assert by_id["mining-com"].get("default_enabled") is True


def test_catalog_excludes_weibo_and_toutiao():
    ids = {s["id"] for s in load_catalog()}
    blob = json.dumps(load_catalog()).lower()
    assert "weibo" not in ids
    assert "toutiao" not in ids
    assert "weibo" not in blob
    assert "toutiao" not in blob


def test_default_off_optional_sources_exist():
    off = {s["id"] for s in load_catalog() if not s.get("default_enabled")}
    assert {
        "gov-cn-policy",
        "stcn",
        "treasury",
        "reuters-politics",
        "the-block",
        "reuters-crypto",
        "wgc",
        "reuters-metals",
        "reuters-energy",
    } <= off


def test_resolve_enabled_uses_defaults_then_overrides():
    catalog = load_catalog()
    enabled = resolve_enabled(catalog, settings={})
    assert "coindesk" in enabled
    assert "the-block" not in enabled

    enabled2 = resolve_enabled(
        catalog,
        settings={"finance_sources_enabled": {"the-block": True, "coindesk": False}},
    )
    assert "the-block" in enabled2
    assert "coindesk" not in enabled2


def test_resolve_enabled_sources_arg_overrides_settings():
    catalog = load_catalog()
    enabled = resolve_enabled(
        catalog,
        settings={"finance_sources_enabled": {"coindesk": True, "kitco": True}},
        source_ids=["kitco", "eia"],
    )
    assert enabled == ["kitco", "eia"]


def test_scripts_to_run_dedupes_shared_fetchers():
    catalog = load_catalog()
    scripts = scripts_to_run(catalog, ["reuters-markets", "reuters-energy"])
    assert scripts
    # Two catalog rows may share one fetcher script; run it once.
    assert len(scripts) == len(set(scripts))


def test_topic_category_comes_from_catalog_row():
    assert topic_category_for_source("kitco") == "gold"
    assert topic_category_for_source("ap-news") == "us-political"
    assert topic_category_for_source("yahoo-finance") == "markets"


def test_drop_china_domain_from_non_china_categories():
    items = [
        {"title": "Fed holds rates", "url": "https://apnews.com/article/1", "category": "us-political"},
        {"title": "美联储维持利率", "url": "https://finance.sina.com.cn/x", "category": "us-political"},
        {"title": "央行降准", "url": "https://www.pbc.gov.cn/x", "category": "china-policy"},
    ]
    kept = drop_china_domain_items(items)
    urls = {it["url"] for it in kept}
    assert "https://apnews.com/article/1" in urls
    assert "https://www.pbc.gov.cn/x" in urls
    assert not any("sina.com.cn" in u for u in urls)
    assert CHINA_DOMAIN_RE.search("https://www.cls.cn/detail/1")


def test_extract_rag_items_payload():
    merged = {
        "report_date": "2026-08-27",
        "categories": [
            {
                "category": "gold",
                "label": "黄金",
                "items": [
                    {
                        "title": "Gold hits record",
                        "summary": "Spot gold rose.",
                        "url": "https://www.kitco.com/news/1",
                        "source": "Kitco News",
                    }
                ],
            }
        ],
    }
    rag = extract_rag_items(merged)
    assert len(rag) == 1
    meta = rag[0]["metadata"]
    assert meta["doc_type"] == "finance_news"
    assert meta["item_type"] == "finance_news"
    assert meta["date"] == "2026-08-27"
    assert meta["category"] == "gold"
    assert meta["source"] == "Kitco News"
    assert "Gold hits record" in rag[0]["text"]


def test_filter_items_for_summary_by_date_and_category():
    items = [
        {"date": "2026-08-20", "category": "gold", "title": "A", "text": "gold a"},
        {"date": "2026-08-25", "category": "gold", "title": "B", "text": "gold b"},
        {"date": "2026-08-25", "category": "oil", "title": "C", "text": "oil c"},
        {"date": "2026-08-26", "category": "crypto", "title": "D", "text": "btc d"},
    ]
    got = filter_items_for_summary(
        items, start="2026-08-24", end="2026-08-26", categories=["gold", "oil"]
    )
    titles = [it["title"] for it in got]
    assert titles == ["B", "C"]


def test_catalog_by_id_lookup():
    row = catalog_by_id("fed")
    assert row["display"]
    assert row["fetcher"]
    with pytest.raises(KeyError):
        catalog_by_id("not-a-source")


def test_merge_uses_catalog_categories(tmp_path):
    (tmp_path / "kitco.json").write_text(
        json.dumps({
            "source": "kitco",
            "items": [
                {
                    "title": "Gold futures jump on safe-haven demand",
                    "url": "https://www.kitco.com/news/gold-1",
                    "date": "2026-08-27",
                    "summary": "Bullion prices rose as yields fell.",
                    "category": "markets",
                    "points": [],
                }
            ],
        }),
        encoding="utf-8",
    )
    merged = merge_source_jsons(str(tmp_path), report_date="2026-08-27")
    cats = {c["category"] for c in merged["categories"]}
    assert "gold" in cats
    gold_items = next(c["items"] for c in merged["categories"] if c["category"] == "gold")
    assert gold_items[0]["title"].startswith("Gold")
    assert gold_items[0].get("source")


def test_drop_near_duplicates_keeps_higher_priority_story():
    kept = drop_near_duplicates([
        {
            "title": "Fed holds rates as inflation cools",
            "summary": "The Federal Reserve held interest rates as inflation cooled.",
            "_priority": 1,
        },
        {
            "title": "Fed holds rates, inflation cools further",
            "summary": "The Federal Reserve held interest rates as inflation cooled further.",
            "_priority": 2,
        },
    ])
    titles = [it["title"] for it in kept]
    assert titles == ["Fed holds rates as inflation cools"]


def test_drop_near_duplicates_keeps_distinct_labor_reports():
    kept = drop_near_duplicates([
        {
            "title": "The Employment Situation — July 2026",
            "summary": "Nonfarm payroll employment rose; unemployment rate held at 4.2 percent.",
        },
        {
            "title": "ADP National Employment Report: private sector added 44,000 jobs in July",
            "summary": "Pay was up 4.4 percent year over year according to ADP payroll data.",
        },
    ])
    assert len(kept) == 2


def test_merge_near_dedupes_markets_keeps_cross_category_oil(tmp_path):
    _write_source_json(
        tmp_path, "reuters-markets",
        "Fed holds rates as inflation cools",
        "https://www.reuters.com/markets/fed-1",
    )
    _write_source_json(
        tmp_path, "cnbc-markets",
        "Fed holds rates, inflation cools further",
        "https://www.cnbc.com/fed-1",
    )
    _write_source_json(
        tmp_path, "oilprice",
        "Oil climbs as OPEC cuts output",
        "https://oilprice.com/news/oil-1",
        category_hint="oil",
    )
    _write_source_json(
        tmp_path, "reuters-energy",
        "Oil climbs after OPEC output cuts",
        "https://www.reuters.com/energy/oil-1",
        category_hint="oil",
    )
    merged = merge_source_jsons(str(tmp_path), report_date="2026-08-27")
    markets = next(c["items"] for c in merged["categories"] if c["category"] == "markets")
    market_titles = [it["title"] for it in markets]
    assert "Fed holds rates as inflation cools" in market_titles
    assert "Fed holds rates, inflation cools further" not in market_titles
    oil = next(c["items"] for c in merged["categories"] if c["category"] == "oil")
    oil_titles = [it["title"] for it in oil]
    assert any("Oil climbs" in t for t in oil_titles)
    assert len(oil_titles) == 1


def test_load_finance_items_from_reports(tmp_path):
    from finance_sources import load_finance_items_from_reports

    d = tmp_path / "2026-08-25" / "finance-news"
    d.mkdir(parents=True)
    (d / "finance-news-data.json").write_text(
        json.dumps({
            "report_date": "2026-08-25",
            "categories": [
                {"category": "gold", "items": [{"title": "Gold up", "url": "https://kitco.com/1", "summary": "x"}]},
                {"category": "oil", "items": [{"title": "Oil down", "url": "https://oilprice.com/1"}]},
            ],
        }),
        encoding="utf-8",
    )
    got = load_finance_items_from_reports(str(tmp_path), "2026-08-24", "2026-08-26", ["gold"])
    assert [it["title"] for it in got] == ["Gold up"]


def test_finance_report_items_prefers_zh_and_keeps_url():
    from finance_sources import finance_report_items

    merged = {
        "categories": [
            {
                "category": "gold",
                "label": "黄金",
                "items": [
                    {
                        "title": "Gold hits record",
                        "title_zh": "金价创新高",
                        "url": "https://www.kitco.com/news/1",
                        "source": "Kitco News",
                    }
                ],
            }
        ]
    }
    cats = finance_report_items(merged)
    gold = next(c for c in cats if c["category"] == "gold")
    assert gold["items"][0]["title"] == "金价创新高"
    assert gold["items"][0]["url"] == "https://www.kitco.com/news/1"
    assert gold["items"][0]["source"] == "Kitco News"


def test_daily_fetch_exposes_finance_report_items_api():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "finance-items" in src
    assert "finance_report_items" in src
    html = open(os.path.join(_SCRIPTS, "rag", "templates", "index.html"), encoding="utf-8").read()
    assert "loadDfFinanceCategoryReport" in html


def test_daily_fetch_uses_per_category_mp3_names():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    for name in AUDIO_FILES.values():
        assert name in src, f"missing {name} in daily_fetch.py"
    assert '"finance_audio": "finance-news.mp3"' not in src


def test_orchestrator_wires_catalog_and_sources_flag():
    path = os.path.join(_PIPELINE, "run-finance-news.py")
    src = open(path, encoding="utf-8").read()
    assert "--sources" in src
    assert "merge_source_jsons" in src
    assert "fetch-china-news.py" not in src


def _write_source_json(folder, source_id, title, url, category_hint="markets"):
    (folder / f"{source_id}.json").write_text(
        json.dumps({
            "source": source_id,
            "items": [
                {
                    "title": title,
                    "url": url,
                    "date": "2026-08-27",
                    "summary": title,
                    "category": category_hint,
                    "points": [],
                }
            ],
        }),
        encoding="utf-8",
    )


def test_daily_fetch_imports_config_roots():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "from config import" in src
    assert "JIRA_REPORT_SCRIPT" in src
    assert "KNOWLEDGE_ROOT" in src
    assert "REPORTS_ROOT" in src


def test_merge_subset_enabled_ids_keeps_other_on_disk_jsons(tmp_path):
    """--sources / enabled_ids must not wipe sibling category files already on disk."""
    _write_source_json(
        tmp_path, "kitco",
        "Gold futures jump on safe-haven demand",
        "https://www.kitco.com/news/gold-1",
    )
    _write_source_json(
        tmp_path, "oilprice",
        "Oil climbs as Middle East tensions rise",
        "https://oilprice.com/news/oil-1",
    )
    merged = merge_source_jsons(
        str(tmp_path), report_date="2026-08-27", enabled_ids=["kitco"]
    )
    cats = {c["category"] for c in merged["categories"]}
    assert "gold" in cats
    assert "oil" in cats


def test_cls_and_yicai_keep_always():
    by_id = {s["id"]: s for s in load_catalog()}
    assert by_id["cls"].get("keep_always") is True
    assert by_id["yicai"].get("keep_always") is True


def test_us_macro_official_sources_in_catalog():
    by_id = {s["id"]: s for s in load_catalog()}
    for sid, display_part, method in (
        ("bea", "BEA", "rss"),
        ("census", "Census", "scrape"),
        ("ism", "ISM", "scrape"),
        ("adp", "ADP", "scrape"),
    ):
        row = by_id[sid]
        assert row["category"] == "us-political"
        assert row.get("default_enabled") is True
        assert row.get("keep_always") is True
        assert row.get("method") == method
        assert display_part.lower() in row["display"].lower()
    bea_feeds = " ".join(u for _, u in (by_id["bea"].get("feeds") or []))
    assert "apps.bea.gov/rss/rss.xml" in bea_feeds
    assert by_id["census"]["fetcher"].endswith("fetch-census.py")
    assert by_id["ism"]["fetcher"].endswith("fetch-ism.py")
    assert by_id["adp"]["fetcher"].endswith("fetch-adp.py")
    assert by_id["marketwatch"].get("default_enabled") is True
    assert by_id["marketwatch"].get("keep_always") is not True


def test_china_domain_blocks_weibo_and_toutiao():
    items = [
        {"title": "BTC", "url": "https://weibo.com/ttarticle/p/show?id=1", "category": "crypto"},
        {"title": "Gold", "url": "https://www.toutiao.com/article/1/", "category": "gold"},
        {"title": "Kitco", "url": "https://www.kitco.com/news/1", "category": "gold"},
    ]
    kept = drop_china_domain_items(items)
    urls = {it["url"] for it in kept}
    assert "https://www.kitco.com/news/1" in urls
    assert not any("weibo.com" in u or "toutiao.com" in u for u in urls)


def test_run_all_sources_indexes_after_finance_fetch():
    path = os.path.join(_PIPELINE, "run-all-sources.py")
    src = open(path, encoding="utf-8").read()
    finance_at = src.find("Phase 5: Finance News Fetch")
    index_script = "index_briefing.py"
    assert finance_at != -1
    after = src[finance_at:]
    assert index_script in after, "index_briefing.py must run after finance fetch"


def test_daily_fetch_indexes_after_finance_refetch():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    refetch_at = src.find("Re-fetching finance news sources")
    assert refetch_at != -1
    after = src[refetch_at:]
    assert "_index_briefing_warn" in after
    assert "index_briefing.py" in src


def test_fetch_sources_timeout_covers_finance_900s():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    marker = 'run_all = os.path.join(scripts_dir, "pipeline", "run-all-sources.py")'
    idx = src.find(marker)
    assert idx != -1
    chunk = src[idx:idx + 900]
    assert "timeout=1500" in chunk


def test_refetch_finance_only_when_explicit_in_only_steps():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert 'only_steps and "refetch_finance" in only_steps' in src
    assert 'if _should_run("refetch_finance")' not in src


def test_run_daily_fetch_persists_finance_picker():
    path = os.path.join(_SCRIPTS, "rag", "templates", "index.html")
    src = open(path, encoding="utf-8").read()
    fn = src[src.find("async function runDailyFetchFromModal()") :]
    fn = fn[: fn.find("\nasync function ")] if "\nasync function " in fn[1:] else fn[:2500]
    assert "saveDfFinanceSources" in fn


def test_ap_playwright_timeout_exceeds_120():
    path = os.path.join(_PIPELINE, "run-finance-news.py")
    src = open(path, encoding="utf-8").read()
    assert "timeout" in src
    catalog = load_catalog()
    ap = next(s for s in catalog if s["id"] == "ap-news")
    assert int(ap.get("timeout") or 0) >= 180


def test_reuters_politics_feed_is_not_world_rss():
    row = catalog_by_id("reuters-politics")
    feeds = " ".join(u for _, u in (row.get("feeds") or []))
    assert "newsletter-rss/world" not in feeds
    assert "politic" in feeds.lower() or "/politics" in feeds.lower()


def test_categories_with_items_skips_empty():
    from finance_sources import categories_with_items

    merged = {
        "categories": [
            {"category": "gold", "items": [{"title": "a"}]},
            {"category": "oil", "items": []},
            {"category": "crypto"},
        ]
    }
    assert categories_with_items(merged) == ["gold"]


def test_daily_fetch_missing_audio_uses_categories_with_items():
    path = os.path.join(_SCRIPTS, "rag", "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "categories_with_items" in src


def test_daily_fetch_impl_overview_says_six_finance_mp3s():
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "docs",
        "implementation",
        "personal",
        "daily-fetch-impl.md",
    )
    text = open(path, encoding="utf-8").read()
    assert "**two** MP3" not in text
    assert "six" in text.lower()


def test_cnbc_markets_rss_feeds_are_unique():
    path = os.path.join(_SCRIPTS, "fetchers", "news", "fetch-cnbc-markets.py")
    src = open(path, encoding="utf-8").read()
    urls = re.findall(r"https://search\.cnbc\.com[^\"']+", src)
    assert urls
    assert len(urls) == len(set(urls))


def test_exclude_finance_news_hits():
    from rag_filters import exclude_finance_news

    rows = [
        {"title": "AI", "item_type": "news_item"},
        {"title": "Gold", "item_type": "finance_news"},
    ]
    assert [r["title"] for r in exclude_finance_news(rows)] == ["AI"]
    assert len(exclude_finance_news(rows, include_finance_news=True)) == 2


def test_vector_search_applies_finance_must_not():
    path = os.path.join(_SCRIPTS, "rag", "rag_engine.py")
    src = open(path, encoding="utf-8").read()
    assert "must_not" in src
    assert "exclude_finance_news" in src


def test_official_us_macro_sources_assign_us_region():
    from finance_news_filter import assign_region

    for source in (
        "BEA News",
        "BLS Employment",
        "Census Bureau",
        "ISM PMI Reports",
        "ADP Employment",
        "Federal Reserve",
    ):
        assert assign_region({"source": source, "title": "Housing Starts", "summary": ""}) == "us"


def test_keyword_heuristic_finance_beats_generic_fenxi():
    rag = os.path.join(_SCRIPTS, "rag")
    if rag not in sys.path:
        sys.path.insert(0, rag)
    from intent import Intent, _keyword_heuristic

    result = _keyword_heuristic("分析黄金新闻")
    assert result is not None
    assert result.intent == Intent.FINANCE_NEWS


def test_fetch_rss_unknown_source_id_does_not_crash(tmp_path):
    script = os.path.join(_SCRIPTS, "fetchers", "news", "fetch-rss-source.py")
    import subprocess

    r = subprocess.run(
        [sys.executable, script, str(tmp_path), "not-a-source"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    out = tmp_path / "not-a-source.json"
    assert out.is_file()


def test_merge_drops_exact_title_from_yesterday(tmp_path):
    ydir = tmp_path / "2026-08-29" / "finance-news"
    tdir = tmp_path / "2026-08-30" / "finance-news"
    ydir.mkdir(parents=True)
    tdir.mkdir(parents=True)
    (ydir / "finance-news-data.json").write_text(
        json.dumps({
            "report_date": "2026-08-29",
            "categories": [{
                "category": "gold",
                "label": "黄金",
                "items": [{
                    "title": "Gold futures jump on safe-haven demand",
                    "summary": "Bullion prices rose.",
                }],
            }],
        }),
        encoding="utf-8",
    )
    (tdir / "kitco.json").write_text(
        json.dumps({
            "source": "kitco",
            "items": [
                {
                    "title": "Gold futures jump on safe-haven demand",
                    "url": "https://www.kitco.com/news/gold-1",
                    "date": "2026-08-30",
                    "summary": "Bullion prices rose as yields fell.",
                    "points": [],
                },
                {
                    "title": "Silver rallies as industrial demand jumps",
                    "url": "https://www.kitco.com/news/silver-1",
                    "date": "2026-08-30",
                    "summary": "Silver prices climbed on factory demand.",
                    "points": [],
                },
            ],
        }),
        encoding="utf-8",
    )
    merged = merge_source_jsons(str(tdir), report_date="2026-08-30")
    titles = [it["title"] for c in merged.get("categories") or [] for it in c.get("items") or []]
    assert "Gold futures jump on safe-haven demand" not in titles
    assert "Silver rallies as industrial demand jumps" in titles


def test_merge_keeps_title_only_seen_two_days_ago(tmp_path):
    older = tmp_path / "2026-08-28" / "finance-news"
    tdir = tmp_path / "2026-08-30" / "finance-news"
    older.mkdir(parents=True)
    tdir.mkdir(parents=True)
    (older / "finance-news-data.json").write_text(
        json.dumps({
            "report_date": "2026-08-28",
            "categories": [{
                "category": "gold",
                "items": [{"title": "Gold futures jump on safe-haven demand"}],
            }],
        }),
        encoding="utf-8",
    )
    (tdir / "kitco.json").write_text(
        json.dumps({
            "source": "kitco",
            "items": [{
                "title": "Gold futures jump on safe-haven demand",
                "url": "https://www.kitco.com/news/gold-1",
                "date": "2026-08-30",
                "summary": "Bullion prices rose as yields fell.",
                "points": [],
            }],
        }),
        encoding="utf-8",
    )
    merged = merge_source_jsons(str(tdir), report_date="2026-08-30")
    titles = [it["title"] for c in merged.get("categories") or [] for it in c.get("items") or []]
    assert "Gold futures jump on safe-haven demand" in titles
