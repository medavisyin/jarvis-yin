"""AI briefing items must be translated before Chinese audio narration."""

from __future__ import annotations

import os
import sys

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _p in (_RAG, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _sample_briefing():
    return {
        "per_source_data": [
            {
                "name": "TechCrunch AI",
                "items": [
                    {
                        "title": "OpenAI launches GPT-5 for developers",
                        "summary": "The company said the model is faster and cheaper for API users.",
                    },
                    {
                        "title": "阿里云发布新模型",
                        "summary": "面向企业客户的推理服务。",
                    },
                ],
            }
        ]
    }


def test_translate_briefing_writes_zh_fields():
    from briefing_translate import translate_briefing_data

    calls = []

    def fake_batch(texts):
        calls.append(list(texts))
        return [f"ZH:{t[:20]}" for t in texts]

    out = translate_briefing_data(_sample_briefing(), translate_batch=fake_batch)
    items = out["per_source_data"][0]["items"]
    assert items[0]["title_zh"].startswith("ZH:")
    assert items[0]["summary_zh"].startswith("ZH:")
    assert "title_zh" not in items[1]
    assert out.get("translated") is True
    assert calls and "OpenAI launches GPT-5 for developers" in calls[0]


def test_translate_truncates_long_summary():
    from briefing_translate import SUMMARY_MAX, translate_briefing_data

    data = {
        "per_source_data": [
            {"name": "Arxiv", "items": [{"title": "Paper", "summary": "A" * 900}]}
        ]
    }
    seen = []

    def fake_batch(texts):
        seen.extend(texts)
        return ["译"] * len(texts)

    translate_briefing_data(data, translate_batch=fake_batch)
    summaries = [t for t in seen if t.startswith("A")]
    assert summaries
    assert len(summaries[0]) == SUMMARY_MAX


def test_pick_item_text_prefers_zh():
    from briefing_translate import pick_item_text

    it = {
        "title": "English title",
        "title_zh": "中文标题",
        "summary": "English summary",
        "summary_zh": "中文摘要",
    }
    title, summary = pick_item_text(it, prefer_zh=True)
    assert title == "中文标题"
    assert summary == "中文摘要"
    title_en, summary_en = pick_item_text(it, prefer_zh=False)
    assert title_en == "English title"
    assert summary_en == "English summary"


def test_zh_audio_not_ready_until_translated():
    from briefing_translate import briefing_ready_for_zh_audio

    assert briefing_ready_for_zh_audio({"per_source_data": []}) is False
    assert briefing_ready_for_zh_audio({"translated": True, "per_source_data": []}) is True


def test_daily_fetch_ai_audio_uses_translated_fields():
    path = os.path.join(_RAG, "routes", "daily_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "translate_briefing_data" in src
    assert "pick_item_text" in src
    assert "ai_news_translate" in src
    assert "briefing_ready_for_zh_audio" in src
