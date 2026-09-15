# Langfuse Tracing (DeepSeek + Agent Loop) Implementation Plan

> **For the implementing agent:** Follow this plan task-by-task. Complete each step, verify it works, then move to the next.

**Goal:** Self-hosted Langfuse records full prompts, completions, latency, and token counts for DeepSeek (`call_deepseek`) and Jarvis chat (`agent_loop` `ollama.chat`), without breaking the LLM path if Langfuse is down.

**Architecture:** A small `scripts/tracing.py` helper is a no-op unless `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set. DeepSeek uses the Langfuse OpenAI SDK drop-in (one generation per API call). Chat wraps the existing `ollama.chat` stream as one generation (concatenated output + Ollama eval counts). Langfuse itself runs as a sibling Docker Compose stack under `deploy/langfuse/` (UI `http://localhost:3000`). Flask stays. Fail-open everywhere.

**Tech Stack:** Langfuse Python SDK v4 (`langfuse`, OTel-based), existing `openai` client (DeepSeek), existing `ollama` Python client (streaming chat), Docker Compose for Langfuse server, pytest.

**Approved decisions (do not re-litigate):**
- Self-hosted Langfuse (not Cloud)
- Full traces (prompts + completions + model + latency + tokens)
- v1 wrap points only: `call_deepseek` and `agent_loop` `ollama.chat` (including vision `ollama.chat` in the same loop)
- Fail-open if keys missing or Langfuse unreachable
- Approach A: official SDK v4 (not OTel-first, not homegrown HTTP)
- Keep Flask; no uv, no FastAPI, no Jarvis app image, no AWS in this slice
- Do not change `tests/` gitignore; tests still live in `tests/` for local pytest
- Do not put Langfuse keys in `.global_settings.json`
- DeepSeek: OpenAI drop-in only — do **not** also open a second `as_type="generation"` around `call_deepseek` (that would duplicate traces)
- Ollama local `cost_details` omitted / zero
- Session: pass `/api/agent` `session_id` into `run_agent` and `propagate_attributes(session_id=...)`

---

### Task 1: Tracing helper — enabled flag + no-op generation (TDD)

**Files:**
- Create: `tests/test_tracing.py`
- Create: `scripts/tracing.py`

**Step 1: Write the failing tests**

```python
"""Langfuse helper is off by default and never raises into callers."""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import tracing  # noqa: E402


def test_disabled_when_keys_missing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    assert tracing.is_enabled() is False


def test_enabled_when_both_keys_set(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
    tracing.reset_for_tests()
    assert tracing.is_enabled() is True


def test_noop_generation_update_does_not_raise(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    with tracing.start_generation(name="ollama-chat", model="qwen3.5:4b", input={"q": "hi"}) as gen:
        gen.update(output="hello", usage_details={"input_tokens": 1, "output_tokens": 1})
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tracing'` (or import error for `is_enabled`).

**Step 3: Write minimal implementation**

Create `scripts/tracing.py`:

```python
"""Optional Langfuse tracing. Fail-open: never raise into LLM callers."""
from __future__ import annotations

import atexit
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger(__name__)

_warned = False


class _NoOpGeneration:
    def update(self, **kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None


def reset_for_tests() -> None:
    """Clear process-level caches so pytest env changes take effect."""
    global _warned
    _warned = False


def is_enabled() -> bool:
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def _warn_once(exc: BaseException) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    log.warning("Langfuse tracing disabled after error: %s", exc)


def _langfuse_host() -> str:
    return (
        (os.environ.get("LANGFUSE_HOST") or "").strip()
        or (os.environ.get("LANGFUSE_BASE_URL") or "").strip()
        or "http://localhost:3000"
    )


@contextmanager
def start_generation(
    *,
    name: str,
    model: str,
    input: Any = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> Iterator[Any]:
    """Yield a Langfuse generation or a no-op. Always safe to use as `with`."""
    if not is_enabled():
        yield _NoOpGeneration()
        return
    try:
        from langfuse import get_client, propagate_attributes

        client = get_client()
        attrs = {}
        if session_id:
            attrs["session_id"] = session_id
        ctx = (
            propagate_attributes(**attrs)
            if attrs
            else _null_ctx()
        )
        with ctx:
            with client.start_as_current_observation(
                as_type="generation",
                name=name,
                model=model,
                input=input,
                metadata=metadata or {},
            ) as gen:
                yield gen
                return
    except Exception as exc:
        _warn_once(exc)
        yield _NoOpGeneration()


@contextmanager
def _null_ctx() -> Iterator[None]:
    yield None


def openai_client_class():
    """Return OpenAI class: Langfuse drop-in when enabled, else stock openai."""
    if is_enabled():
        try:
            from langfuse.openai import OpenAI
            return OpenAI
        except Exception as exc:
            _warn_once(exc)
    from openai import OpenAI
    return OpenAI


def flush() -> None:
    if not is_enabled():
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception as exc:
        _warn_once(exc)


atexit.register(flush)
```

