# Know-How: LLM Prompt Engineering

A beginner-friendly guide to **prompt engineering** — designing inputs for large language models to get reliable, structured outputs. Covers patterns used throughout Jarvis. No prior NLP background required.

## What is prompt engineering?

Prompt engineering is the practice of crafting inputs to LLMs so they produce useful, predictable outputs. Think of it as **programming via natural language** — instead of writing code, you write precise instructions.

The same LLM can be a news anchor, a financial analyst, a translator, or a JSON formatter — depending entirely on **how you prompt it**.

## System vs user prompts

LLM APIs typically accept two message types:

| Role | Purpose | Example |
|------|---------|---------|
| **System** | Sets the persona, rules, and output format — the "operating manual" | "You are a professional Chinese news anchor. Generate a narration script..." |
| **User** | Provides the specific request or data | "Here are today's AI news items: [data]" |

The system prompt is set once per conversation/task. The user prompt changes with each request.

```python
messages = [
    {"role": "system", "content": "You are a senior financial analyst..."},
    {"role": "user", "content": "Analyze this stock data: ..."},
]
```

## Key techniques

### Role assignment

Tell the model **who** it is. This shapes tone, expertise level, and output style.

| Jarvis use case | Role | File |
|-----------------|------|------|
| Audio narration | "You are a professional news anchor" | `agent.py` |
| Stock prediction | "You are a senior financial analyst" | `llm_reasoning.py` |
| Sentiment analysis | "You are a sentiment analysis expert" | `sentiment.py` |
| Translation | "You are a professional translator" | `run-world-news.py` |
| Teaching | "You are an expert AI tutor" | `agent.py` (Explain This) |

### Output format specification

Explicitly state the **exact format** you want:

```
Respond ONLY with valid JSON in this format:
{"score": <float -1 to 1>, "reasoning": "<one sentence>"}
```

Without this, the model may add commentary, explanations, or markdown around the structured data.

### Constraint setting

Boundaries prevent the model from going off-track:

- `"Do NOT include any text outside the JSON object"`
- `"Keep your narration under 2000 characters"`
- `"Use exactly these section headers: ..."`
- `"If insufficient data, return {"score": 0, "reasoning": "insufficient data"}"`

### Temperature control

Temperature controls randomness in the model's output:

| Temperature | Behavior | Use case in Jarvis |
|-------------|----------|-------------------|
| 0.1–0.3 | Deterministic, focused | Sentiment scoring, JSON extraction, translation |
| 0.4–0.5 | Balanced | Stock analysis reports, explanations |
| 0.6–0.8 | Creative, varied | Audio narration scripts, learning content |

```python
"options": {"temperature": 0.3, "num_predict": 500}  # structured output
"options": {"temperature": 0.7, "num_predict": 8192}  # creative narration
```

### Few-shot examples

Showing the model what good output looks like before asking for output:

```
Example input: "Company reports record earnings"
Example output: {"score": 0.8, "reasoning": "Strong positive earnings signal"}

Now analyze: "Stock drops 5% on trade fears"
```

Jarvis uses few-shot patterns in sentiment analysis and scanner scoring.

## Structured output patterns

Getting reliable JSON from LLMs is a core challenge. Jarvis uses several strategies:

### The prompt approach

```python
prompt = """Analyze the sentiment of this headline for stock {symbol}.
Respond ONLY with valid JSON:
{{"score": <float from -1.0 to 1.0>, "reasoning": "<brief explanation>"}}

Headline: {headline}"""
```

### Parsing with fallback

LLMs sometimes add extra text around JSON. Jarvis extracts it:

```python
import json, re

def parse_llm_json(text):
    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try extracting JSON from surrounding text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None  # fallback: parsing failed
```

### Batch processing

For efficiency, Jarvis sometimes sends multiple items in one prompt:

```python
# Translation: batch multiple titles in one call
prompt = f"""Translate these {len(texts)} texts from English to Chinese.
Return a JSON array with exactly {len(texts)} translated strings.
[{json.dumps(texts, ensure_ascii=False)}]"""
```

