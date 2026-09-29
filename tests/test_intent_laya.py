"""Intent order: keywords, then Chinese-to-English, then Laya, then the fast LLM."""

from __future__ import annotations

import os
import sys
import threading
from unittest.mock import patch

_RAG = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))
if _RAG not in sys.path:
    sys.path.insert(0, _RAG)

from intent import Intent, IntentResult, _laya_classify, classify_intent


def _hit(intent: Intent, confidence: float = 0.9) -> IntentResult:
    return IntentResult(
        intent=intent,
        confidence=confidence,
        enhanced_query="translated",
        original_query="original",
        reasoning="laya",
    )


def test_keyword_skips_translation_and_laya():
    with patch("intent._translate_to_english") as translate, patch(
        "intent._laya_classify"
    ) as laya, patch("intent._llm_classify") as llm:
        result = classify_intent("分析一下股票行情")
    assert result.intent == Intent.STOCK_ANALYSIS
    translate.assert_not_called()
    laya.assert_not_called()
    llm.assert_not_called()


def test_chinese_without_keyword_is_translated_then_classified():
    with patch("intent._translate_to_english", return_value="How does the cache work?") as translate, patch(
        "intent._laya_classify", return_value=_hit(Intent.KNOWLEDGE_QA)
    ) as laya, patch("intent._llm_classify") as llm:
        result = classify_intent("那个缓存是怎么做的")
    assert result.intent == Intent.KNOWLEDGE_QA
    translate.assert_called_once()
    assert translate.call_args.args[0] == "那个缓存是怎么做的"
    laya.assert_called_once()
    assert laya.call_args.args[1] == "How does the cache work?"
    assert laya.call_args.args[2] == "那个缓存是怎么做的"
    llm.assert_not_called()


def test_english_skips_translation():
    with patch("intent._translate_to_english") as translate, patch(
        "intent._laya_classify", return_value=_hit(Intent.EXPLAIN_TOPIC)
    ) as laya:
        result = classify_intent("Explain the caching layer in our system")
    assert result.intent == Intent.EXPLAIN_TOPIC
    translate.assert_not_called()
    assert laya.call_args.args[1] == "Explain the caching layer in our system"


def test_low_laya_confidence_uses_fast_llm():
    with patch("intent._translate_to_english") as translate, patch(
        "intent._laya_classify", return_value=_hit(Intent.SMALLTALK, confidence=0.2)
    ), patch("intent._llm_classify", return_value=_hit(Intent.KNOWLEDGE_QA, confidence=0.7)) as llm:
        result = classify_intent("Explain the caching layer in our system")
    assert result.intent == Intent.KNOWLEDGE_QA
    translate.assert_not_called()
    llm.assert_called_once()


def test_laya_failure_uses_fast_llm():
    with patch("intent._laya_classify", return_value=None), patch(
        "intent._llm_classify", return_value=_hit(Intent.KNOWLEDGE_QA, confidence=0.7)
    ) as llm:
        result = classify_intent("Explain the caching layer in our system")
    assert result.intent == Intent.KNOWLEDGE_QA
    llm.assert_called_once()


def test_laya_classify_uses_english_choice_and_keeps_original_query():
    class FakeRouter:
        def __init__(self):
            self.call = None

        def predict(self, text, questions, **kwargs):
            self.call = (text, questions, kwargs)
            return {
                "answers": {
                    "intent": {
                        "choice": "knowledge_qa",
                        "confidence": 0.2,
                        "answer_confidence": 0.91,
                    }
                }
            }

    fake = FakeRouter()
    original = "那个缓存是怎么做的"
    with patch("intent._laya_router", return_value=fake):
        result = _laya_classify(original, "How does the cache work?", original)
    assert result is not None
    assert result.intent == Intent.KNOWLEDGE_QA
    assert result.confidence == 0.91
    assert result.enhanced_query == original
    assert result.original_query == original
    text, questions, kwargs = fake.call
    assert text == "How does the cache work?"
    assert kwargs["model"] == "english"
    assert kwargs["min_confidence"] == 0.6
    assert questions["intent"]["type"] == "choice"


