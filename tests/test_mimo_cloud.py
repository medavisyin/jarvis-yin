"""Cloud model routing accepts MiMo beside GLM."""
from __future__ import annotations

import importlib.util
import os
import sys
import types

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
_STOCK = os.path.join(_SCRIPTS, "stock")
if _STOCK in sys.path:
    sys.path.remove(_STOCK)
for _p in (_SCRIPTS, _RAG):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)
sys.modules.pop("config", None)

import glm_chat  # noqa: E402
import mimo_chat  # noqa: E402
from routes.intensive_reading import _reading_llm  # noqa: E402
from routes.stock import _llm_from_body  # noqa: E402


def test_llm_from_body_accepts_mimo():
    assert _llm_from_body({"llm": "mimo"}) == (True, "mimo")


def test_reading_llm_accepts_mimo():
    assert _reading_llm("mimo") == "mimo"
    assert _reading_llm("other") == "ollama"


def test_call_deepseek_uses_mimo_when_cloud_provider_is_mimo(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "stock_config_mimo_test",
        os.path.join(_STOCK, "config.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    token = glm_chat.set_cloud_llm("mimo")
    monkeypatch.setattr(mod, "get_mimo_key", lambda: "sk-1234567890abcd")
    monkeypatch.setattr(mimo_chat, "make_client", lambda _key: object())
    monkeypatch.setattr(mimo_chat, "complete", lambda _client, _messages, max_tokens=4096: "from-mimo")
    try:
        out = mod.call_deepseek("sys", "user")
    finally:
        glm_chat.reset_cloud_llm(token)
    assert out["ok"] is True
    assert out["content"] == "from-mimo"
    assert out["model"] == "mimo-v2.6-flash"


def test_stock_analyze_mimo_failure_hides_key_and_names_mimo():
    secret = "sk-1234567890abcd"
    from web_api import Flask
    from routes.stock import stock_bp

    fetch = types.ModuleType("fetch_market_data")
    fetch.fetch_daily_ohlcv = lambda _symbol: None
    fetch.fetch_realtime_quote = lambda _symbol: {}
    reasoning = types.ModuleType("llm_reasoning")

    def boom(_symbol, realtime_quote=None, cost_price=None):
        raise RuntimeError(f"Bearer {secret}")

    reasoning.generate_prediction_deepseek = boom
    saved = {name: sys.modules.get(name) for name in ("fetch_market_data", "llm_reasoning")}
    sys.modules["fetch_market_data"] = fetch
    sys.modules["llm_reasoning"] = reasoning
    try:
        app = Flask(__name__)
        app.register_blueprint(stock_bp)
        response = app.test_client().post(
            "/api/stock/analyze/deepseek",
            json={"symbol": "600000", "llm": "mimo"},
        )
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
    assert response.status_code == 500
    error = response.get_json()["error"]
    assert "DeepSeek" not in error
    assert secret not in error
    assert "MiMo" in error
