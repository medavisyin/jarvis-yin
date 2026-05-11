"""
Jarvis Telegram Bot — remote command interface.

Lets you send commands to Jarvis from your phone via Telegram.
Only responds to the configured owner (TELEGRAM_OWNER_ID).

Requires:
  pip install python-telegram-bot httpx[socks]

Config is loaded from bot_telegram.env next to this file.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime

import httpx
from telegram import InputFile, Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s [TelegramBot] %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_telegram.env")


def _load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not os.path.isfile(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_env = _load_env(_ENV_FILE)

BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", _env.get("TELEGRAM_BOT_TOKEN", ""))
OWNER_ID: int = int(os.environ.get("TELEGRAM_OWNER_ID", _env.get("TELEGRAM_OWNER_ID", "0")))
SOCKS_PROXY: str = os.environ.get("SOCKS_PROXY", _env.get("SOCKS_PROXY", ""))
AGENT_URL: str = os.environ.get("AGENT_URL", _env.get("AGENT_URL", "http://127.0.0.1:18889"))
SEARCH_URL: str = os.environ.get("SEARCH_URL", _env.get("SEARCH_URL", "http://127.0.0.1:18888"))
REPORTS_ROOT: str = os.environ.get("JARVIS_REPORTS_ROOT", "C:/reports/ai")

AUDIO_FILES = [
    ("ai-briefing.mp3", "AI Briefing"),
    ("world-news.mp3", "World News"),
    ("china-news.mp3", "China News"),
]

if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is required. Set it in bot_telegram.env or as an env var.")
if not OWNER_ID:
    raise SystemExit("TELEGRAM_OWNER_ID is required.")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=620, write=30, pool=10))
    return _http


async def _agent_get(path: str, **params) -> dict:
    r = await _get_http().get(f"{AGENT_URL}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def _agent_post(path: str, payload: dict | None = None) -> dict:
    r = await _get_http().post(f"{AGENT_URL}{path}", json=payload)
    r.raise_for_status()
    return r.json()


async def _search_get(path: str, **params) -> dict:
    r = await _get_http().get(f"{SEARCH_URL}{path}", params=params)
    r.raise_for_status()
    return r.json()


async def _search_post(path: str, payload: dict | None = None) -> dict:
    r = await _get_http().post(f"{SEARCH_URL}{path}", json=payload)
    r.raise_for_status()
    return r.json()


async def _poll_job(base_url: str, path: str, job_id: str,
                    update: Update, timeout: int = 900) -> dict:
    url = f"{base_url}{path}/{job_id}"
    start = time.time()
    last_step = ""
    while time.time() - start < timeout:
        await asyncio.sleep(5)
        try:
            r = await _get_http().get(url)
            data = r.json()
        except Exception:
            continue
        status = data.get("status", "")
        step = data.get("step", "")
        if step and step != last_step:
            last_step = step
            await update.message.reply_text(f"... {step}")
        if status in ("done", "error", "completed"):
            return data
    return {"status": "timeout", "result": f"Job timed out ({timeout}s)"}


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 20] + "\n\n... (truncated)"


async def _send_long_text(update: Update, text: str, limit: int = 4000) -> None:
    """Split long text into multiple Telegram messages respecting the 4096 char limit.

    Splits at paragraph boundaries (double newline), falling back to single newlines,
    then hard-cuts if no suitable boundary is found.
    """
    if len(text) <= limit:
        await update.message.reply_text(text)
        return

    remaining = text
    while remaining:
        if len(remaining) <= limit:
            await update.message.reply_text(remaining)
            break

        # Try splitting at paragraph boundary
        chunk = remaining[:limit]
        split_idx = chunk.rfind("\n\n")
        if split_idx < limit // 4:
            # Paragraph boundary too early — try single newline
            split_idx = chunk.rfind("\n")
        if split_idx < limit // 4:
            # No good boundary — hard cut
            split_idx = limit

        await update.message.reply_text(remaining[:split_idx].rstrip())
        remaining = remaining[split_idx:].lstrip("\n")
        await asyncio.sleep(0.3)  # avoid flood limit


# ---------------------------------------------------------------------------
# Audio delivery helpers
# ---------------------------------------------------------------------------

async def _send_audio_files(update: Update, target_date: str = "") -> int:
    """Send today's (or specified date's) audio files to the Telegram chat.

    Returns the number of files successfully sent.
    """
    if not target_date:
        target_date = datetime.now().strftime("%Y-%m-%d")

    date_dir = os.path.join(REPORTS_ROOT, target_date)
    if not os.path.isdir(date_dir):
        await update.message.reply_text(f"No reports found for {target_date}")
        return 0

    sent = 0
    for filename, label in AUDIO_FILES:
        fpath = os.path.join(date_dir, filename)
        if not os.path.isfile(fpath):
            continue
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        if size_mb > 50:
            await update.message.reply_text(f"{label}: file too large ({size_mb:.1f}MB, Telegram limit 50MB)")
            continue
        try:
            with open(fpath, "rb") as f:
                await update.message.reply_audio(
                    audio=InputFile(f, filename=filename),
                    title=f"{label} ({target_date})",
                    performer="Jarvis",
                )
            sent += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            log.error("Failed to send %s: %s", filename, e)
            await update.message.reply_text(f"Failed to send {label}: {e}")
    return sent


# ---------------------------------------------------------------------------
# Formatters — turn API JSON into readable Telegram text
# ---------------------------------------------------------------------------

def _fmt_stock_candidate(c: dict, rank: int) -> str:
    name = c.get("name", "?")
    symbol = c.get("symbol", "?")
    price = c.get("price", 0)
    change = c.get("change_pct", 0)
    score = c.get("final_score") or c.get("score_l1", 0)
    pe = c.get("pe", "-")
    cap = c.get("market_cap", 0)

    direction = "+" if change >= 0 else ""
    cap_str = f"{cap/10000:.1f}B" if cap > 10000 else f"{cap:.0f}M"

    lines = [f"{rank}. {name} ({symbol})"]
    lines.append(f"   Price: {price}  {direction}{change:.1f}%  Score: {score}")
    lines.append(f"   PE: {pe}  Cap: {cap_str}")

    signals = c.get("signals", {})
    if signals:
        sig_parts = [f"{k}:{v}" for k, v in signals.items()]
        lines.append(f"   Signals: {', '.join(sig_parts)}")

    reasoning = c.get("reasoning", "")
    if reasoning:
        lines.append(f"   {reasoning[:120]}")

    buy_low = c.get("buy_low")
    buy_high = c.get("buy_high")
    if buy_low and buy_high:
        lines.append(f"   Buy range: {buy_low} - {buy_high}")

    risk = c.get("risk", "")
    if risk:
        lines.append(f"   Risk: {risk[:100]}")

    return "\n".join(lines)


def _fmt_scan_result(data: dict) -> str:
    top_picks = data.get("top_picks", [])
    meta = data.get("meta", {})

    header = (
        f"AI Stock Scan Complete\n"
        f"Market: {meta.get('market_total', '?')} stocks\n"
        f"L1 Filter: {meta.get('layer1_count', '?')} → L2 Analysis: {meta.get('layer2_count', '?')}\n"
    )

    if not top_picks:
        return (
            header +
            "\nResult: No stocks passed the buyability check today.\n"
            "This is normal — \"no recommendation\" beats a bad one."
        )

    lines = [header, f"Recommended: {len(top_picks)} stock(s)\n"]
    for i, p in enumerate(top_picks, 1):
        lines.append(
            f"{i}. {p.get('name', '?')} ({p.get('symbol', '?')})\n"
            f"   Price: ¥{p.get('price', '?')}  PE: {p.get('pe', '?')}\n"
            f"   Score: {p.get('final_score', '?')}/100  Fund: {p.get('fund_score', '?')}/100\n"
            f"   Reason: {p.get('reasoning', 'N/A')}\n"
            f"   Risk: {p.get('risk', 'N/A')}\n"
            f"   Buy range: {p.get('buy_low', '?')} ~ {p.get('buy_high', '?')}"
        )
    return "\n".join(lines)


def _fmt_stock_analyze(data: dict, symbol: str) -> str:
    if "error" in data:
        return f"{symbol}: {data['error']}"

    lines = [f"Stock Analysis: {symbol}\n"]

    for key, label in [
        ("technical_report", "Technical"),
        ("fundamental_report", "Fundamental"),
        ("sentiment_report", "Sentiment"),
        ("xgb_report", "XGBoost"),
        ("prediction_report", "Prediction"),
    ]:
        report = data.get(key, "")
        if report:
            text = str(report).strip()
            if len(text) > 600:
                text = text[:600] + "..."
            lines.append(f"--- {label} ---")
            lines.append(text)
            lines.append("")

    if len(lines) == 1:
        lines.append("(No report data returned)")

    return "\n".join(lines)


def _fmt_train_status(data: dict) -> str:
    lines = ["Training complete.\n"]
    progress = data.get("progress", {})
    if isinstance(progress, dict):
        done = progress.get("completed", 0)
        total = progress.get("total", 0)
        lines.append(f"Symbols: {done}/{total}")
        results = progress.get("results", {})
        if isinstance(results, dict):
            for sym, info in list(results.items())[:10]:
                if isinstance(info, dict):
                    acc = info.get("accuracy", info.get("score", ""))
                    lines.append(f"  {sym}: {acc}")
                else:
                    lines.append(f"  {sym}: {info}")
    elif isinstance(progress, str):
        lines.append(progress[:500])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("Unauthorized.")
            log.warning("Rejected user %s (%s)", update.effective_user.id, update.effective_user.full_name)
            return
        return await func(update, context)
    return wrapper


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

HELP_TEXT = """Jarvis Bot Commands:

