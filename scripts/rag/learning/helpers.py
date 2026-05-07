"""
Learning session helper functions for the Jarvis RAG agent.

Topic resolution, intent classification for English learning channels,
article content fetching, and web reference search.
"""

import json
import logging
import os
import re
from typing import Optional

from routes.ai_news import _load_ai_kb
from routes.daily_fetch import (
    _load_recent_ai_news_titles,
    _load_recent_world_news_titles,
)

from .constants import LEARNING_SESSION_IDS

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL_FAST = "qwen3:1.7b"


def resolve_topic_from_history(query: str, history: list[dict]) -> str | None:
    """If query is a topic number reference (e.g. '16', 'topic 16'), resolve it
    to the actual topic title from the most recent assistant message that
    contains a topic-selection numbered list."""
    m = re.match(r"^(?:topic\s*)?#?\s*(\d{1,2})\s*$", query.strip(), re.IGNORECASE)
    if not m:
        return None
    target_num = int(m.group(1))
    _topic_markers = ("pick a topic", "type a number", "choose a topic",
                      "select a topic", "topics to choose")
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not any(marker in content.lower() for marker in _topic_markers):
            continue
        numbered = re.findall(r"^\s*(\d{1,2})\.\s+(.+)$", content, re.MULTILINE)
        if not numbered:
            continue
        for num_str, title in numbered:
            clean = title.strip()
            if clean.startswith("**"):
                continue
            if int(num_str) == target_num:
                return clean
    return None


def wants_more_topics(query: str) -> bool:
    """Detect if the user is asking for new/different topics."""
    q = query.lower().strip()
    signals = [
        "more topic", "other topic", "new topic", "different topic",
        "change topic", "switch topic", "another topic",
        "give me more", "show me more", "next topic",
        "refresh topic", "recent topic", "latest topic",
        "list topic", "show topic", "what topic",
        "更多", "换一个",
    ]
    if any(s in q for s in signals):
        return True
    return bool(re.match(r"^(?:topics?|show\s+me|list|recent|latest|refresh)\s*$", q, re.IGNORECASE))


def classify_learning_channel_intent(query: str, topic_titles: list[str],
                                     channel_desc: str) -> dict:
    """Use fast LLM to classify user intent in a learning channel.
    Returns: {"intent": "select_topic"|"more_topics"|"followup"|"off_topic",
              "topic": "<resolved topic title or empty>"}"""
    import requests as _req
    titles_sample = "\n".join(f"- {t}" for t in topic_titles[:20])
    try:
        resp = _req.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL_FAST,
                "messages": [
                    {"role": "system", "content": (
                        f"You classify user input for a learning channel: {channel_desc}\n\n"
                        "Available topics:\n" + titles_sample + "\n\n"
                        "Classify the input into ONE intent:\n"
                        "- select_topic: user wants to learn about a specific topic (number or name)\n"
                        "- more_topics: user wants to see the topic list, refresh it, or see recent/latest topics\n"
                        "- followup: user asks a follow-up question about a previously discussed topic\n"
                        "- off_topic: unrelated to the channel's topics\n\n"
                        "Output ONLY a JSON object: {\"intent\": \"...\", \"topic\": \"...\"}\n"
                        "For select_topic, set topic to the EXACT matching title from the list above.\n"
                        "For other intents, set topic to empty string."
                    )},
                    {"role": "user", "content": query},
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 120, "num_ctx": 1024},
            },
            timeout=10,
        )
        raw = resp.json().get("message", {}).get("content", "").strip()
        json_match = re.search(r"\{[^}]+\}", raw)
        if json_match:
            result = json.loads(json_match.group())
            intent = result.get("intent", "off_topic")
            topic = result.get("topic", "")
            if intent in ("select_topic", "more_topics", "followup", "off_topic"):
                return {"intent": intent, "topic": topic}
    except Exception:
        pass
    return {"intent": "off_topic", "topic": ""}


def resolve_topic_by_name_in_list(query: str, titles: list[str]) -> str | None:
    """Match a query to a title from a given list using partial matching."""
    q = re.sub(r"^(?:drill\s+down\s+(?:to|on|into)?|tell\s+me\s+(?:about|more\s+about)?|"
               r"analyze|explain|teach\s+me\s+(?:about)?|show\s+me|go\s+(?:deeper\s+(?:on|into)?))\s*",
               "", query.strip(), flags=re.IGNORECASE).strip().strip('"\'')
    if not q or len(q) < 3:
        return None
    q_lower = q.lower()
    for title in titles:
        if title.strip().lower() == q_lower:
            return title.strip()
    for title in titles:
        if q_lower in title.strip().lower() or title.strip().lower() in q_lower:
            return title.strip()
    return None


WEB_SEARCH_PROXY = os.environ.get("BRIEFING_PROXY", "")


