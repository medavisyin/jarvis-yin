# LLM — Large Language Models & Local Inference

> Learning track for understanding, deploying, and tuning large language models.
> Maps to **Track 2 (LLM)** in the [learning roadmap](../rag/ch8-learning-roadmap.md).

---

## What This Covers

- **Local LLM serving** with Ollama (model selection, Modelfile, parameters, quantization)
- **Prompt engineering** (system prompts, few-shot, chain-of-thought, tool calling)
- **Streaming inference** (SSE, token-by-token delivery)
- **Model families** (Qwen, Llama, Gemma, Mistral — when to pick which)
- **Fine-tuning concepts** (LoRA, QLoRA, RLHF — theory and when it's worth it)

## How Jarvis Uses LLMs

| Component | LLM Role | Script |
|-----------|----------|--------|
| RAG Agent chat | Ollama streaming + auto-RAG context injection | `scripts/rag/agent.py` |
| Query rewriting | Small model (`qwen3:1.7b`) rewrites vague search queries | `scripts/rag/search_ui.py` |
| Learning guide generation | Generates daily learning content from briefing topics | `scripts/tools/learning-guide-generator.py` |
| Stock sentiment | LLM-based sentiment analysis on financial news | `scripts/stock/` |
| News translation | Ollama translates world/China news content | Pipeline scripts |

## Related Jarvis Docs

- [Ollama — Local LLM](ollama-local-llm.md) — setup, models, API usage
- [Prompt Engineering](llm-prompt-engineering.md) — patterns and techniques
- [RAG Agent Design](../../design/rag-agent-design.md) — how the agent orchestrates LLM + retrieval
- [Agent Implementation](../../implementation/rag/agent-impl.md) — SSE streaming, tool calling, sessions

## Beginner Guide: How LLMs Generate Text

### What Actually Happens When You Ask an LLM a Question?

An LLM doesn't "think" — it **predicts the next word** (technically "token") one at a time. Given "The capital of France is", it calculates a probability for every possible next word:

```
"Paris"    → 92% probability
"a"        → 3%
"located"  → 2%
"the"      → 1%
...thousands more words with tiny probabilities
```

Then it picks one, adds it to the sentence, and repeats. The **parameters** you set control *how* it picks from those probabilities.

### Temperature — Controls Randomness

Temperature scales the probability distribution before picking the next word.

```
temperature = 0.0  (deterministic — always picks the highest probability)
  "The capital of France is Paris."
  "The capital of France is Paris."    ← same answer every time
  "The capital of France is Paris."

temperature = 0.7  (balanced — usually picks likely words, occasionally creative)
  "The capital of France is Paris, a city known for..."
  "The capital of France is Paris, often called..."    ← slight variation

temperature = 1.5  (wild — frequently picks unlikely words)
  "The capital of France is remarkably intertwined with..."
  "The capital of France is dancing through centuries..."    ← unpredictable
```

**Rule of thumb:**
- **0.0–0.3** → Factual tasks (code, data extraction, translation) — you want consistency
- **0.5–0.8** → General conversation, writing — balanced creativity
- **1.0+** → Brainstorming, poetry — you want surprise

**In Jarvis:** The agent uses low temperature for RAG answers (factual, grounded in retrieved docs) and slightly higher for creative tasks like learning guides.

### top_p (Nucleus Sampling) — Controls Vocabulary Width

Instead of scaling probabilities (temperature), `top_p` **cuts off** the tail. It keeps only the smallest set of words whose combined probability reaches `top_p`.

```
Given probabilities: Paris=92%, a=3%, located=2%, the=1%, Berlin=0.5%, ...

top_p = 0.95 → Keep: [Paris, a, located]  (92+3+2 = 97% > 95%, stop)
                Pick randomly from these 3 words (weighted by probability)

top_p = 0.50 → Keep: [Paris]  (92% > 50%, stop immediately)
                Always picks "Paris" — very focused

top_p = 1.00 → Keep ALL words (no filtering)
                Could pick anything, even very unlikely words
```

**Temperature vs top_p — what's the difference?**

| | Temperature | top_p |
|-|-------------|-------|
| **What it does** | Reshapes the probability curve (flatter = more random) | Cuts off the long tail (fewer candidates) |
| **Low value** | Always picks the #1 word | Only considers top candidates |
| **High value** | All words become equally likely | All words stay in the running |
| **Best for** | Controlling "creativity level" | Preventing "nonsense" words |

Most people adjust **one or the other**, not both. Ollama defaults: `temperature=0.8`, `top_p=0.9`.

### Context Window — How Much the LLM Can "See"

The context window is the **maximum number of tokens** the model can process at once. This includes everything: the system prompt + the retrieved RAG chunks + the conversation history + the new question + the answer being generated.

```
┌─────────────────────────────────────────────────┐
│              Context Window (e.g. 8192 tokens)  │
│                                                 │
│  System prompt:          ~200 tokens            │
│  RAG context (5 chunks): ~1500 tokens           │
│  Conversation history:   ~2000 tokens           │
│  User question:          ~50 tokens             │
│  ─────────────────────────────────               │
│  Space left for answer:  ~4442 tokens           │
└─────────────────────────────────────────────────┘
```

**What happens if you exceed it?** The model silently drops the oldest content. Your carefully retrieved RAG context could get pushed out by long conversation history — the model literally "forgets" it.

| Model | Typical Context Window |
|-------|----------------------|
| `qwen3:1.7b` | 32,768 tokens |
| `llama3.1:8b` | 131,072 tokens |
| `gemma2:9b` | 8,192 tokens |
| GPT-4o (cloud) | 128,000 tokens |

**In Jarvis:** The agent manages this by limiting RAG context to the top 5 chunks and trimming conversation history when it gets long.

### Quick Experiment: Try It Yourself

```bash
# Install Ollama (https://ollama.com), then:
ollama pull qwen3:1.7b

# Try different temperatures:
ollama run qwen3:1.7b "Write a one-sentence summary of machine learning"
# Run it 3 times with default settings — answers will vary slightly

# In the Ollama API (what Jarvis uses):
curl http://localhost:11434/api/chat -d '{
  "model": "qwen3:1.7b",
  "messages": [{"role": "user", "content": "What is RAG?"}],
  "stream": false,
  "options": {"temperature": 0.0}
}'
# temperature=0.0 gives identical answers every time
```

## Suggested Learning Path

1. **Beginner:** Run Ollama locally, try different models, experiment with temperature/top_p, observe how context window affects answers
2. **Intermediate:** Write effective system prompts, implement tool calling, understand tokenization
3. **Advanced:** Fine-tuning with LoRA, RLHF concepts, model evaluation and benchmarking

---

*Part of the [Jarvis Learning Series](../). See also: [RAG](../rag/), [Machine Learning](../machine-learning/), [Hugging Face](../huggingface/)*
