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

import httpx
from telegram import Update
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
/fetch   — Run daily pipeline (5-30 min)
/fetch_step <name> — Run one step
  (fetch_sources, ai_audio, commit_report, jira_daily, wiki_fetch, world_audio, china_audio)
/search <query> — RAG search
/ask <question> — Ask Jarvis (LLM)
/index — Index new briefings
/knowledge — Refresh knowledge docs
/stock <code> — Stock analysis
/train — Train stock models
/scan — Run stock scanner"""


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
    except Exception as e:
        await update.message.reply_text(f"Fetch error: {e}")


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


@owner_only
async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /help for list.")


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
    app.add_handler(CommandHandler("fetch_step", cmd_fetch_step))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("index", cmd_index))
    app.add_handler(CommandHandler("knowledge", cmd_knowledge))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("train", cmd_train))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

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