**Step 4: Run the tests and make sure they pass**

Run: `pytest tests/test_tracing.py -v`
Expected: PASS (3 tests). `langfuse` package is **not** required for these tests.

---

### Task 2: Fail-open when the SDK raises (TDD)

**Files:**
- Modify: `tests/test_tracing.py`
- Modify: `scripts/tracing.py` only if tests reveal a gap

**Step 1: Write the failing test**

Append to `tests/test_tracing.py`:

```python
def test_start_generation_fail_open_when_sdk_raises(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()

    def boom():
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(tracing, "is_enabled", lambda: True)
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise ImportError("simulated missing sdk")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with tracing.start_generation(name="x", model="m") as gen:
        gen.update(output="still ok")
```

**Step 2: Run test to verify it fails or already passes**

Run: `pytest tests/test_tracing.py::test_start_generation_fail_open_when_sdk_raises -v`
Expected: PASS if Task 1 implementation already swallows import errors; if FAIL, the `except Exception` around `get_client` is missing — add it.

**Step 3:** No production change if already green.

**Step 4:** Re-run `pytest tests/test_tracing.py -v` — all PASS.

---

### Task 3: DeepSeek client uses Langfuse OpenAI drop-in (TDD)

**Files:**
- Create: `tests/test_tracing_deepseek.py`
- Modify: `scripts/stock/config.py` (`_get_deepseek_client` only)

**Step 1: Write the failing tests**

```python
"""DeepSeek OpenAI client swaps to Langfuse drop-in when tracing is on."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_STOCK = os.path.join(_SCRIPTS, "stock")
for _p in (_SCRIPTS, _STOCK):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tracing  # noqa: E402
import config as stock_config  # noqa: E402  # scripts/stock/config.py


def test_deepseek_uses_stock_openai_when_tracing_off(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset_for_tests()
    seen = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen["cls"] = "stock"
            seen["kwargs"] = kwargs

    monkeypatch.setattr(stock_config, "get_deepseek_key", lambda: "sk-test")
    monkeypatch.setattr(tracing, "openai_client_class", lambda: FakeOpenAI)
    # After implementation, _get_deepseek_client must call tracing.openai_client_class()
    client = stock_config._get_deepseek_client()
    assert client is not None
    assert seen.get("cls") == "stock"


def test_deepseek_uses_langfuse_openai_when_tracing_on(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    tracing.reset_for_tests()
    seen = {}

    class FakeLangfuseOpenAI:
        def __init__(self, **kwargs):
            seen["cls"] = "langfuse"
            seen["kwargs"] = kwargs

    monkeypatch.setattr(stock_config, "get_deepseek_key", lambda: "sk-test")
    monkeypatch.setattr(tracing, "openai_client_class", lambda: FakeLangfuseOpenAI)
    client = stock_config._get_deepseek_client()
    assert seen.get("cls") == "langfuse"
    assert seen["kwargs"]["base_url"] == stock_config.DEEPSEEK_BASE_URL
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracing_deepseek.py -v`
Expected: FAIL because `_get_deepseek_client` still does `from openai import OpenAI` and does not call `tracing.openai_client_class`.

**Step 3: Write minimal implementation**

In `scripts/stock/config.py`, change `_get_deepseek_client` to:

```python
def _get_deepseek_client():
    """Create an OpenAI client configured for the DeepSeek API."""
    sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
    from tracing import openai_client_class
    key = get_deepseek_key()
    if not key:
        return None
    OpenAI = openai_client_class()
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
```

Prefer adding the `sys.path` insert once at module top next to the existing parent-config load (do not insert on every call). `scripts/stock/config.py` already loads `../config.py` via importlib; add:

```python
_scripts_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
```

near the other path setup, then:

