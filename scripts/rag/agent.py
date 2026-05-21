"""
Jarvis — AI-powered RAG assistant using Qwen3-VL:8b via Ollama.

Answers questions with context from the Qdrant RAG store, performs multi-step
reasoning via tool calling, analyzes images, and invokes available skills
(Jira, commit summaries, briefing search, Confluence) as tools.

Usage:
  python agent.py [port]
  Opens at http://localhost:18889 (or custom port)

Dependencies: pip install ollama qdrant-client sentence-transformers flask pypdf
"""
import base64
import glob
import json
import logging
import os
import re
import uuid
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from flask import Flask, Response, request, jsonify, render_template_string, make_response, send_file

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import (
    CHAT_SESSIONS_DIR,
    JIRA_REPORT_SCRIPT,
    KNOWLEDGE_ROOT,
    NOTES_FILE,
    PROJECT_GRAPH_PATH,
    REPORTS_ROOT,
    SNAPSHOT_PATH,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLLAMA_MODEL = os.environ.get("RAG_AGENT_MODEL", "qwen3.5:4b")
OLLAMA_MODEL_FAST = "qwen3:1.7b"
OLLAMA_HOST = "http://localhost:11434"
COLLECTION = "ai_briefings"
VECTOR_SIZE = 384
JIRA_SCRIPT = JIRA_REPORT_SCRIPT
MAX_AGENT_ITERATIONS = 8
TOOL_TIMEOUT_SECONDS = 120

REPO_CONFIG = [
    {"name": "P4M Next", "path": "d:/projects/p4m"},
    {"name": "Admin App", "path": "d:/projects/admin-app"},
    {"name": "Core Framework", "path": "d:/projects/core-framework"},
    {"name": "Vaadin UI", "path": "d:/projects/vaadin-ui"},
    {"name": "AWS Infrastructure P4M EKS", "path": "d:/p4m_cloud_project/aws-infra-p4m-eks"},
    {"name": "RIS Utilization Dashboard", "path": "D:/cto/scm/ris-utilization-dashboard"},
    {"name": "B4M Next", "path": "d:/projects/b4m.next"},
    {"name": "Application Server", "path": "d:/projects/applicationserver"},
    {"name": "Apache Dist", "path": "d:/projects/apache-dist"},
    {"name": "Communication Stack", "path": "d:/projects/communication-stack"},
    {"name": "Identity Server", "path": "d:/projects/identityserver"},
    {"name": "Keycloak", "path": "d:/projects/keycloak"},
    {"name": "Local Gateway", "path": "d:/projects/local-gateway"},
    {"name": "Local Gateway Plugins", "path": "d:/projects/local-gateway-plugins"},
    {"name": "Parent", "path": "d:/projects/parent"},
    {"name": "SMS Service", "path": "d:/projects/sms-service"},
    {"name": "SMS Service Client", "path": "d:/projects/sms-service-client"},
    {"name": "Teleradiology Cloud Backend", "path": "d:/projects/teleradiology-cloud-backend"},
]

from prompts import (
    SYSTEM_PROMPT_FULL,
    SYSTEM_PROMPT_COMPACT,
    SYSTEM_PROMPT_PROJECT_ADDON,
    SYSTEM_PROMPT_AI_LEARNING,
    SYSTEM_PROMPT_ENGLISH_LEARNING,
    SYSTEM_PROMPT_CASUAL_ENGLISH,
    SYSTEM_PROMPT_AWS_CERT,
    SYSTEM_PROMPT_DEEP_DIVE,
)

# ---------------------------------------------------------------------------
# RAG engine (imported from rag_engine.py)
# ---------------------------------------------------------------------------
from rag_engine import (
    get_embed_model as _get_embed_model,
    get_qdrant as _get_qdrant,
    get_qdrant_points,
    sync_qdrant_points_from_snapshot as _sync_qdrant_points_from_snapshot,
    batch_encode as _batch_encode,
    vector_search as _vector_search,
    load_project_graph as _load_project_graph,
    auto_rag_search as _auto_rag_search,
)

# ---------------------------------------------------------------------------
# Agent loop (imported from agent_loop.py)
# ---------------------------------------------------------------------------
import agent_loop
agent_loop.init(
    ollama_model=OLLAMA_MODEL,
    ollama_host=OLLAMA_HOST,
    ollama_model_fast=OLLAMA_MODEL_FAST,
    max_agent_iterations=MAX_AGENT_ITERATIONS,
)
from agent_loop import run_agent

# ---------------------------------------------------------------------------
# Conversation memory store (imported from memory/ package)
# ---------------------------------------------------------------------------
from memory.store import init_memory_store
from config import MEMORY_SNAPSHOT_PATH
from rag_engine import get_embed_model

init_memory_store(
    snapshot_path=MEMORY_SNAPSHOT_PATH,
    embed_model_fn=get_embed_model,
)

app = Flask(__name__)




# ===================================================================
# TOOL IMPLEMENTATIONS
# ===================================================================

# ===================================================================
# TOOL IMPLEMENTATIONS (from tools/ package)
# ===================================================================

from tools import (
    TOOL_SCHEMAS, register_tools, execute_tool as _execute_tool,
    get_all_tool_functions, init_tools, tool_commit_summary, tool_jira_report,
)

init_tools(
    reports_root=REPORTS_ROOT,
    jira_script=JIRA_SCRIPT,
    tool_timeout=TOOL_TIMEOUT_SECONDS,
    repo_config=REPO_CONFIG,
)
TOOL_FUNCTIONS = get_all_tool_functions()
register_tools(TOOL_FUNCTIONS)
agent_loop.register_auto_tools(
    commit_fn=tool_commit_summary,
    jira_fn=tool_jira_report,
)


# ===================================================================
# FLASK ROUTES
# ===================================================================

from learning import LEARNING_SESSION_IDS as _LEARNING_SESSION_IDS
from learning.helpers import (
    classify_and_resolve_learning_input as _classify_and_resolve_learning_input,
    fetch_fresh_topics as _fetch_fresh_topics,
    resolve_topic_from_history as _resolve_topic_from_history,
    wants_more_topics as _wants_more_topics,
    web_search_references as _web_search_references,
)


def _fetch_source_url_content(url: str, timeout: int = 20) -> tuple:
    """Fetch a URL and return (text_content, error_string).
    Uses the same SOCKS proxy as the fetcher scripts."""
    if not url:
        return "", "No URL provided"
    try:
        import httpx
        proxy = os.environ.get("BRIEFING_PROXY", "")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Jarvis/1.0)",
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        }
        client_kwargs = {"timeout": timeout, "follow_redirects": True}
        if proxy:
            client_kwargs["proxy"] = proxy
        with httpx.Client(**client_kwargs) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            raw = r.text

        if "html" in content_type.lower() or raw.strip().startswith("<!") or raw.strip().startswith("<html"):
            text = _html_to_text(raw)
        else:
            text = raw

        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text, ""
    except Exception as e:
        return "", str(e)[:200]


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text, stripping tags and scripts."""
    import html as html_mod
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = html_mod.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _read_raw_file_content(raw_file_ref: str) -> str:
    """Read a raw/*.md file from the most recent reports directory."""
    for d_offset in range(7):
        dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        raw_path = os.path.join(REPORTS_ROOT, dt, raw_file_ref)
        if os.path.isfile(raw_path):
            try:
                with open(raw_path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                continue
    return ""


def _fetch_article_content(title: str, session_id: str) -> str:
    """Fetch the full article summary/content for a given topic title.
    Searches world news JSON (for casual english), briefing JSON (for tech english),
    the learning roadmap + docs (for AI learning), or AWS cert study notes."""
    title_lower = title.strip().lower()
    if session_id == _LEARNING_SESSION_IDS.get("aws_cert"):
        parts = []
        import re as _re2
        dm = _re2.search(r"domain\s*(\d)", title_lower)
        _aws_domain_file_map = {
            "1": "01-ai-ml-fundamentals.md",
            "2": "02-genai-fundamentals.md",
            "3": "03-foundation-models.md",
            "4": "04-responsible-ai.md",
            "5": "05-security-compliance.md",
        }
        _aws_topic_file_hints = {
            "polly": "06-aws-managed-ai-services.md",
            "comprehend": "06-aws-managed-ai-services.md",
            "rekognition": "06-aws-managed-ai-services.md",
            "lex": "06-aws-managed-ai-services.md",
            "transcribe": "06-aws-managed-ai-services.md",
            "translate": "06-aws-managed-ai-services.md",
            "textract": "06-aws-managed-ai-services.md",
            "personalize": "06-aws-managed-ai-services.md",
            "forecast": "06-aws-managed-ai-services.md",
            "kendra": "06-aws-managed-ai-services.md",
            "fraud detector": "06-aws-managed-ai-services.md",
            "mturk": "06-aws-managed-ai-services.md",
            "mechanical turk": "06-aws-managed-ai-services.md",
            "a2i": "06-aws-managed-ai-services.md",
            "augmented ai": "06-aws-managed-ai-services.md",
            "deepracer": "06-aws-managed-ai-services.md",
            "managed ai": "06-aws-managed-ai-services.md",
            "prompt engineering": "03-foundation-models.md",
            "rag": "03-foundation-models.md",
            "retrieval augmented": "03-foundation-models.md",
            "rlhf": "03-foundation-models.md",
            "responsible ai": "04-responsible-ai.md",
            "bias": "04-responsible-ai.md",
            "clarify": "03-foundation-models.md",
            "model monitor": "03-foundation-models.md",
            "guardrail": "02-genai-fundamentals.md",
            "bedrock": "02-genai-fundamentals.md",
            "sagemaker": "01-ai-ml-fundamentals.md",
            "genai": "02-genai-fundamentals.md",
            "generative ai": "02-genai-fundamentals.md",
            "security": "05-security-compliance.md",
            "compliance": "05-security-compliance.md",
            "encryption": "05-security-compliance.md",
            "macie": "05-security-compliance.md",
            "privatelink": "05-security-compliance.md",
        }
        aws_notes_dir = os.path.join(KNOWLEDGE_ROOT, "notes", "aws_ai_p1")
        if os.path.isdir(aws_notes_dir):
            target_files = []
            if dm:
                d_num = dm.group(1)
                if d_num in _aws_domain_file_map:
                    target_files = [_aws_domain_file_map[d_num]]
            else:
                for hint_key, hint_file in _aws_topic_file_hints.items():
                    if hint_key in title_lower:
                        target_files = [hint_file]
                        break
                if not target_files:
                    target_files = sorted(f for f in os.listdir(aws_notes_dir)
                                          if f.endswith(".md"))
            for fname in target_files:
                fpath = os.path.join(aws_notes_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if title_lower in content.lower() or dm:
                        if dm:
                            parts.append(f"From {fname}:\n\n{content[:6000]}")
                        else:
                            sections = _re2.split(r"(?=^## )", content,
                                                  flags=_re2.MULTILINE)
                            for section in sections:
                                if title_lower in section.lower():
                                    parts.append(
                                        f"From {fname}:\n\n{section[:5000]}")
                                    break
                            if not parts:
                                parts.append(f"From {fname}:\n\n{content[:5000]}")
                        if len(parts) >= 3:
                            break
                except OSError:
                    continue
        if not parts:
            roadmap = _load_aws_cert_roadmap()
            if roadmap:
                sections = _re2.split(r"(?=^## )", roadmap, flags=_re2.MULTILINE)
                for section in sections:
                    if title_lower in section.lower():
                        parts.append(section[:3000])
                        break
        return "\n\n---\n\n".join(parts) if parts else ""
    elif session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
        parts = []
        import re as _re_ai

        _ai_domain_file_map = {
            "1": "01-llm-foundations.md",
            "2": "02-tokens-embeddings.md",
            "3": "03-prompt-engineering.md",
            "4": "04-rag.md",
            "5": "05-fine-tuning.md",
            "6": "06-ai-engineering.md",
            "7": "07-evaluation-safety.md",
            "8": "08-ai-news-digest.md",
        }
        _ai_topic_file_hints = {
            "transformer": "01-llm-foundations.md",
            "attention": "01-llm-foundations.md",
            "self-attention": "01-llm-foundations.md",
            "gpt": "01-llm-foundations.md",
            "bert": "01-llm-foundations.md",
            "encoder": "01-llm-foundations.md",
            "decoder": "01-llm-foundations.md",
            "foundation model": "01-llm-foundations.md",
            "scaling law": "01-llm-foundations.md",
            "multimodal": "01-llm-foundations.md",
            "clip": "01-llm-foundations.md",
            "blip": "01-llm-foundations.md",
            "token": "02-tokens-embeddings.md",
            "tokeniz": "02-tokens-embeddings.md",
            "bpe": "02-tokens-embeddings.md",
            "embedding": "02-tokens-embeddings.md",
            "word2vec": "02-tokens-embeddings.md",
            "sentence-bert": "02-tokens-embeddings.md",
            "sbert": "02-tokens-embeddings.md",
            "contrastive": "02-tokens-embeddings.md",
            "cosine": "02-tokens-embeddings.md",
            "clustering": "02-tokens-embeddings.md",
            "bertopic": "02-tokens-embeddings.md",
            "umap": "02-tokens-embeddings.md",
            "classification": "02-tokens-embeddings.md",
            "setfit": "02-tokens-embeddings.md",
            "prompt": "03-prompt-engineering.md",
            "chain-of-thought": "03-prompt-engineering.md",
            "chain of thought": "03-prompt-engineering.md",
            "cot": "03-prompt-engineering.md",
            "few-shot": "03-prompt-engineering.md",
            "zero-shot": "03-prompt-engineering.md",
            "temperature": "03-prompt-engineering.md",
            "sampling": "03-prompt-engineering.md",
            "top-p": "03-prompt-engineering.md",
            "jailbreak": "03-prompt-engineering.md",
            "prompt injection": "03-prompt-engineering.md",
            "langchain": "03-prompt-engineering.md",
            "memory": "03-prompt-engineering.md",
            "rag": "04-rag.md",
            "retrieval": "04-rag.md",
            "retrieval-augmented": "04-rag.md",
            "vector db": "04-rag.md",
            "vector database": "04-rag.md",
            "qdrant": "04-rag.md",
            "bm25": "04-rag.md",
            "hybrid search": "04-rag.md",
            "rerank": "04-rag.md",
            "cross-encoder": "04-rag.md",
            "chunk": "04-rag.md",
            "hyde": "04-rag.md",
            "self-rag": "04-rag.md",
            "crag": "04-rag.md",
            "agent": "04-rag.md",
            "react": "04-rag.md",
            "tool calling": "04-rag.md",
            "fine-tun": "05-fine-tuning.md",
            "finetun": "05-fine-tuning.md",
            "lora": "05-fine-tuning.md",
            "qlora": "05-fine-tuning.md",
            "peft": "05-fine-tuning.md",
            "sft": "05-fine-tuning.md",
            "rlhf": "05-fine-tuning.md",
            "dpo": "05-fine-tuning.md",
            "alignment": "05-fine-tuning.md",
            "preference": "05-fine-tuning.md",
            "instruction tuning": "05-fine-tuning.md",
            "dataset engineering": "05-fine-tuning.md",
            "model merging": "05-fine-tuning.md",
            "inference": "06-ai-engineering.md",
            "quantiz": "06-ai-engineering.md",
            "gguf": "06-ai-engineering.md",
            "vllm": "06-ai-engineering.md",
            "ollama": "06-ai-engineering.md",
            "llama.cpp": "06-ai-engineering.md",
            "deploy": "06-ai-engineering.md",
            "serving": "06-ai-engineering.md",
            "mlops": "06-ai-engineering.md",
            "llmops": "06-ai-engineering.md",
            "monitoring": "06-ai-engineering.md",
            "feedback": "06-ai-engineering.md",
            "production": "06-ai-engineering.md",
            "guardrail": "06-ai-engineering.md",
            "cach": "06-ai-engineering.md",
            "evaluat": "07-evaluation-safety.md",
            "benchmark": "07-evaluation-safety.md",
            "perplexity": "07-evaluation-safety.md",
            "bleu": "07-evaluation-safety.md",
            "rouge": "07-evaluation-safety.md",
            "bertscore": "07-evaluation-safety.md",
            "hallucination": "07-evaluation-safety.md",
            "bias": "07-evaluation-safety.md",
            "responsible ai": "07-evaluation-safety.md",
            "safety": "07-evaluation-safety.md",
            "security": "07-evaluation-safety.md",
            "red team": "07-evaluation-safety.md",
            "news": "08-ai-news-digest.md",
            "latest": "08-ai-news-digest.md",
            "recent": "08-ai-news-digest.md",
            "trending": "08-ai-news-digest.md",
            "digest": "08-ai-news-digest.md",
        }

        dm = _re_ai.search(r"domain\s*(\d)", title_lower)
        ai_notes_dir = os.path.join(KNOWLEDGE_ROOT, "notes", "ai_learning")

        if os.path.isdir(ai_notes_dir):
            target_files = []
            if dm:
                d_num = dm.group(1)
                if d_num in _ai_domain_file_map:
                    target_files = [_ai_domain_file_map[d_num]]
            else:
                for hint_key, hint_file in _ai_topic_file_hints.items():
                    if hint_key in title_lower:
                        target_files = [hint_file]
                        break
                if not target_files:
                    target_files = sorted(
                        f for f in os.listdir(ai_notes_dir)
                        if f.endswith(".md")
                    )

            for fname in target_files:
                fpath = os.path.join(ai_notes_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if title_lower in content.lower() or dm:
                        if dm:
                            parts.append(f"From {fname}:\n\n{content[:6000]}")
                        else:
                            sections = _re_ai.split(
                                r"(?=^## )", content, flags=_re_ai.MULTILINE
                            )
                            for section in sections:
                                if title_lower in section.lower():
                                    parts.append(
                                        f"From {fname}:\n\n{section[:5000]}"
                                    )
                                    break
                            if not parts:
                                parts.append(
                                    f"From {fname}:\n\n{content[:5000]}"
                                )
                        if len(parts) >= 3:
                            break
                except OSError:
                    continue

        if not parts:
            roadmap = _load_ai_learning_roadmap()
            if roadmap:
                sections = _re_ai.split(
                    r"(?=^## )", roadmap, flags=_re_ai.MULTILINE
                )
                for section in sections:
                    if title_lower in section.lower():
                        parts.append(section[:3000])
                        break

        return "\n\n---\n\n".join(parts) if parts else ""
    elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
        for d_offset in range(7):
            dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            wn_path = os.path.join(REPORTS_ROOT, dt, "world-news", "world-news-data.json")
            if not os.path.isfile(wn_path):
                wn_path = os.path.join(REPORTS_ROOT, dt, "world-news-data.json")
            if os.path.isfile(wn_path):
                try:
                    with open(wn_path, "r", encoding="utf-8") as f:
                        wdata = json.load(f)
                    for cat in wdata.get("categories", []):
                        cat_name = cat.get("label", cat.get("category", ""))
                        for article in cat.get("items", cat.get("articles", [])):
                            if article.get("title", "").strip().lower() == title_lower:
                                parts = [f"Title: {article.get('title', '')}"]
                                if cat_name:
                                    parts.append(f"Category: {cat_name}")
                                if article.get("source"):
                                    parts.append(f"Source: {article['source']}")
                                if article.get("date"):
                                    parts.append(f"Date: {article['date']}")
                                if article.get("url"):
                                    parts.append(f"URL: {article['url']}")
                                if article.get("summary"):
                                    parts.append(f"\nSummary:\n{article['summary']}")
                                if article.get("body"):
                                    parts.append(f"\nFull content:\n{article['body'][:5000]}")
                                points = article.get("points", [])
                                if points and isinstance(points, list):
                                    parts.append("\nKey points:")
                                    for p in points:
                                        parts.append(f"- {p}")
                                if article.get("commentary"):
                                    parts.append(f"\nCommentary:\n{article['commentary']}")
                                if article.get("analysis"):
                                    parts.append(f"\nAnalysis:\n{article['analysis']}")
                                return "\n".join(parts)
                except Exception:
                    continue
    elif session_id == _LEARNING_SESSION_IDS.get("english_learning"):
        matched_item = None
        matched_source_name = ""
        for d_offset in range(7):
            if matched_item:
                break
            dt = (datetime.now() - timedelta(days=d_offset)).strftime("%Y-%m-%d")
            for fname in ("briefing-data-filtered.json", "briefing-data.json"):
                json_path = os.path.join(REPORTS_ROOT, dt, fname)
                if not os.path.isfile(json_path):
                    continue
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for src_block in data.get("per_source_data", []):
                        src_name = src_block.get("name", src_block.get("source", ""))
                        for item in src_block.get("items", []):
                            if item.get("title", "").strip().lower() == title_lower:
                                matched_item = item
                                matched_source_name = src_name
                                break
                        if matched_item:
                            break
                    if not matched_item:
                        for section in data.get("sections", []):
                            for item in section.get("items", []):
                                if item.get("title", "").strip().lower() == title_lower:
                                    matched_item = item
                                    matched_source_name = section.get("source", "")
                                    break
                            if matched_item:
                                break
                except Exception:
                    continue
                if matched_item:
                    break
        if not matched_item:
            try:
                kb = _load_ai_kb()
                for item in kb.get("items", []):
                    if item.get("title", "").strip().lower() == title_lower:
                        matched_item = item
                        matched_source_name = item.get("source", "")
                        break
            except Exception:
                pass
        if matched_item:
            parts = [f"Title: {matched_item.get('title', '')}"]
            if matched_source_name:
                parts.append(f"Source: {matched_source_name}")
            if matched_item.get("source") and matched_item["source"] != matched_source_name:
                parts.append(f"Publisher: {matched_item['source']}")
            if matched_item.get("date"):
                parts.append(f"Date: {matched_item['date']}")
            if matched_item.get("url"):
                parts.append(f"URL: {matched_item['url']}")
            if matched_item.get("category"):
                parts.append(f"Category: {matched_item['category']}")
            if matched_item.get("summary"):
                parts.append(f"\nSummary:\n{matched_item['summary']}")
            if matched_item.get("body"):
                parts.append(f"\nFull content:\n{matched_item['body'][:5000]}")
            if matched_item.get("commentary"):
                parts.append(f"\nExpert commentary:\n{matched_item['commentary']}")
            if matched_item.get("prediction"):
                parts.append(f"\nIndustry prediction:\n{matched_item['prediction']}")
            points = matched_item.get("points", [])
            if points and isinstance(points, list):
                parts.append("\nKey points:")
                for p in points:
                    parts.append(f"- {p}")
            if matched_item.get("_dedup_tag"):
                parts.append(f"\nContext: {matched_item['_dedup_tag']}")
            return "\n".join(parts)
    return ""


@app.route("/api/agent", methods=["POST"])
def api_agent():
    """Main agent endpoint. Accepts JSON with query, optional image, optional history."""
    from router import route_session
    from pipeline import handle_query as pipeline_handle_query, get_response_disclaimer, get_confidence_event, get_rewrite_event
    from memory.extractor import extract_immediate as _extract_immediate_memory

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Empty query"}), 400

    image_b64 = data.get("image")
    history = data.get("history", [])
    session_id = data.get("session_id", "")

    route = route_session(session_id, load_session_fn=_load_session_file)
    learning_prompt = route.learning_prompt
    is_learning = route.is_learning
    is_aws_cert = route.is_aws_cert
    rag_query_override = None
    effective_query = query
    web_refs = ""

    # --- Non-learning sessions: use the pipeline orchestrator ---
    if not is_learning:
        try:
            ctx = pipeline_handle_query(
                query=query,
                session_id=session_id,
                history=history,
                image_b64=image_b64,
                load_session_fn=_load_session_file,
            )
            effective_query = ctx.effective_query
            rag_query_override = ctx.rag_query
            disclaimer = get_response_disclaimer(ctx.intent_result)
            confidence_event = get_confidence_event(ctx.intent_result)
            rewrite_event = get_rewrite_event(ctx)

            def generate():
                if rewrite_event:
                    yield f"data: {json.dumps(rewrite_event, ensure_ascii=False)}\n\n"
                if confidence_event:
                    yield f"data: {json.dumps(confidence_event, ensure_ascii=False)}\n\n"
                _prefetch_tools = {"commit_summary", "jira_report"}
                _auto = [t for t in ctx.all_suggested_tools if t in _prefetch_tools]
                for event in run_agent(
                    effective_query,
                    image_b64=image_b64,
                    conversation_history=history,
                    system_prompt_override=ctx.system_prompt,
                    rag_query_override=rag_query_override,
                    suggested_tools=ctx.all_suggested_tools,
                    auto_prefetch=_auto,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if disclaimer:
                    yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chr(10) + disclaimer + chr(10)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                # Fire-and-forget immediate memory extraction
                import threading
                def _bg_extract():
                    try:
                        _extract_immediate_memory(query, "", session_id)
                    except Exception:
                        pass
                threading.Thread(target=_bg_extract, daemon=True).start()

            return Response(
                generate(), mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except Exception as _pipe_err:
            logger.warning("Pipeline failed, falling through to legacy path: %s", _pipe_err)
            effective_query = query
            rag_query_override = None

    if is_aws_cert:
        query_lower = query.strip().lower()
        import re as _re
        _progress_triggers = ("progress", "show progress", "how am i doing",
                              "status", "my progress", "show status")
        _quiz_pattern = _re.compile(
            r"^(?:quiz|test|exam)\s+(?:me\s+)?(?:on\s+)?(.+)$"
            r"|^practice\s+(?:questions?\s+)?(?:for\s+|on\s+|about\s+)?(.+)$",
            _re.IGNORECASE,
        )
        _teach_pattern = _re.compile(
            r"^teach\s+(?:me\s+)?(?:about\s+)?(.+)$", _re.IGNORECASE
        )
        _domain_pattern = _re.compile(
            r"domain\s*(\d)", _re.IGNORECASE
        )
        _task_pattern = _re.compile(
            r"task\s*(\d)\.(\d)", _re.IGNORECASE
        )

        if query_lower in _progress_triggers:
            progress = _load_aws_cert_progress()
            progress_text = _format_aws_cert_progress(progress)
            effective_query = (
                f"The student asked to see their study progress. "
                f"Here is their current progress data:\n\n{progress_text}\n\n"
                f"Present this progress summary to them and recommend what to study next "
                f"based on the weakest domains. Be encouraging."
            )
        elif (qm := _quiz_pattern.match(query.strip())):
            quiz_topic = (qm.group(1) or qm.group(2) or query).strip()
            rag_query_override = f"AWS AIF-C01 {quiz_topic}"
            article_content = _fetch_article_content(quiz_topic, session_id)
            _update_aws_cert_progress(quiz_topic, "quiz")
            effective_query = (
                f"QUIZ MODE: Generate 5 multiple-choice questions about \"{quiz_topic}\" "
                f"in AIF-C01 exam format (4 options A/B/C/D, one correct).\n"
            )
            if article_content:
                effective_query += f"\nReference material:\n{article_content}\n"
            effective_query += (
                f"\nPresent all 5 questions numbered Q1-Q5, then wait for the "
                f"student's answers before scoring."
            )
        elif (tm := _teach_pattern.match(query.strip())):
            teach_topic = tm.group(1).strip()
            rag_query_override = f"AWS AIF-C01 {teach_topic}"
            article_content = _fetch_article_content(teach_topic, session_id)
            _update_aws_cert_progress(teach_topic, "teach")
            effective_query = (
                f"TEACH MODE: Teach the student about \"{teach_topic}\".\n"
            )
            if article_content:
                effective_query += f"\nReference material:\n{article_content}\n"
            effective_query += (
                f"\nFollow the teaching structure: domain context → concept from zero "
                f"→ deeper with AWS services → exam tips → next steps."
            )
        else:
            dm = _domain_pattern.search(query)
            tm2 = _task_pattern.search(query)
            if dm or tm2:
                article_content = _fetch_article_content(query, session_id)
                rag_query_override = f"AWS AIF-C01 {query}"
                topic_for_progress = query.strip()
                _update_aws_cert_progress(topic_for_progress, "teach")
                if article_content:
                    effective_query = (
                        f"The student wants to learn about: \"{query}\".\n\n"
                        f"Reference material:\n{article_content}\n\n"
                        f"Teach this following the TEACH MODE structure."
                    )
            else:
                rag_query_override = f"AWS AIF-C01 {query}"
                article_content = _fetch_article_content(query, session_id)
                if article_content:
                    effective_query = (
                        f"The student asks: \"{query}\"\n\n"
                        f"Reference material:\n{article_content}\n\n"
                        f"Answer using the reference material and your knowledge. "
                        f"Always note which exam domain this relates to."
                    )
                else:
                    web_refs = _web_search_references(
                        f"AWS AIF-C01 {query} certification", 3
                    )

    elif is_learning:
        if session_id == _LEARNING_SESSION_IDS.get("english_learning"):
            eng_result = _classify_and_resolve_learning_input(query, history, session_id)
            eng_intent = eng_result["intent"]
            eng_topic = eng_result.get("resolved_topic")

            if eng_intent == "select_topic" and eng_topic:
                rag_query_override = eng_topic
                article_content = _fetch_article_content(eng_topic, session_id)
                if article_content:
                    effective_query = (
                        f"The student selected topic: \"{eng_topic}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"PRODUCE A COMPREHENSIVE TECH ENGLISH ANALYSIS (600+ words). "
                        f"You MUST include ALL seven sections from your system instructions:\n"
                        f"1. Article Summary (100-150 words)\n"
                        f"2. AI Insight — Future Impact Analysis (Economic / Life / Investment)\n"
                        f"3. Key Technical Vocabulary & Phrases (15-20 items)\n"
                        f"4. Useful Sentence Patterns (8-10 patterns)\n"
                        f"5. How a Native Speaker Would Explain This (150-200 word presentation)\n"
                        f"6. Grammar & Usage Spotlight (2-3 patterns)\n"
                        f"7. Discussion Questions (3-4 questions)\n\n"
                        f"Do NOT skip any section. Do NOT ask questions first. "
                        f"Use ALL the article content plus any RAG context to make the analysis rich and detailed. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student selected topic: \"{eng_topic}\".\n\n"
                        f"No article content was found in the briefing data, but use the RAG context below "
                        f"and your own knowledge about this topic to produce a COMPREHENSIVE TECH ENGLISH "
                        f"ANALYSIS (600+ words) with ALL seven sections from your system instructions. "
                        f"Do NOT ask questions first — start the analysis directly. "
                        f"Original input: {query}"
                    )
            elif eng_intent == "more_topics":
                topic_ctx = _fetch_fresh_topics(session_id, history)
                if topic_ctx:
                    effective_query = (
                        f"The student wants to see topics. Here are the current topics:\n\n"
                        f"{topic_ctx}\n\n"
                        f"Present these as a numbered list and ask the student to pick one. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student wants to see topics but none are available right now. "
                        f"Let them know and suggest they check back later or paste any tech text for English help."
                    )
            elif eng_intent == "followup":
                pass
            else:
                topic_list = _fetch_fresh_topics(session_id, history)
                effective_query = (
                    f"The student typed: \"{query}\".\n\n"
                    f"This doesn't match any AI news topic in our knowledge base. "
                    f"Politely guide them to pick a topic from the list below, or type a topic name "
                    f"they're interested in.\n\n"
                    f"Available topics:\n{topic_list if topic_list else '(none available)'}\n\n"
                    f"Be brief and helpful."
                )

                def generate():
                    for event in run_agent(effective_query, image_b64=image_b64,
                                           conversation_history=history,
                                           system_prompt_override=learning_prompt,
                                           rag_query_override=None):
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(generate(), mimetype="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        elif session_id == _LEARNING_SESSION_IDS.get("casual_english"):
            cas_result = _classify_and_resolve_learning_input(query, history, session_id)
            cas_intent = cas_result["intent"]
            cas_topic = cas_result.get("resolved_topic")

            if cas_intent == "select_topic" and cas_topic:
                rag_query_override = cas_topic
                article_content = _fetch_article_content(cas_topic, session_id)
                if article_content:
                    effective_query = (
                        f"The student selected topic: \"{cas_topic}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"PRODUCE A COMPREHENSIVE CASUAL ENGLISH ANALYSIS (500+ words). "
                        f"You MUST include ALL six sections from your system instructions:\n"
                        f"1. What Happened? (200-250 words) — DETAILED summary covering ALL key facts, "
                        f"specific details, numbers, and consequences. The reader must fully understand the news.\n"
                        f"2. Everyday Vocabulary & Expressions (15-20 items)\n"
                        f"3. Useful Sentence Patterns (8-10 patterns)\n"
                        f"4. How a Native Speaker Would Tell This Story (150-200 words)\n"
                        f"5. Cultural Context & Social Cues (2-3 points)\n"
                        f"6. Practice Conversations (2 dialogues)\n\n"
                        f"IMPORTANT: Section 1 must be DETAILED and cover all the facts from the article. "
                        f"Do NOT skip any section. Do NOT ask questions first. "
                        f"Use ALL the article content plus any RAG context. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student selected topic: \"{cas_topic}\".\n\n"
                        f"No article content found, but use the RAG context below "
                        f"and your own knowledge to produce a COMPREHENSIVE CASUAL ENGLISH "
                        f"ANALYSIS (500+ words) with ALL six sections from your system instructions. "
                        f"Do NOT ask questions first — start the analysis directly. "
                        f"Original input: {query}"
                    )
            elif cas_intent == "more_topics":
                topic_ctx = _fetch_fresh_topics(session_id, history)
                if topic_ctx:
                    effective_query = (
                        f"The student wants to see topics. Here are the current topics:\n\n"
                        f"{topic_ctx}\n\n"
                        f"Present these as a numbered list and ask the student to pick one. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student wants to see topics but none are available right now. "
                        f"Let them know and suggest they check back later."
                    )
            elif cas_intent == "followup":
                pass
            else:
                topic_list = _fetch_fresh_topics(session_id, history)
                effective_query = (
                    f"The student typed: \"{query}\".\n\n"
                    f"This doesn't match any world news topic in our knowledge base. "
                    f"Politely guide them to pick a topic from the list below, or type a topic name.\n\n"
                    f"Available topics:\n{topic_list if topic_list else '(none available)'}\n\n"
                    f"Be brief and helpful."
                )

                def generate():
                    for event in run_agent(effective_query, image_b64=image_b64,
                                           conversation_history=history,
                                           system_prompt_override=learning_prompt,
                                           rag_query_override=None):
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

                return Response(generate(), mimetype="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        _eng_cas_ids = (_LEARNING_SESSION_IDS.get("english_learning"), _LEARNING_SESSION_IDS.get("casual_english"))
        if session_id not in _eng_cas_ids:
            resolved = _resolve_topic_from_history(query, history)
        else:
            resolved = None
        if resolved:
            rag_query_override = resolved
            article_content = _fetch_article_content(resolved, session_id)
            if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
                web_refs = _web_search_references(f"{resolved} tutorial guide", 5)
            if article_content:
                if session_id == _LEARNING_SESSION_IDS.get("ai_learning"):
                    effective_query = (
                        f"The student selected topic: \"{resolved}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"Teach them about this topic using the article above. "
                        f"Original input: {query}"
                    )
                else:
                    effective_query = (
                        f"The student selected topic: \"{resolved}\".\n\n"
                        f"Here is the full article content:\n{article_content}\n\n"
                        f"Analyze this article NOW. Do NOT ask the student questions first. "
                        f"Start by summarizing the article, then extract and teach the key "
                        f"phrases, expressions, and vocabulary from it. Show how to discuss "
                        f"this topic naturally in English. Original input: {query}"
                    )
            else:
                effective_query = (
                    f"The student selected topic: \"{resolved}\". "
                    f"Analyze this topic and teach them using the retrieved context below. "
                    f"Do NOT ask questions first — start teaching directly. "
                    f"Original input: {query}"
                )
        elif session_id == _LEARNING_SESSION_IDS.get("ai_learning") and not _wants_more_topics(query):
            web_refs = _web_search_references(f"{query} AI machine learning tutorial", 5)
        elif _wants_more_topics(query) and session_id != _LEARNING_SESSION_IDS.get("ai_learning"):
            topic_ctx = _fetch_fresh_topics(session_id, history)
            if topic_ctx:
                effective_query = (
                    f"The student wants new topics. Here are fresh topics to present:\n\n"
                    f"{topic_ctx}\n\n"
                    f"Present these as a new numbered list and ask the student to pick one. "
                    f"Original input: {query}"
                )

    if web_refs:
        effective_query += (
            f"\n\nIMPORTANT: At the end of your answer, include these real web references "
            f"for further learning (copy them exactly as-is, do not modify the URLs):\n\n{web_refs}"
        )

    def generate():
        for event in run_agent(effective_query, image_b64=image_b64,
                               conversation_history=history,
                               system_prompt_override=learning_prompt,
                               rag_query_override=rag_query_override):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if web_refs:
            yield f"data: {json.dumps({'type': 'answer_chunk', 'content': chr(10) + chr(10) + web_refs + chr(10)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Record a user interaction event for feedback-weighted ranking."""
    try:
        rag_dir = os.path.dirname(os.path.abspath(__file__))
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)
        from feedback_store import record_event
        data = request.get_json() or {}
        record_event(
            query=data.get("query", ""),
            chunk_id=data.get("chunk_id", ""),
            action=data.get("action", ""),
            position=data.get("position", 0),
        )
        return jsonify({"recorded": True})
    except ImportError:
        return jsonify({"recorded": False, "error": "feedback_store not available"})


@app.route("/api/feedback/helpful", methods=["POST"])
def api_feedback_helpful():
    """Record explicit relevance feedback for eval dataset generation."""
    try:
        rag_dir = os.path.dirname(os.path.abspath(__file__))
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)
        from feedback_store import record_eval_candidate, record_event
        data = request.get_json() or {}
        query = data.get("query", "")
        helpful = data.get("helpful", True)
        chunk_ids = data.get("chunk_ids", [])
        if not isinstance(chunk_ids, list):
            return jsonify({"recorded": False, "error": "chunk_ids must be a list"}), 400
        for cid in chunk_ids[:5]:
            record_eval_candidate(query, str(cid), helpful)
            action = "view_doc" if helpful else "reformulate"
            record_event(query, str(cid), action, position=0)
        return jsonify({"recorded": True, "count": len(chunk_ids[:5])})
    except ImportError:
        return jsonify({"recorded": False, "error": "feedback_store not available"})
    except Exception as e:
        return jsonify({"recorded": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Memory API routes
# ---------------------------------------------------------------------------
@app.route("/api/memory", methods=["GET"])
def api_memory_list():
    """List all stored memories, optionally filtered by type."""
    from memory.store import get_all_memories
    mem_type = request.args.get("type")
    memories = get_all_memories(memory_type=mem_type)
    return jsonify({
        "count": len(memories),
        "memories": [
            {
                "id": m.id,
                "text": m.text,
                "type": m.memory_type,
                "timestamp": m.timestamp,
                "confidence": m.confidence,
            }
            for m in memories
        ],
    })


@app.route("/api/memory/<memory_id>", methods=["DELETE"])
def api_memory_delete(memory_id):
    """Delete a specific memory by ID."""
    from memory.store import delete_memory
    success = delete_memory(memory_id)
    if success:
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Memory not found"}), 404


@app.route("/api/memory/extract", methods=["POST"])
def api_memory_extract_batch():
    """Trigger batch fact extraction from a session's conversation history."""
    from memory.extractor import extract_batch
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    conversation = data.get("conversation", [])
    if not conversation:
        session_data = _load_session_file(session_id) if session_id else None
        if session_data:
            conversation = session_data.get("messages", [])
    if not conversation:
        return jsonify({"error": "No conversation data"}), 400

    entries = extract_batch(conversation, session_id=session_id)
    return jsonify({
        "extracted": len(entries),
        "facts": [{"text": e.text, "confidence": e.confidence} for e in entries],
    })


@app.route("/api/health")
def api_health():
    """Health check — verifies Ollama and Qdrant are reachable."""
    status = {"ollama": False, "qdrant": False, "model": OLLAMA_MODEL,
              "fast_model": OLLAMA_MODEL_FAST}
    try:
        import ollama
        models = ollama.list()
        available = [m.model for m in models.models] if models.models else []
        status["ollama"] = True
        status["ollama_models"] = available
        status["model_loaded"] = any(OLLAMA_MODEL in m for m in available)
    except Exception as e:
        status["ollama_error"] = str(e)

    try:
        client = _get_qdrant()
        info = client.get_collection(COLLECTION)
        status["qdrant"] = True
        status["qdrant_points"] = info.points_count or info.vectors_count
    except Exception as e:
        status["qdrant_error"] = str(e)

    return jsonify(status)


_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), ".global_settings.json")

_GLOBAL_SETTINGS_DEFAULTS = {
    "audio_lang_ai": "zh",
    "audio_lang_world": "zh",
    "audio_lang_china": "zh",
    "audio_lang_wiki": "en",
    "audio_lang_knowledge": "zh",
    "deepseek_api_key": "",
}


def _load_settings() -> dict:
    """Load settings from disk, merging with defaults."""
    settings = dict(_GLOBAL_SETTINGS_DEFAULTS)
    if os.path.isfile(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.loads(f.read())
            settings.update(saved)
        except Exception:
            pass
    return settings


def _save_settings(settings: dict):
    """Persist settings to disk."""
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(settings, indent=2, ensure_ascii=False))
    except Exception:
        pass


_GLOBAL_SETTINGS = _load_settings()


def _get_deepseek_key() -> str:
    """Return the configured DeepSeek API key (settings > env var)."""
    return (_GLOBAL_SETTINGS.get("deepseek_api_key") or "").strip() \
        or os.environ.get("DEEPSEEK_API_KEY", "")


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Get or update global settings."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        for k in _GLOBAL_SETTINGS_DEFAULTS:
            if k in data:
                _GLOBAL_SETTINGS[k] = data[k]
        _save_settings(_GLOBAL_SETTINGS)
        return jsonify({"ok": True, "settings": _settings_safe()})
    return jsonify(_settings_safe())


def _settings_safe() -> dict:
    """Return settings with API key masked for GET responses."""
    out = dict(_GLOBAL_SETTINGS)
    key = out.get("deepseek_api_key", "")
    if key and len(key) > 8:
        out["deepseek_api_key_masked"] = key[:4] + "****" + key[-4:]
    else:
        out["deepseek_api_key_masked"] = ""
    out.pop("deepseek_api_key", None)
    return out


@app.route("/api/settings/deepseek-key", methods=["POST"])
def api_settings_deepseek_key():
    """Set the DeepSeek API key (separate endpoint for security)."""
    data = request.get_json(silent=True) or {}
    key = (data.get("api_key") or "").strip()
    _GLOBAL_SETTINGS["deepseek_api_key"] = key
    _save_settings(_GLOBAL_SETTINGS)
    masked = key[:4] + "****" + key[-4:] if len(key) > 8 else ("****" if key else "")
    return jsonify({"ok": True, "masked": masked})


@app.route("/api/deepseek/test", methods=["POST"])
def api_deepseek_test():
    """Test the DeepSeek API connection with a simple chat completion."""
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip() or _get_deepseek_key()
    if not api_key:
        return jsonify({"ok": False, "error": "No API key configured"}), 400

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say hello in one sentence."},
            ],
            max_tokens=50,
            stream=False,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            timeout=30,
        )
        msg = response.choices[0].message
        return jsonify({
            "ok": True,
            "model": response.model or "unknown",
            "reply": msg.content or "",
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else {},
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/switch-model", methods=["GET", "POST"])
def api_switch_model():
    """Get or set the active Ollama model."""
    global OLLAMA_MODEL
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_model = data.get("model", "").strip()
        if new_model:
            OLLAMA_MODEL = new_model
            return jsonify({"model": OLLAMA_MODEL, "changed": True})
        return jsonify({"error": "No model specified"}), 400
    return jsonify({"model": OLLAMA_MODEL})


# ---------------------------------------------------------------------------
# Chat session persistence (JSON files under REPORTS_ROOT/.chat-sessions)
# ---------------------------------------------------------------------------

def _ensure_chat_sessions_dir() -> None:
    os.makedirs(CHAT_SESSIONS_DIR, exist_ok=True)


def _parse_session_id(session_id: str) -> str | None:
    try:
        return str(uuid.UUID(session_id))
    except (ValueError, TypeError):
        return None


def _session_file_path(session_id: str) -> str:
    return os.path.join(CHAT_SESSIONS_DIR, f"{session_id}.json")


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _load_session_file(session_id: str) -> dict | None:
    path = _session_file_path(session_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save_session_file(data: dict) -> bool:
    sid = data.get("id")
    if not sid:
        return False
    _ensure_chat_sessions_dir()
    path = _session_file_path(sid)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


@app.route("/api/sessions", methods=["GET"])
def api_sessions_list():
    """List recent chat sessions (metadata only), newest first, max 50."""
    _ensure_chat_sessions_dir()
    items = []
    try:
        for name in os.listdir(CHAT_SESSIONS_DIR):
            if not name.endswith(".json"):
                continue
            sid = name[:-5]
            if _parse_session_id(sid) is None:
                continue
            path = os.path.join(CHAT_SESSIONS_DIR, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            messages = data.get("messages")
            if not isinstance(messages, list):
                messages = []
            items.append({
                "id": data.get("id", sid),
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(messages),
            })
    except OSError as e:
        return jsonify({"error": str(e)}), 500

    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    items = items[:50]
    return jsonify({"sessions": items})


@app.route("/api/sessions", methods=["POST"])
def api_sessions_create():
    """Create a new empty chat session."""
    _ensure_chat_sessions_dir()
    sid = str(uuid.uuid4())
    now = _now_iso()
    data = {
        "id": sid,
        "title": "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    if not _save_session_file(data):
        return jsonify({"error": "Failed to create session file"}), 500
    return jsonify(data)


@app.route("/api/sessions/<session_id>", methods=["GET"])
def api_sessions_get(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(data)


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_sessions_delete(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    path = _session_file_path(sid)
    if not os.path.isfile(path):
        return jsonify({"error": "Session not found"}), 404
    try:
        os.remove(path)
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "id": sid})


@app.route("/api/sessions/<session_id>/messages", methods=["POST"])
def api_sessions_append_messages(session_id):
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    body = request.get_json(silent=True) or {}
    user_msg = (body.get("user_message") or "").strip()
    assistant_msg = body.get("assistant_message")
    if assistant_msg is None:
        assistant_msg = ""
    else:
        assistant_msg = str(assistant_msg)
    if not user_msg and not assistant_msg:
        return jsonify({"error": "user_message or assistant_message is required"}), 400

    now = _now_iso()
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []

    user_count_before = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
    if user_count_before == 0 and user_msg:
        data["title"] = user_msg[:60]

    if user_msg:
        messages.append({"role": "user", "content": user_msg, "timestamp": now})
    if assistant_msg:
        messages.append({"role": "assistant", "content": assistant_msg, "timestamp": now})
    data["messages"] = messages
    data["updated_at"] = now

    if not _save_session_file(data):
        return jsonify({"error": "Failed to save session"}), 500
    return jsonify({
        "ok": True,
        "id": sid,
        "title": data["title"],
        "updated_at": data["updated_at"],
        "message_count": len(messages),
    })


@app.route("/api/sessions/<session_id>/clear", methods=["POST"])
def api_sessions_clear(session_id):
    """Clear all messages from a session, keeping the session itself."""
    sid = _parse_session_id(session_id)
    if not sid:
        return jsonify({"error": "Invalid session id"}), 400
    data = _load_session_file(sid)
    if not data:
        return jsonify({"error": "Session not found"}), 404
    data["messages"] = []
    data["updated_at"] = _now_iso()
    if not _save_session_file(data):
        return jsonify({"error": "Failed to save session"}), 500
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Learning Notes API
# ---------------------------------------------------------------------------

def _load_notes() -> list[dict]:
    if os.path.isfile(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return []


def _save_notes(notes: list[dict]) -> bool:
    try:
        os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


@app.route("/api/notes", methods=["GET"])
def api_notes_list():
    notes = _load_notes()
    tag = request.args.get("tag")
    if tag:
        notes = [n for n in notes if tag.lower() in [str(t).lower() for t in n.get("tags", []) if t]]
    notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return jsonify(notes)


@app.route("/api/notes", methods=["POST"])
def api_notes_create():
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    note = {
        "id": str(uuid.uuid4()),
        "content": content,
        "title": body.get("title", content[:80]).strip(),
        "tags": body.get("tags", []),
        "session_id": body.get("session_id", ""),
        "session_type": body.get("session_type", ""),
        "created_at": _now_iso(),
    }
    notes = _load_notes()
    notes.append(note)
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify(note), 201


@app.route("/api/notes/<note_id>", methods=["PUT"])
def api_notes_update(note_id):
    body = request.get_json(silent=True) or {}
    new_content = (body.get("content") or "").strip()
    if not new_content:
        return jsonify({"error": "content is required"}), 400
    notes = _load_notes()
    found = None
    for n in notes:
        if n.get("id") == note_id:
            found = n
            break
    if not found:
        return jsonify({"error": "Note not found"}), 404
    found["content"] = new_content
    found["title"] = new_content[:80].split("\n")[0]
    found["updated_at"] = _now_iso()
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify({"ok": True, "note": found})


@app.route("/api/notes/<note_id>", methods=["DELETE"])
def api_notes_delete(note_id):
    notes = _load_notes()
    before = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    if len(notes) == before:
        return jsonify({"error": "Note not found"}), 404
    if not _save_notes(notes):
        return jsonify({"error": "Failed to save"}), 500
    return jsonify({"ok": True})

from routes.toolbar import toolbar_bp
app.register_blueprint(toolbar_bp)


from routes.ai_news import (
    ai_news_bp,
    _load_ai_kb,
)
app.register_blueprint(ai_news_bp)


# ---------------------------------------------------------------------------
# Daily Fetch + Learning sessions (Blueprint)
# ---------------------------------------------------------------------------
from routes.daily_fetch import (
    daily_fetch_bp,
    _load_recent_ai_news_titles,
    _load_recent_world_news_titles,
    _load_ai_learning_roadmap,
    _load_aws_cert_roadmap,
    _load_aws_cert_progress,
    _format_aws_cert_progress,
    _update_aws_cert_progress,
)
app.register_blueprint(daily_fetch_bp)


# Stock routes (Blueprint)
from routes.stock import stock_bp
app.register_blueprint(stock_bp)


# ===================================================================
# WEB UI
# ===================================================================

# Web UI template loaded from external file
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
with open(os.path.join(_TEMPLATE_DIR, "index.html"), "r", encoding="utf-8") as _f:
    AGENT_HTML = _f.read()


@app.route("/")
def index():
    resp = make_response(render_template_string(AGENT_HTML))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ===================================================================
# MAIN
# ===================================================================

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18889
    print(f"Starting Jarvis on http://127.0.0.1:{port}", flush=True)
    print(f"Model: {OLLAMA_MODEL} via {OLLAMA_HOST}", flush=True)
    print("Preloading embedding model and Qdrant data...", flush=True)
    _get_embed_model()
    _get_qdrant()
    print("Ready! Open your browser.", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
