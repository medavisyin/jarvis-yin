"""Jarvis-native world-monitor dashboard payload (local JSON + Ollama later)."""

from __future__ import annotations

import json
import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
sys.path.insert(0, _PIPELINE)

from world_monitor import (  # noqa: E402
    VARIANTS,
    classify_streams,
    compute_correlation,
    finance_radar,
    layers_for_variant,
    build_dashboard,
)


def test_six_site_variants_and_layer_catalog():
    assert VARIANTS == ["world", "tech", "finance", "commodity", "happy", "energy"]
    world_ids = {ly["id"] for ly in layers_for_variant("world")}
    assert "military" in world_ids
    assert "cii" not in world_ids
    tech_ids = {ly["id"] for ly in layers_for_variant("tech")}
    assert "news_technology" in tech_ids
    assert "military" not in tech_ids or "news_technology" in tech_ids
    happy_ids = {ly["id"] for ly in layers_for_variant("happy")}
    assert "happy" in happy_ids


def test_classify_streams_four_buckets():
    assert "military" in classify_streams("NATO troops and missile defense")
    assert "economic" in classify_streams("New sanctions and tariffs announced")
    assert "disaster" in classify_streams("Earthquake and flood kill dozens")
    assert "escalation" in classify_streams("Nuclear red line and invasion threat")
    assert classify_streams("garden festival opens downtown") == []


def test_correlation_requires_two_streams(tmp_path):
    items = [
        {
            "title": "Missile strike in Kyiv",
            "hubs": [{"id": "kyiv", "lat": 50.45, "lon": 30.52, "country": "UA"}],
            "streams": ["military"],
        },
        {
            "title": "Sanctions after Kyiv attack",
            "hubs": [{"id": "kyiv", "lat": 50.45, "lon": 30.52, "country": "UA"}],
            "streams": ["economic"],
        },
    ]
    hits = compute_correlation(items)
    assert hits
    assert hits[0]["hub_id"] == "kyiv"
    assert set(hits[0]["streams"]) >= {"military", "economic"}
    solo = compute_correlation([items[0]])
    assert solo == []


def test_finance_radar_buckets():
    data = {
        "categories": [
            {"category": "markets", "items": [{"title": "S&P futures"}]},
            {"category": "crypto", "items": [{"title": "Bitcoin"}]},
            {"category": "gold", "items": [{"title": "Bullion"}]},
            {"category": "oil", "items": [{"title": "Brent"}]},
        ]
    }
    radar = finance_radar(data)
    assert radar["exchanges"]["count"] == 1
    assert radar["crypto"]["count"] == 1
    assert radar["commodities"]["count"] == 2
    assert radar["composite"]["count"] == 4


def test_finance_radar_default_signals_are_empty():
    radar = finance_radar({"categories": []})
    assert radar["signals"]["fear_greed"]["value"] is None
    assert radar["signals"]["vix"]["value"] is None
    assert radar["signals"]["quotes"] == []
    assert radar["signals"]["mood"]["risk_level"] == ""


def test_finance_radar_attaches_numeric_signals():
    data = {
        "categories": [
            {"category": "markets", "items": [{"title": "S&P futures"}]},
        ]
    }
    signals = {
        "fear_greed": {"value": 28, "label": "Fear", "source": "alternative.me"},
        "vix": {"value": 22.4, "change_pct": 1.2, "source": "Yahoo Finance"},
        "quotes": [
            {"id": "gold", "symbol": "GC=F", "label": "Gold", "value": 2650.1, "change_pct": 0.4},
            {"id": "oil", "symbol": "CL=F", "label": "WTI", "value": 71.2, "change_pct": -0.8},
            {"id": "spx", "symbol": "^GSPC", "label": "S&P 500", "value": 5630.0, "change_pct": 0.2},
            {"id": "btc", "symbol": "BTC-USD", "label": "Bitcoin", "value": 64000.0, "change_pct": 1.1},
        ],
        "mood": {"risk_level": "fear", "signals": ["恐惧 (Fear)"], "recommendation": "观望"},
        "fetched_at": "2026-09-20T10:00:00",
    }
    radar = finance_radar(data, signals=signals)
    assert radar["exchanges"]["count"] == 1
    assert radar["signals"]["fear_greed"]["value"] == 28
    assert radar["signals"]["vix"]["value"] == 22.4
    ids = {q["id"] for q in radar["signals"]["quotes"]}
    assert ids == {"gold", "oil", "spx", "btc"}
    assert radar["signals"]["mood"]["risk_level"] == "fear"


def test_build_dashboard_uses_injected_radar_signals(tmp_path):
    day = tmp_path / "2026-09-20"
    wn = day / "world-news"
    fn = day / "finance-news"
    wn.mkdir(parents=True)
    fn.mkdir()
    (wn / "world-news-data.json").write_text(
        json.dumps({"categories": [{"category": "politics", "items": [{"title": "Talks in London", "source": "BBC"}]}]}),
        encoding="utf-8",
    )
    (fn / "finance-news-data.json").write_text(
        json.dumps({"categories": [{"category": "markets", "items": [{"title": "Dow"}]}]}),
        encoding="utf-8",
    )
    signals = {
        "fear_greed": {"value": 64, "label": "Greed", "source": "alternative.me"},
        "vix": {"value": 14.1, "change_pct": -0.5, "source": "Yahoo Finance"},
        "quotes": [{"id": "gold", "symbol": "GC=F", "label": "Gold", "value": 2650.1, "change_pct": 0.4}],
        "mood": {"risk_level": "greed", "signals": ["贪婪"], "recommendation": "注意风险"},
        "fetched_at": "2026-09-20T10:00:00",
    }
    dash = build_dashboard(str(tmp_path), "2026-09-20", variant="finance", radar_signals=signals)
    assert dash["finance_radar"]["signals"]["fear_greed"]["value"] == 64
    assert dash["finance_radar"]["signals"]["quotes"][0]["id"] == "gold"