```python
def _get_deepseek_client():
    from tracing import openai_client_class
    key = get_deepseek_key()
    if not key:
        return None
    OpenAI = openai_client_class()
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
```

Do **not** wrap `call_deepseek` in `start_generation` (duplicate trace). The drop-in already records input/output/usage/latency.

**Step 4: Run tests**

Run: `pytest tests/test_tracing_deepseek.py tests/test_tracing.py -v`
Expected: PASS.

---

### Task 4: Trace `agent_loop` Ollama stream (TDD)

**Files:**
- Create: `tests/test_tracing_agent_loop.py`
- Modify: `scripts/rag/agent_loop.py`

`run_agent` currently has no `session_id`. Add an optional `session_id: str | None = None` argument. Extract a helper `_traced_ollama_chat(...)` used for both the streaming call and the vision call so tests do not need to drive the full RAG/tool loop.

**Step 1: Write the failing tests**

```python
"""Ollama chat in agent_loop records one generation when tracing is on."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_RAG = os.path.join(_SCRIPTS, "rag")
for _p in (_SCRIPTS, _RAG):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tracing  # noqa: E402
import agent_loop  # noqa: E402


class _FakeChunk:
    def __init__(self, content="", tool_calls=None, prompt_eval_count=None, eval_count=None):
        self.message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count


def test_traced_ollama_chat_records_usage_on_last_chunk(monkeypatch):
    updates = []

    class FakeGen:
        def update(self, **kwargs):
            updates.append(kwargs)

    class FakeCM:
        def __enter__(self):
            return FakeGen()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        tracing,
        "start_generation",
        lambda **kwargs: FakeCM(),
    )

    def fake_chat(**kwargs):
        assert kwargs["stream"] is True
        return [
            _FakeChunk("Hel"),
            _FakeChunk("lo", prompt_eval_count=12, eval_count=3),
        ]

    fake_ollama = SimpleNamespace(chat=fake_chat)
    texts = []
    for token, extra in agent_loop._traced_ollama_chat(
        fake_ollama,
        model="qwen3.5:4b",
        messages=[{"role": "user", "content": "hi"}],
        session_id="sess-1",
        stream=True,
        think=False,
        options={},
        tools=[],
    ):
        if token:
            texts.append(token)
    assert "".join(texts) == "Hello"
    assert any(u.get("output") == "Hello" for u in updates)
    usage = next(u["usage_details"] for u in updates if "usage_details" in u)
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracing_agent_loop.py -v`
Expected: FAIL with `AttributeError: module 'agent_loop' has no attribute '_traced_ollama_chat'`.

**Step 3: Write minimal implementation**

Add to `scripts/rag/agent_loop.py` (after imports, before `run_agent`):

```python
def _usage_from_chunk(chunk) -> dict:
    prompt = getattr(chunk, "prompt_eval_count", None)
    out = getattr(chunk, "eval_count", None)
    if prompt is None and out is None:
        return {}
    details = {}
    if prompt is not None:
        details["input_tokens"] = int(prompt)
    if out is not None:
        details["output_tokens"] = int(out)
    return details


def _traced_ollama_chat(ollama_mod, *, model, messages, session_id=None, **call_kwargs):
    """Call ollama.chat; yield (token_text, chunk). Records one Langfuse generation.

    For stream=True, token_text is each content delta. For stream=False, yields
    once with the full message content.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from tracing import start_generation

    stream = call_kwargs.get("stream", True)
    with start_generation(
        name="ollama-chat",
        model=model,
        input={"messages": messages},
        session_id=session_id,
        metadata={"stream": stream},
    ) as gen:
        try:
            result = ollama_mod.chat(model=model, messages=messages, **call_kwargs)
        except Exception as exc:
            try:
                gen.update(output=str(exc), metadata={"error": True})
            except Exception:
                pass
            raise
        full = ""
        last_chunk = None
        if stream:
            for chunk in result:
                last_chunk = chunk
                text = (getattr(chunk.message, "content", None) or "") if getattr(chunk, "message", None) else ""
                full += text
                yield text, chunk
        else:
            last_chunk = result
            full = (getattr(result.message, "content", None) or "") if getattr(result, "message", None) else ""
            yield full, result
        usage = _usage_from_chunk(last_chunk) if last_chunk is not None else {}
        update_kwargs = {"output": full}
        if usage:
            update_kwargs["usage_details"] = usage
        try:
            gen.update(**update_kwargs)
        except Exception:
            pass
```