def resolve_english_topic_by_name(query: str) -> str | None:
    """Try to match a free-text query to a known AI news topic title.
    Supports partial matches like 'drill down to Android Coach' or 'Android Coach'."""
    q = query.strip()
    q = re.sub(
        r"^(?:drill\s+down\s+(?:to|on|into)?|tell\s+me\s+(?:about|more\s+about)?|"
        r"analyze|explain|teach\s+me\s+(?:about)?|show\s+me|go\s+(?:deeper\s+(?:on|into)?))\s*",
        "",
        q,
        flags=re.IGNORECASE,
    ).strip().strip('"\'')
    if not q or len(q) < 3:
        return None
    q_lower = q.lower()
    all_titles = _load_recent_ai_news_titles()
    for title in all_titles:
        if title.strip().lower() == q_lower:
            return title.strip()
    for title in all_titles:
        if q_lower in title.strip().lower() or title.strip().lower() in q_lower:
            return title.strip()
    try:
        kb = _load_ai_kb()
        for item in kb.get("items", []):
            t = item.get("title", "").strip()
            if t and (t.lower() == q_lower or q_lower in t.lower() or t.lower() in q_lower):
                return t
    except Exception:
        pass
    return None


def classify_and_resolve_learning_input(query: str, history: list[dict], session_id: str) -> dict:
    """Classify user input for Tech English or Casual English using LLM + heuristics.
    Returns: {"intent": "select_topic"|"more_topics"|"followup"|"off_topic",
              "resolved_topic": "<topic title or None>"}"""
    q = query.strip()
    if re.match(r"^(?:topic\s*)?#?\s*\d{1,2}\s*$", q, re.IGNORECASE):
        resolved = resolve_topic_from_history(query, history)
        return {"intent": "select_topic", "resolved_topic": resolved}
    if wants_more_topics(q):
        return {"intent": "more_topics", "resolved_topic": None}

    is_tech = session_id == LEARNING_SESSION_IDS.get("english_learning")
    if is_tech:
        all_titles = _load_recent_ai_news_titles()
        channel_desc = "Tech English - learning English through AI news articles"
    else:
        all_items = _load_recent_world_news_titles()
        all_titles = [it["title"] for it in all_items]
        channel_desc = "Casual English - learning everyday English through world news"

    name_match = resolve_english_topic_by_name(q) if is_tech else resolve_topic_by_name_in_list(q, all_titles)
    if name_match:
        return {"intent": "select_topic", "resolved_topic": name_match}

    classified = classify_learning_channel_intent(q, all_titles, channel_desc)
    intent = classified["intent"]
    llm_topic = classified.get("topic", "")

    if intent == "select_topic" and llm_topic:
        for title in all_titles:
            if title.strip().lower() == llm_topic.strip().lower():
                return {"intent": "select_topic", "resolved_topic": title.strip()}
        if is_tech:
            fallback = resolve_english_topic_by_name(llm_topic)
        else:
            fallback = resolve_topic_by_name_in_list(llm_topic, all_titles)
        if fallback:
            return {"intent": "select_topic", "resolved_topic": fallback}

    return {"intent": intent, "resolved_topic": None}


def fetch_fresh_topics(session_id: str, history: list[dict]) -> str:
    """Fetch topics not already shown in the conversation history."""
    already_shown = set()
    for msg in history:
        if msg.get("role") != "assistant":
            continue
        for title in re.findall(r"^\s*\d{1,2}\.\s+(.+)$", msg.get("content", ""), re.MULTILINE):
            already_shown.add(title.strip().lower())

    lines = []
    if session_id == LEARNING_SESSION_IDS.get("english_learning"):
        all_titles = _load_recent_ai_news_titles()
        fresh = [t for t in all_titles if t.strip().lower() not in already_shown]
        for i, t in enumerate(fresh[:20], 1):
            lines.append(f"{i}. {t}")
    elif session_id == LEARNING_SESSION_IDS.get("casual_english"):
        all_items = _load_recent_world_news_titles()
        fresh = [it for it in all_items if it["title"].strip().lower() not in already_shown]
        for i, it in enumerate(fresh[:20], 1):
            lines.append(f"{i}. [{it['category']}] {it['title']}")
    return "\n".join(lines)


def web_search_references(query: str, num_results: int = 5) -> str:
    """Search the web for learning references using DuckDuckGo HTML (no API key).
    Uses the same SOCKS proxy as the fetcher scripts."""
    try:
        import httpx
        from html.parser import HTMLParser

        class _DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results: list[dict] = []
                self._in_link = False
                self._cur: dict = {}

            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if tag == "a" and "result__a" in d.get("class", ""):
                    self._in_link = True
                    href = d.get("href", "")
                    if "uddg=" in href:
                        from urllib.parse import unquote, urlparse, parse_qs

                        parsed = parse_qs(urlparse(href).query)
                        href = unquote(parsed.get("uddg", [href])[0])
                    self._cur = {"url": href, "title": ""}

            def handle_data(self, data):
                if self._in_link:
                    self._cur["title"] += data

            def handle_endtag(self, tag):
                if tag == "a" and self._in_link:
                    self._in_link = False
                    if self._cur.get("url", "").startswith("http"):
                        self.results.append(self._cur)
                    self._cur = {}

        kwargs: dict = {
            "timeout": 15,
            "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis/1.0"},
            "params": {"q": query},
        }
        if WEB_SEARCH_PROXY:
            kwargs["proxy"] = WEB_SEARCH_PROXY
        resp = httpx.get("https://html.duckduckgo.com/html/", **kwargs)
        if resp.status_code != 200:
            return ""
        parser = _DDGParser()
        parser.feed(resp.text)
        refs = parser.results[:num_results]
        if not refs:
            return ""
        lines = ["\n📚 Learn more:"]
        for r in refs:
            lines.append(f"- [{r['title'].strip()}]({r['url']})")
        return "\n".join(lines)
    except Exception as e:
        print(f"[web-search] Failed: {e}")
        return ""