def test_laya_classify_leaves_hub_offline():
    import intent

    class Constants:
        HF_HUB_OFFLINE = False

    previous_module = sys.modules.get("huggingface_hub.constants")
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    sys.modules["huggingface_hub.constants"] = Constants
    os.environ.pop("HF_HUB_OFFLINE", None)
    fake = type("FakeRouter", (), {"predict": lambda *a, **k: {
        "answers": {"intent": {"choice": "knowledge_qa", "answer_confidence": 0.9}}
    }})()
    try:
        with patch("intent._laya_router", return_value=fake):
            result = _laya_classify("How does caching work?", "How does caching work?", "How does caching work?")
        assert result is not None
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert sys.modules["huggingface_hub.constants"].HF_HUB_OFFLINE is True
    finally:
        if previous_module is None:
            sys.modules.pop("huggingface_hub.constants", None)
        else:
            sys.modules["huggingface_hub.constants"] = previous_module
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline
        intent._LAYA_ROUTER = None


def test_laya_router_constructs_once_while_offline():
    import intent

    calls = []

    class FakeRouter:
        def __init__(self):
            calls.append(os.environ.get("HF_HUB_OFFLINE"))

    previous_router = intent._LAYA_ROUTER
    previous_offline = os.environ.get("HF_HUB_OFFLINE")
    intent._LAYA_ROUTER = None
    os.environ.pop("HF_HUB_OFFLINE", None)
    results = []
    start = threading.Barrier(2)

    def build():
        start.wait()
        results.append(intent._laya_router())

    try:
        with patch("laya.Router", FakeRouter):
            threads = [threading.Thread(target=build) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        assert len(calls) == 1
        assert calls[0] == "1"
        assert results[0] is results[1]
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
    finally:
        intent._LAYA_ROUTER = previous_router
        if previous_offline is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous_offline


def test_cjk_translation_reply_skips_laya():
    from unittest.mock import MagicMock

    response = MagicMock()
    response.json.return_value = {"message": {"content": "缓存怎么做的"}}
    with patch("requests.post", return_value=response) as post, patch(
        "intent._laya_classify"
    ) as laya, patch(
        "intent._llm_classify", return_value=_hit(Intent.KNOWLEDGE_QA, confidence=0.7)
    ) as llm:
        result = classify_intent("那个缓存是怎么做的")
    assert result.intent == Intent.KNOWLEDGE_QA
    assert post.call_count == 2
    assert post.call_args.kwargs["json"]["model"] == "qwen3:1.7b"
    laya.assert_not_called()
    llm.assert_called_once()


def test_fewshot_english_translation_is_used():
    import intent
    from unittest.mock import MagicMock

    response = MagicMock()
    response.json.return_value = {
        "message": {"content": "Where is the login flow written in the wiki?"}
    }
    with patch("requests.post", return_value=response) as post:
        translated = intent._translate_to_english("wiki 里登录流程写在哪一页")
    assert translated == "Where is the login flow written in the wiki?"
    messages = post.call_args.kwargs["json"]["messages"]
    assert messages[1]["content"] == "登录失败怎么办"
    assert messages[2]["role"] == "assistant"
    assert post.call_count == 1


def test_cjk_first_reply_retries_and_keeps_english():
    import intent
    from unittest.mock import MagicMock

    echoed = MagicMock()
    echoed.json.return_value = {"message": {"content": "Wiki里登录流程写在哪一页"}}
    english = MagicMock()
    english.json.return_value = {
        "message": {"content": "English: Where is the login flow written in the wiki?"}
    }
    with patch("requests.post", side_effect=[echoed, english]) as post:
        translated = intent._translate_to_english("wiki 里登录流程写在哪一页")
    assert translated == "Where is the login flow written in the wiki?"
    assert post.call_count == 2


def test_translation_failure_skips_laya():
    with patch("intent._translate_to_english", return_value=None), patch(
        "intent._laya_classify"
    ) as laya, patch(
        "intent._llm_classify", return_value=_hit(Intent.KNOWLEDGE_QA, confidence=0.7)
    ) as llm:
        result = classify_intent("那个缓存是怎么做的")
    assert result.intent == Intent.KNOWLEDGE_QA
    laya.assert_not_called()
    llm.assert_called_once()
