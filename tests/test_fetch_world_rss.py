"""Fixture parse for catalog-driven world RSS (People's Daily / Xinhua)."""

from __future__ import annotations

import importlib.util
import os
import sys
import types

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_FETCHER = os.path.join(_SCRIPTS, "fetchers", "news", "fetch-world-rss.py")
_PIPELINE = os.path.join(_SCRIPTS, "pipeline")

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Xinhua World</title>
    <item>
      <title>UN vote in New York</title>
      <link>https://english.news.cn/example</link>
      <description>Security Council meets.</description>
      <pubDate>Sun, 20 Sep 2026 01:00:00 GMT</pubDate>
    </item>
    <item>
      <title>UN vote in New York</title>
      <link>https://english.news.cn/dup</link>
      <description>duplicate title</description>
    </item>
  </channel>
</rss>
"""


def _load_fetcher(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["fetch-world-rss.py", str(tmp_path), "xinhua"])
    for p in (_SCRIPTS, _PIPELINE, os.path.join(_SCRIPTS, "fetchers")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("fetch_world_rss_under_test", _FETCHER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_fetch_world_rss_parses_items_from_http_body(monkeypatch, tmp_path):
    captured = {}

    class _Resp:
        text = _RSS
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _Resp()

    httpx = types.SimpleNamespace(get=fake_get)
    monkeypatch.setitem(sys.modules, "httpx", httpx)
    mod = _load_fetcher(monkeypatch, tmp_path)
    items = mod.fetch_items("xinhua")
    assert captured["url"]
    titles = [it["title"] for it in items]
    assert titles == ["UN vote in New York"]
    assert items[0]["url"] == "https://english.news.cn/example"
    assert items[0]["category"] in ("politics", "economics", "technology", "science")