/status  — Server health check
/fetch   — Run daily pipeline (5-30 min, sends audio when done)
/fetch_step <name> — Run one step
  (fetch_sources, ai_audio, commit_report, jira_daily, wiki_fetch, world_audio, china_audio)
/audio [date] — Send today's audio (or /audio 2026-05-10)
/search <query> — RAG search
/ask <question> — Ask Jarvis (LLM)
/index — Index new briefings
/knowledge — Refresh knowledge docs
/stock <code> — Stock analysis
/train — Train stock models
/scan — Run short-term stock scanner
/longscan — Run long-term stock scanner
/english — Tech English (AI news topics)
/english <topic> — Analyze a topic
/casual — Casual English (world news topics)
/casual <topic> — Analyze a topic
/stop — Exit learning session

After /english or /casual, just type normally:
  "15" → pick topic 15
  "more topics" → refresh list
  "tell me more" → follow up"""


@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Jarvis online.\n\n{HELP_TEXT}")


@owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = []
    try:
        data = await _agent_get("/api/health")
        ollama = data.get("ollama", "unknown")
        qdrant = data.get("qdrant", "unknown")
        lines.append(f"Agent (18889): running")
        lines.append(f"Ollama: {ollama}")
        lines.append(f"Qdrant: {qdrant}")
    except Exception as e:
        lines.append(f"Agent (18889): unreachable")

    try:
        await _search_get("/api/chunk-analysis")
        lines.append("Search UI (18888): running")
    except Exception:
        lines.append("Search UI (18888): unreachable")

    await update.message.reply_text("\n".join(lines))


@owner_only
async def cmd_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Starting daily fetch... (5-30 min)")
    try:
        resp = await _agent_post("/api/toolbar/daily-fetch")
        job_id = resp.get("job_id")
        if not job_id:
            await update.message.reply_text("Failed to start fetch job.")
            return
        result = await _poll_job(AGENT_URL, "/api/toolbar/daily-fetch", job_id, update, timeout=2400)
        status = result.get("status", "unknown")
        msg = result.get("result", result.get("summary", ""))
        text = f"Daily fetch: {status}"
        if msg:
            text += f"\n\n{msg[:3000]}"
        await update.message.reply_text(_truncate(text))

        if status == "done":
            sent = await _send_audio_files(update)
            if sent:
                await update.message.reply_text(f"Sent {sent} audio file(s)")
    except Exception as e:
        await update.message.reply_text(f"Fetch error: {e}")


@owner_only
async def cmd_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send audio files for today or a specified date. Usage: /audio [YYYY-MM-DD]"""
    target_date = context.args[0] if context.args else ""
    sent = await _send_audio_files(update, target_date)
    if not sent:
        await update.message.reply_text(
            f"No audio files found for {target_date or 'today'}.\n"
            "Run /fetch or /fetch_step ai_audio first."
        )


