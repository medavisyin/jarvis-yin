import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

import llm_reasoning  # noqa: F401 — load real config before tests stub it
from ath_rebreak_scanner import _generate_ath_markdown_report, _layer3_judge, _parse_ath_json


def _install_config(monkeypatch, call_deepseek):
    cfg = types.ModuleType("config")
    cfg.call_deepseek = call_deepseek
    monkeypatch.setitem(sys.modules, "config", cfg)


def test_parse_ath_json_verdict():
    text = '{"verdict":"买入","score":70,"reason":"回踩后再突破","risk":"假突破","buy_low":10.0,"buy_high":10.5,"stop_loss":9.5}'
    parsed = _parse_ath_json(text)
    assert parsed["verdict"] == "买入"
    assert parsed["buy_low"] == 10.0


def test_empty_markdown_has_placeholder_not_ath_wording():
    md = _generate_ath_markdown_report([], [], "2026-08-30", {"all_candidates_count": 0})
    assert "暂无" in md
    assert "近5年高" in md
    assert "历史最高" not in md


def test_markdown_notes_rag_skipped():
    md = _generate_ath_markdown_report([], [], "2026-08-30", {"all_candidates_count": 0})
    assert "RAG" in md
    assert "未收录" in md


def test_layer3_not_ok_is_not_buy(monkeypatch):
    _install_config(monkeypatch, lambda *_a, **_k: {"ok": False, "content": ""})
    out = _layer3_judge({
        "symbol": "600000",
        "name": "测试",
        "price": 10.0,
        "tradeable": True,
        "stage": "rebreak",
        "benchmark": 10.1,
        "pullback_tags": ["below_high"],
        "rebreak_date": "2026-08-28",
    })
    assert out["verdict"] != "买入"
    assert "终审失败" in (out.get("reasoning") or "")


def test_layer3_exception_is_not_buy(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("deepseek down")

    _install_config(monkeypatch, boom)
    out = _layer3_judge({
        "symbol": "600000",
        "name": "测试",
        "price": 10.0,
        "tradeable": True,
        "stage": "rebreak",
    })
    assert out["verdict"] != "买入"


def test_layer3_ok_without_json_is_not_buy(monkeypatch):
    _install_config(monkeypatch, lambda *_a, **_k: {"ok": True, "content": "暂无结论"})
    out = _layer3_judge({
        "symbol": "600000",
        "name": "测试",
        "price": 10.0,
        "tradeable": True,
        "stage": "rebreak",
    })
    assert out.get("verdict") == "不买入"
    assert "终审失败" in (out.get("reasoning") or "")