def test_build_dashboard_from_reports(tmp_path):
    day = tmp_path / "2026-09-20"
    wn = day / "world-news"
    fn = day / "finance-news"
    wn.mkdir(parents=True)
    fn.mkdir()
    (wn / "world-news-data.json").write_text(
        json.dumps({
            "total_items": 2,
            "categories": [{
                "category": "politics",
                "items": [
                    {"title": "Missile strike near Kyiv", "summary": "Ukraine", "source": "BBC"},
                    {"title": "Garden show in Lyon", "summary": "", "source": "DW"},
                ],
            }],
        }),
        encoding="utf-8",
    )
    (fn / "finance-news-data.json").write_text(
        json.dumps({"categories": [{"category": "markets", "items": [{"title": "Dow"}]}]}),
        encoding="utf-8",
    )
    dash = build_dashboard(str(tmp_path), "2026-09-20", variant="world")
    assert dash["variant"] == "world"
    assert dash["stats"]["world_items"] == 2
    assert any(p["layer"] == "military" for p in dash["points"])
    assert "cii" not in dash
    assert all(p.get("layer") != "cii" for p in dash["points"])
    assert all(p.get("id") != "cii" for p in dash["panels"])
    assert dash["finance_radar"]["exchanges"]["count"] == 1
    assert "engine" in dash and dash["engine"]["globe"] == "globe.gl"
    assert dash["engine"]["flat"] == "deck.gl"
    assert any(p.get("hub_label") for p in dash["points"])
    assert any(h.get("hub_ids") for h in dash["headlines"])


def test_variant_and_layers_change_headlines(tmp_path):
    day = tmp_path / "2026-09-20"
    wn = day / "world-news"
    fn = day / "finance-news"
    wn.mkdir(parents=True)
    fn.mkdir()
    (wn / "world-news-data.json").write_text(
        json.dumps({
            "categories": [
                {"category": "politics", "items": [{"title": "Missile strike near Kyiv", "source": "BBC"}]},
                {"category": "technology", "items": [{"title": "Chip export talks in Beijing", "source": "Reuters"}]},
            ],
        }),
        encoding="utf-8",
    )
    (fn / "finance-news-data.json").write_text(
        json.dumps({"categories": [{"category": "markets", "items": [{"title": "Dow futures in New York"}]}]}),
        encoding="utf-8",
    )
    world = build_dashboard(str(tmp_path), "2026-09-20", variant="world")
    tech = build_dashboard(str(tmp_path), "2026-09-20", variant="tech")
    finance = build_dashboard(str(tmp_path), "2026-09-20", variant="finance")
    world_titles = [h["title"] for h in world["headlines"]]
    tech_titles = [h["title"] for h in tech["headlines"]]
    finance_titles = [h["title"] for h in finance["headlines"]]
    assert "Missile strike near Kyiv" in world_titles
    assert "Chip export talks in Beijing" not in world_titles
    assert "Missile strike near Kyiv" not in tech_titles
    assert "Chip export talks in Beijing" in tech_titles
    assert finance_titles == ["Dow futures in New York"]
    missile = next(h for h in world["headlines"] if "Missile" in h["title"])
    assert "military" in missile["layers"]
    assert "news_politics" in missile["layers"]


def test_lookback_merges_two_days_and_dedupes(tmp_path):
    def write_day(day: str, items: list[dict]) -> None:
        wn = tmp_path / day / "world-news"
        wn.mkdir(parents=True, exist_ok=True)
        (wn / "world-news-data.json").write_text(
            json.dumps({"categories": [{"category": "politics", "items": items}]}),
            encoding="utf-8",
        )

    write_day("2026-09-20", [{"title": "Missile strike near Kyiv", "url": "https://ex/a", "source": "BBC"}])
    write_day(
        "2026-09-19",
        [
            {"title": "Talks in London", "url": "https://ex/b", "source": "BBC"},
            {"title": "Missile strike near Kyiv", "url": "https://ex/a", "source": "BBC"},
        ],
    )
    one = build_dashboard(str(tmp_path), "2026-09-20", variant="world", lookback_days=1)
    two = build_dashboard(str(tmp_path), "2026-09-20", variant="world", lookback_days=2)
    assert one["lookback"] == 1
    assert one["stats"]["world_items"] == 1
    assert two["lookback"] == 2
    assert two["stats"]["world_items"] == 2
    kyiv = next(h for h in two["headlines"] if "Kyiv" in (h.get("title") or ""))
    assert "kyiv" in (kyiv.get("hub_ids") or [])
    assert "UA" in (kyiv.get("country_ids") or [])


def test_lookback_skips_empty_calendar_gaps(tmp_path):
    def write_day(day: str, title: str) -> None:
        wn = tmp_path / day / "world-news"
        wn.mkdir(parents=True)
        (wn / "world-news-data.json").write_text(
            json.dumps({
                "categories": [{"category": "politics", "items": [{"title": title, "url": f"https://ex/{day}", "source": "BBC"}]}],
            }),
            encoding="utf-8",
        )

    write_day("2026-09-20", "Missile strike near Kyiv")
    write_day("2026-07-28", "Talks in London")
    two = build_dashboard(str(tmp_path), "2026-09-20", variant="world", lookback_days=2)
    assert two["days"] == ["2026-09-20", "2026-07-28"]
    assert two["stats"]["world_items"] == 2