Add `import os` and `import sys` at the top of `agent_loop.py` if missing.

Change `run_agent` signature to add `session_id: str | None = None`.

Replace the streaming block:

```python
stream = ollama.chat(**call_kwargs)
...
for chunk in stream:
```

with:

```python
call_kwargs.pop("model", None)  # passed explicitly
# Keep model in call_kwargs as today — _traced_ollama_chat takes model= separately.
# Current code uses call_kwargs including model. Adapt:

stream_iter = _traced_ollama_chat(
    ollama,
    session_id=session_id,
    **call_kwargs,
)
full_content = ""
tool_calls = []
for text, chunk in stream_iter:
    c = chunk.message
    if text:
        full_content += text
        yield {"type": "token", "content": text}
    if c.tool_calls:
        tool_calls.extend(c.tool_calls)
```

Note: `call_kwargs` already contains `model`, `messages`, `stream`, `think`, `options`, `tools`. `_traced_ollama_chat` should accept `**call_kwargs` that include `model` and `messages` to avoid double-passing. Simpler signature for implementation:

```python
def _traced_ollama_chat(ollama_mod, call_kwargs: dict, *, session_id=None):
    model = call_kwargs["model"]
    messages = call_kwargs["messages"]
    ...
    result = ollama_mod.chat(**call_kwargs)
```

Use this simpler form in the real patch so `run_agent` stays:

```python
stream_iter = _traced_ollama_chat(ollama, call_kwargs, session_id=session_id)
```

Vision call (non-stream) also goes through `_traced_ollama_chat` with `stream=False`.

**Step 4: Run tests**

Run: `pytest tests/test_tracing_agent_loop.py tests/test_tracing.py -v`
Expected: PASS.

If the test's `_traced_ollama_chat(...)` kwargs do not match the simpler `(ollama_mod, call_kwargs)` form, **update the test in the same task** to call:

```python
for token, chunk in agent_loop._traced_ollama_chat(
    fake_ollama,
    {
        "model": "qwen3.5:4b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "think": False,
        "options": {},
        "tools": [],
    },
    session_id="sess-1",
):
```

Keep tests and implementation aligned. Do not expand into intent.py / other HTTP sites.

---

### Task 5: Pass `session_id` from Flask `/api/agent` into `run_agent`

**Files:**
- Modify: `scripts/rag/agent.py` — every `run_agent(...)` call site
- Modify: `scripts/rag/agent_loop.py` — already has the arg from Task 4

**Step 1: Grep call sites**

Confirmed sites in `agent.py` (around 691, 872, 944, 1007). Each must pass `session_id=session_id` (the local variable already read from JSON).

No new test file required if Task 4 covers the helper; this is a wiring change. Add one lightweight test if easy: skip if `agent.py` import is too heavy (it loads Flask + models). **Do not import `agent.py` in unit tests** (side effects). Manual verification in Task 8.

**Step 2: Patch each `run_agent(` to include `session_id=session_id`.**

**Step 3:** `python -c "import ast, pathlib; ast.parse(pathlib.Path(r'scripts/rag/agent.py').read_text(encoding='utf-8'))"` — no syntax error.

---

### Task 6: Dependency + env example

**Files:**
- Modify: `scripts/rag/requirements-rag.txt` — add `langfuse>=3.0.0`
- Create: `.env.example` (repo root)
- Modify: `docs/getting-started.md` — env table + short Langfuse subsection (full prose in Task 8; this task only adds the env rows if you split — **combine with Task 8**)

Add to `scripts/rag/requirements-rag.txt`:

```
langfuse>=3.0.0
```

(SDK v4 still publishes as `langfuse`; pin `>=3` so v4 installs. After `pip index versions langfuse` if available, prefer `langfuse>=4` if that is the current major.)

Create `.env.example`:

```
# Langfuse (self-hosted). Leave blank to disable tracing.
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000
```

Do not copy real keys. `.env` remains gitignored.

Run: `pip install "langfuse>=3"` in the environment that runs Jarvis (document in getting-started). Tests in Tasks 1–4 must still pass **without** requiring a live Langfuse server.

---

### Task 7: Self-hosted Langfuse Compose (config; no unit test)

**Files:**
- Create: `deploy/langfuse/README.md`
- Create: `deploy/langfuse/.gitignore` (ignore local `docker-compose.yml` if downloaded, and `.env`)