@owner_only
async def cmd_fetch_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /fetch_step <name>\n\n"
            "Steps: fetch_sources, topic_dedup, commit_report, "
            "jira_daily, wiki_fetch, ai_audio, world_audio, china_audio"
        )
        return
    step = context.args[0]
    await update.message.reply_text(f"Running: {step}")
    try:
        resp = await _agent_post("/api/toolbar/daily-fetch/continue", {"only_steps": [step]})
        job_id = resp.get("job_id")
        if not job_id:
            await update.message.reply_text("Failed to start step.")
            return
        result = await _poll_job(AGENT_URL, "/api/toolbar/daily-fetch", job_id, update, timeout=900)
        status = result.get("status", "unknown")
        msg = result.get("result", "")
        text = f"{step}: {status}"
        if msg:
            text += f"\n{msg[:2000]}"
        await update.message.reply_text(_truncate(text))

        if status == "done" and step in ("ai_audio", "world_audio", "china_audio"):
            await _send_audio_files(update)
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


@owner_only
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    try:
        data = await _search_get("/api/search", query=query, top_k=5)
        results = data.get("results", [])
        if not results:
            await update.message.reply_text(f"No results for: {query}")
            return
        lines = [f'Search: "{query}"\n']
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", r.get("parent_title", "untitled"))
            score = r.get("score", 0)
            snippet = r.get("text", "")[:150].replace("\n", " ")
            lines.append(f"{i}. {title} (score: {score:.2f})")
            lines.append(f"   {snippet}\n")
        await update.message.reply_text(_truncate("\n".join(lines)))
    except Exception as e:
        await update.message.reply_text(f"Search error: {e}")


