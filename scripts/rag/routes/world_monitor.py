"""Local world-monitor dashboard API (Jarvis-native, Ollama-only)."""

from __future__ import annotations

import os
import sys
from datetime import datetime

_ROUTES_DIR = os.path.dirname(os.path.abspath(__file__))
_RAG_DIR = os.path.dirname(_ROUTES_DIR)
_SCRIPTS_DIR = os.path.dirname(_RAG_DIR)
_PIPELINE_DIR = os.path.join(_SCRIPTS_DIR, "pipeline")
for _p in (_SCRIPTS_DIR, _RAG_DIR, _PIPELINE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from web_api import Blueprint, jsonify, request

from config import REPORTS_ROOT
from world_monitor import VARIANTS, build_dashboard, clamp_lookback, ollama_brief, ollama_hub_insight

world_monitor_bp = Blueprint("world_monitor", __name__)


@world_monitor_bp.route("/api/toolbar/world-monitor", methods=["GET"])
def api_world_monitor():
    target = (request.args.get("date") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    variant = request.args.get("variant") or "world"
    if variant not in VARIANTS:
        variant = "world"
    lookback = clamp_lookback(request.args.get("lookback") or 1)
    return jsonify(build_dashboard(REPORTS_ROOT, target, variant, lookback_days=lookback))


@world_monitor_bp.route("/api/toolbar/world-monitor/brief", methods=["POST"])
def api_world_monitor_brief():
    data = request.get_json(silent=True) or {}
    target = (data.get("date") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    variant = data.get("variant") or "world"
    if variant not in VARIANTS:
        variant = "world"
    lookback = clamp_lookback(data.get("lookback") or 1)
    dash = build_dashboard(REPORTS_ROOT, target, variant, lookback_days=lookback)
    try:
        text = ollama_brief(dash)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300], "dashboard": dash}), 502
    return jsonify({"ok": True, "brief": text, "date": target, "variant": variant})


@world_monitor_bp.route("/api/toolbar/world-monitor/insight", methods=["POST"])
def api_world_monitor_insight():
    data = request.get_json(silent=True) or {}
    target = (data.get("date") or "")[:10] or datetime.now().strftime("%Y-%m-%d")
    variant = data.get("variant") or "world"
    if variant not in VARIANTS:
        variant = "world"
    lookback = clamp_lookback(data.get("lookback") or 1)
    hub_id = str(data.get("hub_id") or "").strip()
    if not hub_id:
        return jsonify({"ok": False, "error": "hub_id required"}), 400
    dash = build_dashboard(REPORTS_ROOT, target, variant, lookback_days=lookback)
    try:
        text = ollama_hub_insight(dash, hub_id)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300], "hub_id": hub_id}), 502
    return jsonify({"ok": True, "insight": text, "hub_id": hub_id, "date": target, "lookback": lookback})
