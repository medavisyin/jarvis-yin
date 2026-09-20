"""Keyword geo-hubs for the Jarvis world-monitor map (original, not World Monitor)."""

from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")
sys.path.insert(0, _PIPELINE)

from geo_hubs import COUNTRIES, HUBS, infer_hubs  # noqa: E402


def test_thirty_one_tier1_countries():
    assert len(COUNTRIES) == 31
    ids = {c["id"] for c in COUNTRIES}
    assert {"US", "CN", "RU", "UA", "TW", "IR", "IL"}.issubset(ids)
    for c in COUNTRIES:
        assert isinstance(c["lat"], (int, float))
        assert isinstance(c["lon"], (int, float))


def test_hubs_have_coordinates_and_keywords():
    assert len(HUBS) >= 20
    for h in HUBS:
        assert h["lat"] or h["lat"] == 0
        assert h.get("keywords")


def test_infer_hubs_matches_english_and_chinese():
    kyiv = infer_hubs("Missile strike near Kyiv as Ukraine holds")
    assert any(h["id"] == "kyiv" or h.get("country") == "UA" for h in kyiv)
    tw = infer_hubs("解放军在台湾海峡周边演练")
    assert any(h.get("country") == "TW" or "taiwan" in h["id"] for h in tw)
    assert infer_hubs("unrelated sports scoreline") == []