## LLM application patterns in Jarvis

| Pattern | Where | Temperature | Model | Output |
|---------|-------|------------|-------|--------|
| **News narration** | Daily Fetch audio | 0.7 | `qwen3:1.7b` | Creative script (~2000 chars) |
| **Sentiment scoring** | `sentiment.py` | 0.3 | `qwen3:1.7b` | JSON `{score, reasoning}` |
| **Scanner ranking** | `scanner.py` | 0.3 | `qwen3.5:4b` | JSON with numeric scores per criterion |
| **Stock prediction** | `llm_reasoning.py` | 0.5 | `qwen3.5:4b` | Multi-section markdown report |
| **News translation** | `run-world-news.py` | 0.3 | `qwen3:1.7b` | JSON array of translated strings |
| **Query rewrite** | `search_ui.py` | 0.3 | any | Short search query |
| **Explain This** | `agent.py` | 0.5 | `qwen3.5:4b` | Educational deep-dive |
| **Trend analysis** | `agent.py` | 0.5 | `qwen3.5:4b` | Narrative outlook summary |

## Token management

Two key parameters control LLM resource usage:

| Parameter | What it does | Jarvis approach |
|-----------|-------------|-----------------|
| `num_predict` | Maximum output tokens the model can generate | Small for JSON (500), large for narration (8192) |
| `num_ctx` | Total context window (input + output) | Dynamically sized based on input length + conversation history |

```python
history_len = sum(len(m.get("content", "")) for m in messages)
ctx_len = len(augmented_query) + len(sys_prompt) + history_len
# Adjust num_ctx to fit content + leave room for generation
```

## The `think: false` pattern

Some models have a "reasoning" or "thinking" mode that produces intermediate reasoning tokens before the answer. Jarvis disables this for most calls:

```python
"options": {"think": False}
```

**Why:** Reasoning tokens add latency, increase output length, and can inject unwanted text into structured outputs. For sentiment scoring or translation, you want the answer directly — not a chain-of-thought analysis first.

**Exception:** For complex multi-step reasoning (stock prediction reports), thinking mode can improve quality.

## Streaming vs non-streaming

| Mode | When to use | Jarvis example |
|------|-------------|----------------|
| **Streaming** (`stream: true`) | User-facing chat — tokens appear as generated | Agent chat, Explain This |
| **Non-streaming** (`stream: false`) | Background processing — need complete response | Sentiment analysis, translation, narration |

Streaming improves perceived latency in chat UIs. Non-streaming is simpler to parse and process programmatically.

## Error handling patterns

| Issue | Strategy |
|-------|----------|
| **Timeout** | Set per-call timeout (600s for narration, 30s for sentiment); retry with shorter input |
| **JSON parse failure** | Regex extraction fallback; default value if all parsing fails |
| **Empty response** | Check for empty/whitespace response; retry once; log and skip |
| **Model refusal** | Some prompts trigger safety filters; rephrase or simplify |
| **Token overflow** | Truncate input to fit context window; summarize long conversations |

## Practical tips

1. **Be specific** — "Analyze the sentiment" is vague; "Rate the sentiment as a float from -1.0 to 1.0" is precise
2. **Constrain the output** — Always specify format, length limits, and what to exclude
3. **Test edge cases** — Empty input, very long input, non-English text, malformed data
4. **Validate output** — Never trust LLM output blindly; parse, validate, fallback
5. **Use the smallest model that works** — `qwen3:1.7b` for simple tasks (sentiment, translation), `qwen3.5:4b` for complex reasoning
6. **Separate concerns** — One prompt per task; don't ask the model to analyze + translate + format in one call

## Further reading

- [OpenAI prompt engineering guide](https://platform.openai.com/docs/guides/prompt-engineering)
- [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Jarvis implementation: [`scripts/rag/agent.py`](../../../scripts/rag/agent.py), [`scripts/stock/sentiment.py`](../../../scripts/stock/sentiment.py), [`scripts/stock/llm_reasoning.py`](../../../scripts/stock/llm_reasoning.py)
