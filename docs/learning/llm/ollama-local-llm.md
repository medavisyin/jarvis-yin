# Know-How: Ollama — Running LLMs Locally

A practical overview of **Ollama** and how **Jarvis** talks to a **local large language model (LLM)** over HTTP.

## What is Ollama?

**Ollama** is a tool for **downloading**, **managing**, and **serving** LLMs on your own computer.

- Exposes a simple **HTTP API** that feels similar to cloud “chat completion” APIs, but **on localhost**.
- Models can run on **CPU** or **GPU**, depending on hardware and model size.

Official site:

- [Ollama](https://ollama.ai)
- [Ollama API reference](https://github.com/ollama/ollama/blob/main/docs/api.md)

## Why use a local LLM instead of a cloud API?

- **Privacy:** Prompts and retrieved context can stay on your machine.
- **Cost:** No per-token cloud billing for local inference.
- **Latency:** No round trip to the public internet (inference itself may still be slow on CPU).
- **Offline:** Works without external API access once the model is pulled.

Trade-offs: smaller local models may be **less capable** than frontier cloud models; **CPU** inference can be slower than GPU or hosted APIs.

## How Jarvis uses Ollama

- **Three model tiers:** **`qwen3.5:4b`** for the **main chat** agent, **`qwen3:1.7b`** for **fast tasks** (query rewriting, categorization, trend analysis, KB summaries, etc.), and **`qwen3:1.7b`** as the **narration model** for Daily Fetch segmented audio generation. The fast model is the constant **`OLLAMA_MODEL_FAST`** in `agent.py`; the narration model is **`OLLAMA_MODEL_NARRATION`** (overridable via **`RAG_NARRATION_MODEL`** env var); the main chat model is **`OLLAMA_MODEL`** and is often overridden by **`RAG_AGENT_MODEL`** from the environment.
- **Default main model:** `qwen3.5:4b` (about **4B** parameters—often reasonable on CPU for interactive use).
- **`think: false`:** On **all fast-response paths**, Jarvis calls **`/api/chat`** with **`think: false`** so “thinking” models skip hidden reasoning tokens and stay fast (see [Think Mode vs Non-Think Mode](#think-mode-vs-non-think-mode-critical-for-performance) below).
- **Endpoints:** **`POST /api/chat`** is **primary** (supports `messages`, streaming, and the `think` flag). **`POST /api/generate`** is still used in **legacy** spots but is **being phased out** in favor of `/api/chat` where possible.
- **Base URL:** `http://localhost:11434` (Ollama’s default).
- **`agent.py`** sends **`POST /api/chat`** with **`stream: true`** for interactive chat so tokens can flow to the UI as they are generated.
- **Model switching:** Jarvis may expose something like **`/api/switch-model`** so you can change models at runtime without editing code (see your local `agent.py` for the exact contract).

Environment variables (typical Jarvis conventions):

| Variable | Purpose |
|----------|---------|
| `OLLAMA_HOST` | API base URL (default `http://localhost:11434`) |
| `OLLAMA_MODEL` | Main chat model name (default `qwen3.5:4b`) |
| `RAG_AGENT_MODEL` | When set, used as the main chat model (see `OLLAMA_MODEL` in `agent.py`) |
| `OLLAMA_MODEL_FAST` | Not an env var in stock Jarvis: the fast model is the constant **`qwen3:1.7b`** in `agent.py` |
| `RAG_NARRATION_MODEL` | When set, used as the narration model for Daily Fetch audio (default `qwen3:1.7b`; constant **`OLLAMA_MODEL_NARRATION`** in `agent.py`) |

## The Ollama API (as used by Jarvis)

### Streaming chat

```python
import json
import requests

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen3.5:4b",
        "messages": [
            {"role": "system", "content": "You are Jarvis..."},
            {"role": "user", "content": "How does DICOM routing work?"},
        ],
        "stream": True,
    },
    stream=True,
)

for line in response.iter_lines():
    if not line:
        continue
    data = json.loads(line)
    print(data["message"]["content"], end="")
```

Each line is a JSON object; streamed partial messages are common—production code should handle errors and the final `done` message per Ollama’s API.

### Health / model list

```python
requests.get("http://localhost:11434/api/tags")
```

Lists models available to the local Ollama daemon.

## Installation

1. Download and install Ollama from [https://ollama.ai](https://ollama.ai).
2. Start the Ollama service (the installer usually sets this up as a background service).
3. Pull a model:

```bash
ollama pull qwen3.5:4b
```

4. Verify:

```bash
ollama list
```

## Model selection guide

- **Smaller models (e.g. low billions of parameters):** Faster on CPU, less depth for reasoning or long contexts.
- **Larger models:** Better quality possible, but may need **GPU** or patience on CPU.
- **Quantization:** Many Ollama models are quantized for size/speed; names often encode variants—pick what fits RAM/VRAM.

Always test with **your real Jarvis prompts** (RAG context + instructions), not generic trivia.

## Performance tips

- Prefer **GPU** when available for larger models.
- Keep **retrieved context** concise; huge prompts slow any model.
- If streaming feels slow, check **CPU/RAM** pressure and whether a smaller model is acceptable.
- Ensure only **one** heavy inference workload competes for GPU/CPU at a time.

## Further reading

- [Ollama documentation](https://github.com/ollama/ollama/tree/main/docs)
- [Ollama model library](https://ollama.com/library)

---

## Ollama API Deep Dive: Endpoints, Modes, and Patterns

### `/api/generate` vs `/api/chat` — Two Endpoints, Different Behaviors

Ollama offers two main inference endpoints. Jarvis uses BOTH, but for different purposes:

| Endpoint | Input Format | Output Format | Best For |
|----------|-------------|---------------|----------|
| `/api/generate` | Single `prompt` string | `response` field | Simple completions, one-shot tasks |
| `/api/chat` | `messages` array (system/user/assistant) | `message.content` field | Multi-turn conversations, precise control |

#### `/api/generate` Example
```python
resp = requests.post("http://localhost:11434/api/generate", json={
    "model": "qwen3.5:4b",
    "prompt": "What is DICOM?",
    "stream": False,
    "options": {"num_predict": 200, "num_ctx": 2048}
})
print(resp.json()["response"])
```

#### `/api/chat` Example
```python
resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen3.5:4b",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is DICOM?"}
    ],
    "stream": False,
    "options": {"num_predict": 200, "num_ctx": 2048}
})
print(resp.json()["message"]["content"])
```

**Why Jarvis switched from `/api/generate` to `/api/chat`:** The `/api/chat` endpoint supports the `think` parameter (see below), which is critical for controlling "thinking" models. The `/api/generate` endpoint does NOT support `think: false`, so thinking models always generate hidden reasoning tokens, causing significant latency.

### Think Mode vs Non-Think Mode (Critical for Performance!)

Modern "reasoning" models (like `qwen3.5:4b`, `qwen3:1.7b`) have a built-in "thinking" capability. When thinking is enabled, the model generates internal reasoning tokens BEFORE producing the visible response. This is great for complex reasoning but terrible for simple tasks.

#### The Problem: Hidden Thinking Overhead

```
User query: "Summarize this AI news"

WITH thinking enabled (default for /api/generate):
  [Hidden thinking: 200-500 tokens, 15-30 seconds on CPU]
  [Visible response: 100 tokens, 5-10 seconds]
  Total: 20-40 seconds

WITH thinking disabled (think: false on /api/chat):
  [No hidden thinking]
  [Visible response: 100 tokens, 5-10 seconds]
  Total: 5-10 seconds  ← 3-4x faster!
```

#### How to Disable Thinking

```python
resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen3:1.7b",
    "messages": [{"role": "user", "content": "Summarize this news"}],
    "stream": True,
    "think": False,  # <-- THIS IS THE KEY PARAMETER
    "options": {"num_predict": 200}
})
```

**Important:** `think: false` is ONLY supported on `/api/chat`, NOT on `/api/generate`. This is why Jarvis migrated all fast-response paths from `/api/generate` to `/api/chat`.

#### When to Use Each Mode

| Use Case | Endpoint | Think | Model | Why |
|----------|----------|:-----:|-------|-----|
| Chat with user (main agent) | `/api/chat` | `true` (default) | `qwen3.5:4b` | Complex reasoning benefits from thinking |
| Query rewriting | `/api/chat` | `false` | `qwen3:1.7b` | Simple task, speed matters |
| Trend analysis (predictions) | `/api/chat` | `true` | `qwen3:1.7b` | Deep reasoning for better predictions |
| AI News KB categorization | `/api/chat` | `false` | `qwen3:1.7b` | Batch classification, speed critical |
| AI News KB summary | `/api/chat` | `false` | `qwen3:1.7b` | Streaming output |
| Audio narration (Knowledge) | `/api/chat` | `true` | `qwen3:1.7b` | Educational long-form narration (~10 min) |
| Audio narration (Daily Fetch) | `/api/chat` | `true` | `qwen3:1.7b` | Segmented per-source podcast narration (~15 min total, `OLLAMA_MODEL_NARRATION`) |
| Image analysis | `/api/chat` | `true` (default) | `qwen3-vl:8b` | Vision model, complex analysis |

### Streaming vs Non-Streaming

#### Non-Streaming (`stream: false`)
The server waits until the entire response is generated, then returns it all at once.

```python
resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen3:1.7b",
    "messages": [{"role": "user", "content": "Classify this item"}],
    "stream": False,
    "think": False,
})
result = resp.json()["message"]["content"]
```

**Use when:** You need the complete response before proceeding (e.g., query rewriting, categorization).

#### Streaming (`stream: true`)
The server sends tokens one at a time as they're generated. Each line is a JSON object.

```python
resp = requests.post("http://localhost:11434/api/chat", json={
    "model": "qwen3:1.7b",
    "messages": [{"role": "user", "content": "Write a summary"}],
    "stream": True,
    "think": False,
}, stream=True)

for line in resp.iter_lines():
    if not line:
        continue
    chunk = json.loads(line)
    if chunk.get("done"):
        break
    token = chunk.get("message", {}).get("content", "")
    print(token, end="", flush=True)
```

**Use when:** You want to show output progressively to the user (e.g., chat responses, trend analysis, AI summaries). Jarvis uses Server-Sent Events (SSE) to forward streamed tokens to the browser.

### The `options` Object — Controlling Generation

The `options` object controls how the model generates text. These parameters have a major impact on both quality and speed.

#### `num_predict` — How Many Tokens to Generate

**What it is:** The maximum number of tokens (roughly words/word-pieces) the model will produce in its response. Once this limit is reached, generation stops even mid-sentence.

**Why it matters:** On CPU, generating each token takes time (~50-200ms depending on model size). Setting `num_predict: 2000` means potentially 100-400 seconds of generation. Setting `num_predict: 30` means at most 6 seconds.

```
num_predict: 30   → "authentication using JWT tokens"  (fast, for rewrites)
num_predict: 200  → A full paragraph summary            (medium, for summaries)
num_predict: 2000 → A detailed multi-paragraph answer   (slow, for chat)
```

**Jarvis settings:**
| Task | `num_predict` | Why |
|------|:---:|-----|
| Query rewriting | 30-40 | Only need a short rephrased query |
| News categorization | 60 | Just category labels |
| Trend analysis (predictions) | 2048-4096 | Deep prediction analysis |
| Main chat responses | 2000+ | Detailed answers with context |

#### `num_ctx` — Context Window Size

**What it is:** The total number of tokens the model can "see" at once — this includes BOTH the input (system prompt + user message + any RAG context) AND the output being generated. Think of it as the model's working memory.

**Why it matters:** Larger context windows require more RAM and are slower to process. The model must process ALL context tokens before generating the first output token (this is called "prefill"). On CPU:

```
num_ctx: 128   → Prefill: ~50ms   (tiny context, fast)
num_ctx: 2048  → Prefill: ~500ms  (standard, moderate)
num_ctx: 8192  → Prefill: ~2-4s   (large context, slow)
```

**What happens if context exceeds `num_ctx`?** The oldest tokens are silently dropped. If your system prompt + RAG context + query is 3000 tokens but `num_ctx` is 2048, the model only sees the last 2048 tokens — potentially losing important context.

**Jarvis settings:**
| Task | `num_ctx` | Why |
|------|:---:|-----|
| Query rewriting | 128 | Input is just the short query, no context needed |
| News categorization | 256 | Short prompt + item titles |
| Trend analysis (predictions) | 4096 | Data + reasoning context |
| Main chat (small context) | 2048 | Short queries with minimal RAG |
| Main chat (medium context) | 4096 | Queries with RAG context |
| Main chat (large context) | 8192 | Queries with lots of RAG context |
| Extended learning session | 16384 | Long conversations with summarization memory |

**Jarvis auto-scales `num_ctx`** based on total content length (system prompt + conversation history + RAG context + current query):

*All sessions (regular chat and learning):*
- Total < 1,500 chars → `num_ctx=2048`, `num_predict=4096`
- Total < 6,000 chars → `num_ctx=4096`, `num_predict=4096`
- Total < 14,000 chars → `num_ctx=8192`, `num_predict=4096`
- Total ≥ 14,000 chars → `num_ctx=16384`, `num_predict=4096`

*Learning sessions* (AI Learning, Tech English, Casual English, AWS AIF-C01 — detected by `system_prompt_override`):
- Total < 6,000 chars → `num_ctx=8192`, `num_predict=4096`
- Total ≥ 6,000 chars → `num_ctx=16384`, `num_predict=4096`

Learning sessions use 4x the response token budget to allow detailed teaching with article analysis, code snippets, and web references. A "▶ Continue" button in the UI lets users extend truncated responses.

#### `temperature` — Creativity vs Determinism

**What it is:** Controls how "random" the model's word choices are. At each step, the model calculates a probability for every possible next token. Temperature scales these probabilities:

```
temperature: 0.0  → Always picks the highest-probability token (deterministic)
temperature: 0.3  → Mostly picks high-probability tokens (focused)
temperature: 0.8  → Balanced between likely and creative choices (default)
temperature: 1.5  → Often picks lower-probability tokens (very creative/chaotic)
```

**Analogy:** Imagine choosing a restaurant. Temperature 0 = always go to your favorite. Temperature 0.8 = usually go to favorites but sometimes try something new. Temperature 1.5 = pick almost randomly.

**When to use low temperature:** Factual tasks where you want consistent, predictable output (classification, rewriting, data extraction).

**When to use high temperature:** Creative tasks where variety is desirable (brainstorming, storytelling).

**Jarvis typically uses the default (0.8)** and relies on `num_predict` and `num_ctx` for performance tuning rather than temperature.

#### `top_p` — Nucleus Sampling

**What it is:** Instead of considering ALL possible next tokens, only consider the smallest set of tokens whose combined probability exceeds `top_p`. This filters out very unlikely tokens.

```
top_p: 0.9  → Consider tokens that cover 90% of probability mass
top_p: 0.5  → Only consider the most likely tokens (more focused)
top_p: 1.0  → Consider all tokens (no filtering)
```

**Relationship with temperature:** Both control randomness, but differently. Temperature scales probabilities; top_p filters the candidate set. In practice, adjusting one is usually enough.

#### `repeat_penalty` — Avoiding Repetition

**What it is:** Penalizes the model for repeating tokens it has already generated. Higher values = stronger penalty against repetition.

```
repeat_penalty: 1.0  → No penalty (model may repeat phrases)
repeat_penalty: 1.1  → Mild penalty (default, good balance)
repeat_penalty: 1.5  → Strong penalty (avoids repetition but may reduce coherence)
```

#### Quick Reference Table

| Parameter | Default | Description | Performance Impact |
|-----------|:-------:|-------------|:------------------:|
| `num_predict` | 128 | Max output tokens | **High** — directly controls generation time |
| `num_ctx` | 2048 | Context window (input + output) | **High** — larger = slower prefill |
| `temperature` | 0.8 | Randomness (0=deterministic) | None |
| `top_p` | 0.9 | Nucleus sampling threshold | None |
| `repeat_penalty` | 1.1 | Repetition penalty | None |

**The two parameters that matter most for speed:** `num_predict` and `num_ctx`. Everything else affects quality but not performance.

> **Note:** `top_k` and `min_score` are NOT Ollama parameters — they are **search parameters** used by Qdrant vector search:
> - `top_k`: Maximum number of results to return from the vector database (default: 10 in Jarvis)
> - `min_score`: Minimum cosine similarity threshold — results below this score are filtered out (default: 0.5 in Jarvis)
>
> These are configured in the search API (`/api/search?top_k=10&min_score=0.5`), not in the Ollama `options` object. See the [Search UI Implementation](../rag/search-ui-impl.md) for details.

### Model Selection Strategy in Jarvis

Jarvis uses three models for different purposes:

| Model | Size | Speed (CPU) | Quality | Used For |
|-------|------|-------------|---------|----------|
| `qwen3:1.7b` | 1.7B params | ~0.5s first token | Basic | Fast tasks: rewriting, classification, educational narration, trend predictions, Daily Fetch segmented audio narration |
| `qwen3.5:4b` | 4B params | ~3-5s first token | Good | Main chat agent, complex reasoning |
| `qwen3-vl:8b` | 8B params | ~15-30s first token | Best | Image/vision analysis |

The fast model (`qwen3:1.7b`) is stored in the constant `OLLAMA_MODEL_FAST` in `agent.py`. The main model is in `OLLAMA_MODEL` (configurable via `RAG_AGENT_MODEL` env var).

**Key insight:** Using the right model for the right task is as important as the prompt itself. A 1.7B model with `think: false` can respond in under 1 second for simple tasks, while a 4B model with thinking enabled might take 30+ seconds for the same task.

### Error Handling Patterns

Jarvis wraps all Ollama calls in try/except blocks because the LLM server may be:
- Not running (connection refused)
- Overloaded (timeout)
- Missing the requested model (404)

```python
try:
    resp = requests.post(
        "http://localhost:11434/api/chat",
        json={...},
        timeout=10,  # Short timeout for fast tasks
    )
    if resp.ok:
        result = resp.json()["message"]["content"]
except Exception:
    pass  # Graceful degradation — feature works without LLM
```

For the search UI query rewriting: if Ollama is down, the original query is used as-is. For the agent chat: if Ollama is down, an error message is shown to the user.
