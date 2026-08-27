"""Shared RAG result filters (kept import-light for unit tests)."""

from __future__ import annotations

FINANCE_NEWS_ITEM_TYPE = "finance_news"


def exclude_finance_news(
    results: list[dict],
    *,
    include_finance_news: bool = False,
) -> list[dict]:
    """Drop finance_news hits unless the caller opted in."""
    if include_finance_news:
        return list(results)
    return [r for r in results if r.get("item_type") != FINANCE_NEWS_ITEM_TYPE]


def finance_news_must_not_conditions() -> list:
    """Qdrant MustNot clause excluding finance_news payloads."""
    from qdrant_client.models import FieldCondition, MatchValue

    return [FieldCondition(key="item_type", match=MatchValue(value=FINANCE_NEWS_ITEM_TYPE))]