@owner_only
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /ask <question>")
        return
    await update.message.reply_text("Thinking...")
    try:
        r = await _get_http().post(
            f"{AGENT_URL}/api/agent",
            json={"query": question, "session_id": "telegram", "history": []},
            timeout=httpx.Timeout(connect=10, read=300, write=30, pool=10),
        )
        if r.status_code != 200:
            await update.message.reply_text(f"Agent returned {r.status_code}")
            return

        answer_parts = []
        for line in r.text.splitlines():
            if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                continue
            try:
                event = json.loads(line[6:])
                etype = event.get("type", "")
                content = event.get("content", event.get("token", ""))
                if etype in ("answer_chunk", "token") and content:
                    answer_parts.append(content)
            except json.JSONDecodeError:
                pass

        answer = "".join(answer_parts).strip()
        if not answer:
            answer = "(Jarvis had no answer for this question)"
        await update.message.reply_text(_truncate(answer))
    except httpx.ReadTimeout:
        await update.message.reply_text("Timed out waiting for Jarvis. Try a simpler question.")
    except Exception as e:
        await update.message.reply_text(f"Ask error: {e}")


@owner_only
async def cmd_index(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Indexing new briefings...")
    try:
        resp = await _search_post("/api/index-new")
        job_id = resp.get("job_id")
        if not job_id:
            await update.message.reply_text("Failed to start indexing.")
            return
        result = await _poll_job(SEARCH_URL, "/api/index-new", job_id, update, timeout=300)
        msg = result.get("result", "")
        items = result.get("new_items", [])
        text = f"Indexing: {result.get('status', 'done')}"
        if msg:
            text += f"\n{msg}"
        if items:
            new_count = sum(1 for it in items if it.get("new"))
            text += f"\n{len(items)} files processed, {new_count} new"
        await update.message.reply_text(_truncate(text))
    except Exception as e:
        await update.message.reply_text(f"Index error: {e}")


@owner_only
async def cmd_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Refreshing knowledge docs...")
    try:
        resp = await _search_post("/api/refresh-knowledge")
        job_id = resp.get("job_id")
        if not job_id:
            await update.message.reply_text("Failed to start refresh.")
            return
        result = await _poll_job(SEARCH_URL, "/api/refresh-knowledge", job_id, update, timeout=600)
        msg = result.get("result", "")
        text = f"Knowledge: {result.get('status', 'done')}"
        if msg:
            text += f"\n{msg}"
        await update.message.reply_text(_truncate(text))
    except Exception as e:
        await update.message.reply_text(f"Knowledge error: {e}")


@owner_only
async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = context.args[0] if context.args else ""
    if not symbol:
        await update.message.reply_text("Usage: /stock <code>\nExample: /stock 002124")
        return
    await update.message.reply_text(f"Analyzing {symbol}... (takes 3-5 min for full analysis)")
    try:
        r = await _get_http().post(
            f"{AGENT_URL}/api/stock/analyze",
            json={"symbol": symbol, "mode": "full"},
            timeout=httpx.Timeout(connect=10, read=600, write=30, pool=10),
        )
        data = r.json()
        text = _fmt_stock_analyze(data, symbol)
        await update.message.reply_text(_truncate(text))
    except httpx.ReadTimeout:
        await update.message.reply_text(f"{symbol}: analysis timed out after 10 min. Try /stock {symbol} again.")
    except Exception as e:
        await update.message.reply_text(f"Stock error: {e}")


@owner_only
async def cmd_train(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Starting model training...")
    try:
        resp = await _agent_post("/api/stock/train/daily")
        await update.message.reply_text(f"Training started: {resp.get('message', 'ok')}")
        last_msg = ""
        for _ in range(60):
            await asyncio.sleep(10)
            try:
                st = await _agent_get("/api/stock/train/status")
                running = st.get("running", False)
                if not running:
                    await update.message.reply_text(_truncate(_fmt_train_status(st)))
                    return
                progress = st.get("progress", {})
                if isinstance(progress, dict):
                    done = progress.get("completed", 0)
                    total = progress.get("total", 0)
                    msg = f"Training... {done}/{total}"
                    if msg != last_msg:
                        last_msg = msg
                        await update.message.reply_text(msg)
            except Exception:
                continue
        await update.message.reply_text("Training still running (stopped polling after 10 min).")
    except Exception as e:
        await update.message.reply_text(f"Train error: {e}")


@owner_only
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Starting scanner...")
    try:
        resp = await _agent_post("/api/stock/scan/start")
        msg = resp.get("message", "started")
        await update.message.reply_text(f"Scanner: {msg}")

        for _ in range(60):
            await asyncio.sleep(10)
            try:
                st = await _agent_get("/api/stock/scan/status")
                status = st.get("status", "")
                if status in ("idle", "completed", "done"):
                    result = await _agent_get("/api/stock/scan/result")
                    text = _fmt_scan_result(result)
                    await update.message.reply_text(_truncate(text))
                    return
            except Exception:
                continue
        await update.message.reply_text("Scan still running (stopped polling after 10 min).")
    except Exception as e:
        await update.message.reply_text(f"Scan error: {e}")


def _fmt_lt_scan_result(data: dict) -> str:
    picks = data.get("picks", [])
    themes = data.get("themes", [])
    metals = data.get("precious_metals", {})
    header = "🔮 AI Long-Term Scan Complete\n"
    lines = [header]
    for key, label in [("gold", "Gold"), ("silver", "Silver")]:
        m = metals.get(key)
        if m and m.get("data_available"):
            lines.append(
                f"{'🥇' if key == 'gold' else '🥈'} {label}: ¥{m.get('latest_price', '?')}"
                f"  Trend: {m.get('trend', '?')}  Upside: {m.get('upside_score', '?')}/100"
                f"  14d: {m.get('change_14d_pct', 0):+.1f}%"
            )
    outlook = metals.get("llm_outlook", {})
    for key, label in [("gold", "Gold"), ("silver", "Silver")]:
        o = outlook.get(key)
        if o:
            lines.append(f"  {label} outlook: {o.get('trend', '?')} — {o.get('advice', '')}")
    if themes:
        lines.append(f"\nThemes: {len(themes)}")
        for i, t in enumerate(themes[:5], 1):
            lines.append(f"  {i}. {t.get('name', '?')} ({t.get('confidence', '?')})")
    if not picks:
        lines.append("\nNo stock picks this round (check metals & themes above).")
    else:
        lines.append(f"\nRecommended: {len(picks)} stock(s)\n")
        for i, p in enumerate(picks, 1):
            us = (p.get("upside") or {}).get("upside_score", "?")
            lines.append(
                f"{i}. {p.get('name', '?')} ({p.get('symbol', '?')})\n"
                f"   Theme: {p.get('theme', '?')}  Upside: {us}/100\n"
                f"   Reason: {p.get('recommendation_reason', 'N/A')}\n"
                f"   Risk: {p.get('recommendation_risk', 'N/A')}"
            )
    return "\n".join(lines)


@owner_only
async def cmd_longscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Starting long-term scanner...")
    try:
        resp = await _agent_post("/api/stock/long-term/start")
        msg = resp.get("message", "started")
        await update.message.reply_text(f"Long-term scanner: {msg}")
        for _ in range(60):
            await asyncio.sleep(10)
            try:
                st = await _agent_get("/api/stock/long-term/status")
                status = st.get("status", "")
                if status in ("idle", "done"):
                    result = await _agent_get("/api/stock/long-term/result")
                    text = _fmt_lt_scan_result(result)
                    await update.message.reply_text(_truncate(text))
                    return
                if status == "error":
                    await update.message.reply_text(f"Long-term scan error: {st.get('error', 'unknown')}")
                    return
            except Exception:
                continue
        await update.message.reply_text("Long-term scan still running (stopped polling after 10 min).")
    except Exception as e:
        await update.message.reply_text(f"Long-term scan error: {e}")


# ---------------------------------------------------------------------------
# English Learning — shared helpers and per-session history
# ---------------------------------------------------------------------------

_ENGLISH_SESSION_ID = "00000000-0000-0000-0000-000000000002"
_CASUAL_SESSION_ID = "00000000-0000-0000-0000-000000000003"

_learning_history: dict[str, list[dict]] = {
    "english": [],
    "casual": [],
}
_MAX_HISTORY = 10

# Active learning session — plain text messages route here
_active_learning_mode: str | None = None  # "english" or "casual" or None


def _push_history(mode: str, role: str, content: str) -> None:
    hist = _learning_history[mode]
    hist.append({"role": role, "content": content})
    if len(hist) > _MAX_HISTORY:
        _learning_history[mode] = hist[-_MAX_HISTORY:]


async def _stream_agent_response(session_id: str, query: str, history: list[dict]) -> str | None:
    """Call /api/agent with SSE and collect the full streamed answer.

    Returns the answer text on success, or None on HTTP/transport errors.
    """
    r = await _get_http().post(
        f"{AGENT_URL}/api/agent",
        json={"query": query, "session_id": session_id, "history": history},
        timeout=httpx.Timeout(connect=10, read=300, write=30, pool=10),
    )
    if r.status_code != 200:
        log.warning("Agent returned HTTP %d for session %s", r.status_code, session_id)
        return None

    parts = []
    for line in r.text.splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        try:
            event = json.loads(line[6:])
            etype = event.get("type", "")
            content = event.get("content", event.get("token", ""))
            if etype in ("answer_chunk", "token") and content:
                parts.append(content)
        except json.JSONDecodeError:
            pass
    return "".join(parts).strip() or None


async def _fetch_topics(mode: str) -> str:
    """Fetch available topics from the learning-context API."""
    ltype = "english_learning" if mode == "english" else "casual_english"
    try:
        data = await _agent_get("/api/toolbar/learning-context", type=ltype)
    except Exception as e:
        log.warning("Failed to fetch %s topics: %s", ltype, e)
        return "(Could not load topics — API unreachable. Try again later.)"

    if mode == "english":
        titles = data.get("news_titles", [])
        if not titles:
            return "(No tech topics available today)"
        lines = ["Today's Tech English topics — pick a topic:\n"]
        for i, t in enumerate(titles[:15], 1):
            lines.append(f"{i}. {t}")
        lines.append("\nJust type a number, title, or \"more topics\"")
        return "\n".join(lines)
    else:
        items = data.get("news_items", [])
        if not items:
            return "(No world news topics available today)"
        lines = ["Today's Casual English topics — pick a topic:\n"]
        for i, item in enumerate(items[:15], 1):
            title = item.get("title", "?")
            lines.append(f"{i}. {title}")
        lines.append("\nJust type a number, title, or \"more topics\"")
        return "\n".join(lines)


@owner_only
async def cmd_english(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tech English learning — select a topic from today's AI news."""
    global _active_learning_mode
    _active_learning_mode = "english"
    query = " ".join(context.args) if context.args else ""
    if not query:
        topics = await _fetch_topics("english")
        await _send_long_text(update, topics)
        _push_history("english", "user", "show me topics")
        _push_history("english", "assistant", topics)
        return

    await update.message.reply_text("Generating Tech English analysis... (30-60s)")
    history = list(_learning_history["english"])
    try:
        answer = await _stream_agent_response(_ENGLISH_SESSION_ID, query, history)
        if answer is None:
            await update.message.reply_text("Agent unavailable. Try again later.")
            return
        _push_history("english", "user", query)
        _push_history("english", "assistant", answer[:1500])
        await _send_long_text(update, answer)
    except httpx.ReadTimeout:
        await update.message.reply_text("Timed out. Try again or pick a different topic.")
    except Exception as e:
        await update.message.reply_text(f"English error: {e}")


@owner_only
async def cmd_casual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Casual English learning — select a topic from today's world news."""
    global _active_learning_mode
    _active_learning_mode = "casual"
    query = " ".join(context.args) if context.args else ""
    if not query:
        topics = await _fetch_topics("casual")
        await _send_long_text(update, topics)
        _push_history("casual", "user", "show me topics")
        _push_history("casual", "assistant", topics)
        return

    await update.message.reply_text("Generating Casual English analysis... (30-60s)")
    history = list(_learning_history["casual"])
    try:
        answer = await _stream_agent_response(_CASUAL_SESSION_ID, query, history)
        if answer is None:
            await update.message.reply_text("Agent unavailable. Try again later.")
            return
        _push_history("casual", "user", query)
        _push_history("casual", "assistant", answer[:1500])
        await _send_long_text(update, answer)
    except httpx.ReadTimeout:
        await update.message.reply_text("Timed out. Try again or pick a different topic.")
    except Exception as e:
        await update.message.reply_text(f"Casual English error: {e}")


@owner_only
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit active learning session mode."""
    global _active_learning_mode
    if _active_learning_mode:
        await update.message.reply_text(f"Exited {_active_learning_mode} session.")
        _active_learning_mode = None
    else:
        await update.message.reply_text("No active session.")


@owner_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /help for list.")


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route plain text to active learning session (conversational mode)."""
    if update.effective_user.id != OWNER_ID:
        return
    if not _active_learning_mode:
        return

    mode = _active_learning_mode
    session_id = _ENGLISH_SESSION_ID if mode == "english" else _CASUAL_SESSION_ID
    query = (update.message.text or "").strip()
    if not query:
        return

    await update.message.reply_text("Thinking...")
    history = list(_learning_history[mode])
    try:
        answer = await _stream_agent_response(session_id, query, history)
        if answer is None:
            await update.message.reply_text("Agent unavailable. Try again later.")
            return
        _push_history(mode, "user", query)
        _push_history(mode, "assistant", answer[:1500])
        await _send_long_text(update, answer)
    except httpx.ReadTimeout:
        await update.message.reply_text("Timed out. Try again.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run_bot():
    """Build, register handlers, and run the bot with manual polling loop."""
    from telegram.request import HTTPXRequest

    req_kwargs = {"connection_pool_size": 8, "connect_timeout": 30.0,
                  "read_timeout": 30.0, "write_timeout": 30.0, "pool_timeout": 10.0}
    if SOCKS_PROXY:
        req_kwargs["proxy"] = SOCKS_PROXY

    request = HTTPXRequest(**req_kwargs)
    get_updates_request = HTTPXRequest(**req_kwargs)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("fetch", cmd_fetch))
    app.add_handler(CommandHandler("audio", cmd_audio))
    app.add_handler(CommandHandler("fetch_step", cmd_fetch_step))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("index", cmd_index))
    app.add_handler(CommandHandler("knowledge", cmd_knowledge))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("train", cmd_train))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("longscan", cmd_longscan))
    app.add_handler(CommandHandler("english", cmd_english))
    app.add_handler(CommandHandler("casual", cmd_casual))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        if isinstance(context.error, Conflict):
            return
        log.error("Unhandled exception: %s", context.error, exc_info=context.error)

    app.add_error_handler(_error_handler)

    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    log.info("Application started, waiting for stale sessions to expire...")
    await asyncio.sleep(5)

    offset = None
    backoff = 2
    max_backoff = 30
    conflict_count = 0
    while True:
        try:
            updates = await app.bot.get_updates(
                offset=offset, timeout=10, allowed_updates=Update.ALL_TYPES
            )
            if conflict_count > 0:
                log.info("Polling recovered after %d conflicts", conflict_count)
                conflict_count = 0
            backoff = 2
            if updates:
                offset = updates[-1].update_id + 1
                for u in updates:
                    await app.process_update(u)
        except Conflict:
            conflict_count += 1
            if conflict_count <= 3:
                log.info("409 conflict #%d, backing off %ds...", conflict_count, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        except Exception as e:
            log.error("Polling error: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


PID_FILE = os.path.join(os.path.dirname(__file__), "bot_telegram.pid")


def _kill_stale_instances():
    """Kill any previous bot_telegram.py processes and remove stale PID file."""
    import subprocess
    import signal

    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            if old_pid != os.getpid():
                log.info("Killing stale bot instance (PID %d)...", old_pid)
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
        os.remove(PID_FILE)

    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             f"commandline like '%bot_telegram%' and processid != '{os.getpid()}'",
             "call", "terminate"],
            capture_output=True, text=True, timeout=15
        )
        killed = result.stdout.count("ReturnValue = 0")
        if killed:
            log.info("Terminated %d other bot instance(s)", killed)
            time.sleep(5)
    except Exception as e:
        log.debug("wmic cleanup: %s", e)


def main():
    log.info("Starting Jarvis Telegram Bot (PID %d)...", os.getpid())
    log.info("Owner ID: %s", OWNER_ID)
    log.info("Agent: %s, Search: %s", AGENT_URL, SEARCH_URL)
    log.info("Proxy: %s", SOCKS_PROXY or "(none)")

    _kill_stale_instances()

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        asyncio.run(_run_bot())
    finally:
        try:
            os.remove(PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
