"""DeepSeek quality-value persona must be 6m–2y, not the 1–2 week ruler."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "stock"))

from llm_reasoning import build_quality_value_system_prompt
from quality_value_scanner import apply_layer4_batch


def test_value_prompt_is_not_short_horizon():
    p = build_quality_value_system_prompt()
    assert "6个月" in p or "6 个月" in p
    assert "2年" in p or "2 年" in p
    assert "价值陷阱" in p
    assert "行业周期" in p
    assert "商誉" in p
    assert "1周/2周" not in p
    assert "deepseek_shared" not in p


def test_medium_horizon_prompt_uses_analysis_style_not_1_2_weeks():
    p = build_quality_value_system_prompt("medium")
    assert "1个月" in p or "1 个月" in p
    assert "6个月" in p or "6 个月" in p
    assert "交叉验证" in p
    assert "概率" in p
    assert "T+1" in p
    assert "价值陷阱" in p
    assert "行业周期" in p
    assert "1周/2周" not in p
    assert "1～2 周" not in p and "1～2周" not in p
    long_p = build_quality_value_system_prompt("long")
    assert "6个月～2年" in long_p or "6个月～2 年" in long_p or "2年" in long_p
    assert "交叉验证" not in long_p


def test_apply_layer4_batch_merges_and_vetoes():
    cands = [
        {"symbol": "600000", "industry": "银行", "name": "浦发"},
        {"symbol": "601398", "industry": "银行", "name": "工行"},
        {"symbol": "000333", "industry": "家电", "name": "美的"},
    ]
    raw = """```json
    [
      {"symbol":"600000","verdict":"买入","score":80,"cycle":"平稳","trap":false,"reason":"a","risk":"r"},
      {"symbol":"601398","verdict":"买入","score":70,"cycle":"衰退","trap":false,"reason":"b","risk":"r"},
      {"symbol":"000333","verdict":"买入","score":90,"cycle":"上升","trap":true,"reason":"c","risk":"r"}
    ]
    ```"""
    picks = apply_layer4_batch(cands, raw)
    symbols = [p["symbol"] for p in picks]
    assert symbols == ["600000"]


def test_parse_prediction_trade_levels_extracts_prices():
    from llm_reasoning import parse_prediction_trade_levels
    raw = '{"verdict":"不买入","buy_low":8.1,"buy_high":8.6,"stop_loss":7.5,"target_price":9.8,"reason":"高风险","risk":"出货"}'
    out = parse_prediction_trade_levels(raw)
    assert out["ok"] is True
    assert out["verdict"] == "不买入"
    assert out["buy_low"] == 8.1
    assert out["buy_high"] == 8.6
    assert out["stop_loss"] == 7.5
    assert out["target_price"] == 9.8


def test_parse_prediction_trade_levels_handles_fenced_json():
    from llm_reasoning import parse_prediction_trade_levels
    raw = '```json\n{"verdict":"买入","buy_low":10,"buy_high":10.5,"stop_loss":9.4,"target_price":11.8,"reason":"ok"}\n```'
    out = parse_prediction_trade_levels(raw)
    assert out["ok"] is True
    assert out["verdict"] == "买入"
    assert out["buy_low"] == 10.0


def test_parse_prediction_trade_levels_all_null_prices_not_ok():
    from llm_reasoning import parse_prediction_trade_levels
    out = parse_prediction_trade_levels('{"verdict":"买入","reason":"无价"}')
    assert out["ok"] is False


def test_trade_levels_prompt_uses_analysis_ruler():
    from llm_reasoning import build_prediction_trade_levels_system_prompt
    p = build_prediction_trade_levels_system_prompt()
    assert "1周/2周" in p or "1～2周" in p or "1～2 周" in p
    assert "buy_low" in p
    assert "buy_high" in p
    assert "stop_loss" in p
    assert "target_price" in p
    assert "不买入" in p
    assert "T+1" in p
    assert "交叉验证" in p
    assert "概率" in p


def test_generate_prediction_trade_levels_disables_thinking(monkeypatch):
    captured = {}

    def fake_call(system_prompt, user_prompt, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "content": '{"verdict":"买入","buy_low":1,"buy_high":1.1,"stop_loss":0.9,"target_price":1.2}',
            "usage": {},
        }

    monkeypatch.setattr("llm_reasoning._load_or_compute", lambda *a, **k: {})
    monkeypatch.setattr("llm_reasoning._build_deepseek_prompt", lambda *a, **k: "prompt")
    import config as cfg
    monkeypatch.setattr(cfg, "call_deepseek", fake_call)
    from llm_reasoning import generate_prediction_trade_levels
    out = generate_prediction_trade_levels("000001")
    assert captured.get("thinking") is False
    assert out["ok"] is True
    assert out["buy_low"] == 1.0
