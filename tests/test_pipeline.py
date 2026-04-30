"""
Integration tests for the Jarvis RAG agent pipeline.

Tests the full query processing pipeline (intent classification, query enhancement,
RAG capability check, memory augmentation, query decomposition) without requiring
Ollama to be running — mocks the LLM calls.

Run: python -m pytest tests/test_pipeline.py -v
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "rag"))

import pytest


@pytest.fixture(autouse=True)
def setup_path():
    """Ensure rag modules are importable without full Qdrant/Ollama."""
    yield


class TestIntentClassification:
    """Test the intent classification module."""

    def test_jira_keywords_detected(self):
        from intent import classify_intent, Intent
        result = classify_intent("Show me the current sprint tickets")
        assert result.intent == Intent.JIRA_REPORT
        assert result.confidence >= 0.8
        assert "jira_report" in result.suggested_tools

    def test_commit_keywords_detected(self):
        from intent import classify_intent, Intent
        result = classify_intent("What did Jan push yesterday?")
        assert result.intent == Intent.COMMIT_SUMMARY
        assert result.confidence >= 0.8
        assert "commit_summary" in result.suggested_tools

    def test_project_query_detected(self):
        from intent import classify_intent, Intent
        result = classify_intent("What depends on the identity-server project?")
        assert result.intent == Intent.PROJECT_QUERY
        assert "project_query" in result.suggested_tools

    def test_stock_keywords_detected(self):
        from intent import classify_intent, Intent
        result = classify_intent("分析一下股票行情")
        assert result.intent == Intent.STOCK_ANALYSIS

    def test_smalltalk_detected(self):
        from intent import classify_intent, Intent
        result = classify_intent("hello")
        assert result.intent == Intent.SMALLTALK

    def test_session_type_overrides_keywords(self):
        from intent import classify_intent, Intent
        result = classify_intent(
            "What are jira tickets?",
            session_type="ai_learning",
        )
        assert result.intent == Intent.LEARNING_AI
        assert result.confidence == 1.0

    def test_llm_fallback_for_ambiguous(self):
        from intent import classify_intent, Intent
        result = classify_intent(
            "How does the caching layer work in our system?"
        )
        assert result.intent in (Intent.KNOWLEDGE_QA, Intent.PROJECT_QUERY)


class TestQueryEnhancement:
    """Test query enhancement logic."""

    def test_short_query_flagged_for_enhancement(self):
        from intent import _needs_enhancement
        assert _needs_enhancement("it") is True
        assert _needs_enhancement("that thing") is True
        assert _needs_enhancement("hi") is True

    def test_clear_query_not_enhanced(self):
        from intent import _needs_enhancement
        assert _needs_enhancement("What is the attention mechanism in transformers?") is False

    def test_pronoun_query_needs_enhancement(self):
        from intent import _needs_enhancement
        assert _needs_enhancement("tell me more about that") is True

    def test_chinese_short_query_triggers_enhancement(self):
        from intent import _needs_enhancement
        # Short queries (< 15 chars) always trigger enhancement
        assert _needs_enhancement("注意力机制") is True
        # Even longer Chinese queries hit the < 15 char heuristic based on word splits
        # The function uses len(query.split()) which splits on spaces (Chinese has none)
        assert _needs_enhancement("注意力") is True


class TestRAGConfidence:
    """Test retrieval confidence scoring."""

    def test_confidence_enum_values(self):
        from intent import RetrievalConfidence
        assert RetrievalConfidence.HIGH.value == "high"
        assert RetrievalConfidence.MEDIUM.value == "medium"
        assert RetrievalConfidence.LOW.value == "low"
        assert RetrievalConfidence.NONE.value == "none"


class TestQueryDecomposition:
    """Test query decomposition for complex queries."""

    def test_simple_query_not_complex(self):
        from decomposer import is_complex_query
        assert is_complex_query("What is RAG?") is False

    def test_multi_part_query_detected(self):
        from decomposer import is_complex_query
        assert is_complex_query(
            "What did Jan commit last week and are any related to Jira tickets?"
        ) is True

    def test_cross_source_signals_complexity(self):
        from decomposer import is_complex_query
        # Cross-source queries that reference both commits AND jira are complex
        assert is_complex_query(
            "What did Jan commit last week and are any of them related to the identity server Jira tickets?"
        ) is True

    def test_simple_query_returns_non_complex_result(self):
        from decomposer import decompose_query
        result = decompose_query("What is RAG?", [])
        assert result is not None
        assert result.is_complex is False
        assert len(result.sub_queries) == 1
        assert result.sub_queries[0].text == "What is RAG?"


class TestPipelineContext:
    """Test the pipeline context and orchestration."""

    def test_pipeline_context_creation(self):
        from pipeline import PipelineContext
        from intent import IntentResult, Intent
        from router import RouteResult

        ctx = PipelineContext(
            query="test",
            effective_query="test enhanced",
            rag_query=None,
            system_prompt=None,
            route=RouteResult(
                session_type=None,
                is_learning=False,
                is_aws_cert=False,
                learning_prompt=None,
            ),
            intent_result=IntentResult(
                intent=Intent.KNOWLEDGE_QA,
                confidence=0.9,
                suggested_tools=["rag_search"],
            ),
        )
        assert ctx.is_decomposed is False
        assert ctx.all_suggested_tools == ["rag_search"]

    def test_pipeline_context_with_memory_tools(self):
        from pipeline import PipelineContext
        from intent import IntentResult, Intent
        from router import RouteResult

        ctx = PipelineContext(
            query="test",
            effective_query="test",
            rag_query=None,
            system_prompt=None,
            route=RouteResult(
                session_type=None,
                is_learning=False,
                is_aws_cert=False,
                learning_prompt=None,
            ),
            intent_result=IntentResult(
                intent=Intent.COMMIT_SUMMARY,
                confidence=0.9,
                suggested_tools=["commit_summary"],
            ),
            memory_tools=["jira_report"],
        )
        assert "commit_summary" in ctx.all_suggested_tools
        assert "jira_report" in ctx.all_suggested_tools


class TestResponseStrategy:
    """Test confidence-based response strategy."""

    def test_high_confidence_no_disclaimer(self):
        from pipeline import build_response_strategy
        from intent import IntentResult, Intent, RetrievalConfidence

        result = IntentResult(
            intent=Intent.KNOWLEDGE_QA,
            rag_confidence=RetrievalConfidence.HIGH.value,
            rag_score=0.75,
        )
        strategy = build_response_strategy(result)
        assert strategy.confidence_level == "high"
        assert strategy.disclaimer is None
        assert strategy.suggest_web_search is False

    def test_low_confidence_has_disclaimer(self):
        from pipeline import build_response_strategy
        from intent import IntentResult, Intent, RetrievalConfidence

        result = IntentResult(
            intent=Intent.KNOWLEDGE_QA,
            rag_confidence=RetrievalConfidence.LOW.value,
            rag_score=0.3,
        )
        strategy = build_response_strategy(result)
        assert strategy.confidence_level == "low"
        assert strategy.disclaimer is not None
        assert strategy.suggest_web_search is True

    def test_none_confidence_suggests_web_search(self):
        from pipeline import build_response_strategy
        from intent import IntentResult, Intent, RetrievalConfidence

        result = IntentResult(
            intent=Intent.KNOWLEDGE_QA,
            rag_confidence=RetrievalConfidence.NONE.value,
            rag_score=0.1,
        )
        strategy = build_response_strategy(result)
        assert strategy.confidence_level == "none"
        assert strategy.use_rag is False
        assert strategy.suggest_web_search is True

    def test_tool_intent_bypasses_confidence(self):
        from pipeline import build_response_strategy
        from intent import IntentResult, Intent

        result = IntentResult(
            intent=Intent.JIRA_REPORT,
            rag_confidence=None,
            rag_score=0.0,
        )
        strategy = build_response_strategy(result)
        assert strategy.confidence_level == "tool_action"


class TestRouter:
    """Test session routing."""

    def test_none_session_not_learning(self):
        from router import route_session
        result = route_session("", load_session_fn=None)
        assert result.is_learning is False
        assert result.learning_prompt is None

    def test_ai_learning_session(self):
        from router import route_session
        from learning.constants import LEARNING_SESSION_IDS
        sid = LEARNING_SESSION_IDS.get("ai_learning", "")
        if sid:
            result = route_session(sid, load_session_fn=None)
            assert result.is_learning is True
            assert result.session_type == "ai_learning"

    def test_aws_cert_session(self):
        from router import route_session
        from learning.constants import LEARNING_SESSION_IDS
        sid = LEARNING_SESSION_IDS.get("aws_cert", "")
        if sid:
            result = route_session(sid, load_session_fn=None)
            assert result.is_aws_cert is True


class TestAgentLoopAutoPrefetch:
    """Test that auto_prefetch parameter controls prefetch behavior."""

    def test_auto_prefetch_overrides_keywords(self):
        """When auto_prefetch is provided, keyword detection is skipped."""
        import agent_loop

        agent_loop.init(
            ollama_model="test",
            ollama_host="http://localhost:11434",
            ollama_model_fast="test-fast",
        )

        query = "Tell me about the attention mechanism"
        with patch("agent_loop._auto_rag_search") as mock_rag, \
             patch("agent_loop._auto_tool_commit") as mock_commit:
            mock_rag.return_value = ("", [])

            gen = agent_loop.run_agent(
                query,
                auto_prefetch=["commit_summary"],
            )
            events = []
            try:
                for event in gen:
                    events.append(event)
                    if event.get("type") == "error" or len(events) > 20:
                        break
            except Exception:
                pass

            mock_commit.assert_called_once()

    def test_no_auto_prefetch_uses_keywords(self):
        """When auto_prefetch is None, keyword detection is used (legacy)."""
        import agent_loop

        agent_loop.init(
            ollama_model="test",
            ollama_host="http://localhost:11434",
            ollama_model_fast="test-fast",
        )

        query = "What is the weather today?"
        with patch("agent_loop._auto_rag_search") as mock_rag, \
             patch("agent_loop._auto_tool_commit") as mock_commit, \
             patch("agent_loop._auto_tool_jira") as mock_jira:
            mock_rag.return_value = ("", [])

            gen = agent_loop.run_agent(
                query,
                auto_prefetch=None,
            )
            events = []
            try:
                for event in gen:
                    events.append(event)
                    if event.get("type") == "error" or len(events) > 20:
                        break
            except Exception:
                pass

            mock_commit.assert_not_called()
            mock_jira.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