Official Langfuse docs require cloning [langfuse/langfuse](https://github.com/langfuse/langfuse) and running their `docker-compose.yml` (web, worker, Postgres, ClickHouse, Redis, MinIO). Do **not** hand-write a 6-service compose that will rot.

`deploy/langfuse/README.md` content:

```markdown
# Self-hosted Langfuse for Jarvis

Jarvis does not start Langfuse. Run this stack separately, then put the UI keys
into the Jarvis `.env`.

## Prerequisites

- Docker Desktop (Windows)
- 4+ CPU / 8+ GB RAM recommended for the Langfuse stack alone

## Start

```bat
cd deploy\langfuse
git clone --depth 1 https://github.com/langfuse/langfuse.git
cd langfuse
```

Edit `docker-compose.yml` secrets marked `# CHANGEME` (NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY, passwords). Then:

```bat
docker compose up -d
```

Wait until the `langfuse-web` container logs `Ready` (~2–3 minutes). Open http://localhost:3000 and create the first user (becomes admin). Create a project, copy **Public key** and **Secret key**.

## Point Jarvis at it

In `c:\jarvis\.env` (never commit):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

Restart Jarvis (`bin\jarvis-restart.bat`). `bin\jarvis-start.bat` does **not** start Langfuse.

## Stop

```bat
cd deploy\langfuse\langfuse
docker compose down
```

Use `docker compose down -v` only if you intend to wipe all traces.
```

Add `deploy/langfuse/.gitignore`:

```
langfuse/
.env
```

so the cloned vendor repo is not committed.

**Verify:** README exists and documents `localhost:3000`. Do not `docker compose up` in CI. Manual: implementer may start compose if Docker is available; not required to finish unit tests.

---

### Task 8: Getting-started subsection

**Files:**
- Modify: `docs/getting-started.md`
  - Add Langfuse rows to **Environment Variables Reference**
  - Add a short subsection after Telegram (or after AI Models): "Optional: LLM tracing with Langfuse"

Table rows:

| Variable | Purpose | Default |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | empty (tracing off) |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | empty (tracing off) |
| `LANGFUSE_HOST` | Self-hosted Langfuse base URL | `http://localhost:3000` |

Prose: tracing is optional; start stack per `deploy/langfuse/README.md`; send one chat in the agent UI and one DeepSeek stock analyze; confirm a trace in the Langfuse UI (input, output, latency, tokens). If Langfuse is down, Jarvis still answers.

Also add `langfuse` to the pip install list in getting-started Step 3.

---

### Task 9: Manual verification checklist (implementer)

Do this after Tasks 1–8. Do not claim done without the unit-test evidence from Tasks 1–4.

**Unit tests (required):**

```
pytest tests/test_tracing.py tests/test_tracing_deepseek.py tests/test_tracing_agent_loop.py -v
```

Expected: all PASS.

**Optional live check (if Docker + Ollama + DeepSeek key available):**

1. `docker compose up -d` in the cloned Langfuse repo; UI at http://localhost:3000
2. Set keys in `.env`; restart agent
3. Send a short chat → Langfuse shows `ollama-chat` generation with prompt, completion, latency; token fields if Ollama sent eval counts
4. Trigger a DeepSeek stock call → generation with `deepseek-v4-flash` and `usage` tokens
5. Stop Langfuse (`docker compose stop`) and send another chat → Jarvis still streams; one warning in logs is acceptable

**Out of scope (do not do):**
- Wrap `intent.py`, `query_rewrite.py`, stock scanners, translate, etc.
- FastAPI, uv, Jarvis Dockerfile, AWS
- Un-ignore `tests/` or `git rm --cached jarvis-start.log`

---

## Verification Summary

- [ ] `scripts/tracing.py` exists; `is_enabled()` false without keys
- [ ] `start_generation` never raises (no-op or fail-open)
- [ ] `_get_deepseek_client` uses `tracing.openai_client_class()`
- [ ] `run_agent` / `_traced_ollama_chat` records output + `usage_details` from last Ollama chunk
- [ ] `session_id` forwarded from `/api/agent`
- [ ] `.env.example` + `deploy/langfuse/README.md` + getting-started env rows
- [ ] pytest files above all PASS
- [ ] Flask unchanged; no second DeepSeek generation span
