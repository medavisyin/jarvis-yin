"""Local geo-hub catalog for Jarvis world-monitor (original keyword matching)."""

from __future__ import annotations

import json
import os
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_DIR, "geo_hubs.json")

_cache: dict[str, Any] | None = None


def _raw() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with open(_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def _init() -> None:
    global COUNTRIES, HUBS
    data = _raw()
    COUNTRIES = list(data["countries"])
    HUBS = list(data["hubs"])


COUNTRIES: list[dict[str, Any]] = []
HUBS: list[dict[str, Any]] = []
_init()


def infer_hubs(text: str) -> list[dict[str, Any]]:
    blob = (text or "").lower()
    if not blob.strip():
        return []
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hub in HUBS:
        for kw in hub.get("keywords") or []:
            if kw.lower() in blob:
                if hub["id"] not in seen:
                    seen.add(hub["id"])
                    hits.append(hub)
                break
    return hits
