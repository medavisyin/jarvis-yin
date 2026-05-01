# Hugging Face — Models, Datasets & the HF Ecosystem

> Learning track for the Hugging Face ecosystem: Transformers, Sentence Transformers,
> Hub, and model evaluation. Maps to **Track 3 (HuggingFace)** in the
> [learning roadmap](../rag/ch8-learning-roadmap.md).

---

## Reading Order

Follow the chapters in order. Each builds on the previous one.

| # | Chapter | What You'll Learn |
|:-:|---------|-------------------|
| 1 | [Getting Started](ch1-getting-started.md) | Pre-trained models, environment setup, your first `pipeline`, model names, inference vs training, offline mode |
| 2 | [Tokenization Deep Dive](ch2-tokenization.md) | Why tokenization matters, BPE / WordPiece / SentencePiece, special tokens, padding, truncation, attention mask |
| 3 | [Model Selection & HF Hub](ch3-model-selection.md) | Task types, model cards, MTEB leaderboard, size vs quality, bi-encoder vs cross-encoder, licenses |
| 4 | [Sentence Transformers](sentence-transformers.md) | Embedding models, `encode`, cosine similarity, batch encoding, offline mode — *Jarvis's core HF usage* |
| 5 | [Datasets Library](ch4-datasets-library.md) | HF `datasets` for RAG evaluation, data management, metrics (precision, recall, MRR), CLI tools |
| — | [Concepts Reference](#beginner-guide-what-are-transformers) | Quick reference below: Transformers architecture, `pipeline` / `AutoTokenizer` / `AutoModel` layers |

## Beginner Path (Start Here)

If you're brand new to Hugging Face, read just these three first:

1. **Ch 1** — install, run your first model
2. **Ch 2** — understand what tokenizers do
3. **Ch 4** — understand embeddings (what Jarvis actually uses)

Then come back for Ch 3 (model selection) when you want to compare or swap models.

## How Jarvis Uses Hugging Face

| Component | HF Usage | Model / Library |
|-----------|----------|-----------------|
| Chunk embeddings | `SentenceTransformer.encode()` at index time | `all-MiniLM-L6-v2` |
| Query embeddings | Same model at search time | `all-MiniLM-L6-v2` |
| Cross-encoder reranking | `CrossEncoder` for precision reranking | `ms-marco-MiniLM-L-6-v2` |
| RAG evaluation & data management | `datasets` library for metrics + browsing | `eval_cli.py` |

All models run **locally** with `HF_HUB_OFFLINE=1` — no API calls to HF servers at runtime.

## Cross-References

- [RAG Architecture](../rag/rag-architecture.md) — how embeddings fit the pipeline
- [Hybrid Search & Reranking](../rag/hybrid-search-reranking.md) — cross-encoder details
- [Learning Roadmap — HF Track](../rag/ch8-learning-roadmap.md) — structured study plan with resources

---

## Beginner Guide: What Are Transformers?

### The Big Picture

**Transformers** is the name of a **neural network architecture** invented by Google in 2017 (the famous "Attention Is All You Need" paper). It's the foundation behind virtually every modern AI model:

```
GPT-4, ChatGPT       ← Transformer
Llama, Qwen, Gemma   ← Transformer
BERT, MiniLM          ← Transformer
Stable Diffusion      ← Uses Transformers internally
```

Before Transformers, AI processed text **one word at a time** (sequentially). Transformers process **all words at once** using a mechanism called "attention" — they can see relationships between any two words in a sentence regardless of distance. This made them dramatically better at understanding language.

### Is It Free?

**Yes, completely free and open source.** There are two things called "Hugging Face" to distinguish:

| | Hugging Face (the company) | `transformers` (the library) |
|-|---------------------------|------------------------------|
| **What** | A company that hosts models, datasets, and tools | A Python library (`pip install transformers`) |
| **Cost** | Hub is free for public models; paid tiers for private/enterprise | 100% free, Apache 2.0 open source |
| **Models** | Hosts 500,000+ models anyone can download | Loads those models with 3 lines of code |

**The models themselves** range from fully open (Llama, Qwen, Gemma, MiniLM — download and run forever, no API key, no internet needed) to restricted (some require agreeing to a license). Jarvis uses only **fully open, locally-runnable models**.

### The Transformers Library — What Are AutoModel, AutoTokenizer, Pipeline?

Think of it as three layers, from easiest to most control:

#### Layer 1: `pipeline` — One-Line AI (Easiest)

```python
from transformers import pipeline

# Sentiment analysis in one line:
classifier = pipeline("sentiment-analysis")
result = classifier("I love this RAG system!")
# → [{'label': 'POSITIVE', 'score': 0.9998}]

# Text generation:
generator = pipeline("text-generation", model="gpt2")
result = generator("Machine learning is", max_length=30)
# → [{'generated_text': 'Machine learning is a field of...'}]

# Question answering:
qa = pipeline("question-answering")
result = qa(question="What is RAG?", context="RAG stands for Retrieval-Augmented Generation...")
# → {'answer': 'Retrieval-Augmented Generation', 'score': 0.95}
```

`pipeline` hides all complexity. You say **what task** you want, it picks a model, tokenizes, runs inference, and formats the output. Great for prototyping.

#### Layer 2: `AutoTokenizer` — Turning Text into Numbers

Models don't understand text — they understand **numbers**. A tokenizer converts between the two:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

# Text → numbers (tokens):
tokens = tokenizer("Hello, how are you?")
# → {'input_ids': [101, 7592, 1010, 2129, 2024, 2017, 1029, 102],
#     'attention_mask': [1, 1, 1, 1, 1, 1, 1, 1]}

# Numbers → text:
text = tokenizer.decode([101, 7592, 1010, 2129, 2024, 2017, 1029, 102])
# → "[CLS] hello, how are you? [SEP]"
```

**Why "Auto"?** Each model has its own vocabulary and tokenization rules. `AutoTokenizer` reads the model's config and loads the right tokenizer automatically — you don't need to know the internals.

**Fun fact:** "Hello" might be one token, but "Ollama" might be split into `["Ol", "lama"]` — the tokenizer breaks unknown words into pieces it knows. This is why token count ≠ word count.

#### Layer 3: `AutoModel` — The Neural Network Itself

```python
from transformers import AutoModel, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModel.from_pretrained("bert-base-uncased")

# Tokenize, then feed to model:
inputs = tokenizer("What is RAG?", return_tensors="pt")
outputs = model(**inputs)

# outputs.last_hidden_state = a giant tensor of numbers
# Shape: [1, 6, 768] = 1 sentence, 6 tokens, 768-dimensional embedding per token
```

`AutoModel` gives you the **raw neural network output** — tensors (multi-dimensional arrays of numbers). You'd use this level when building custom pipelines, like Jarvis's embedding system.

**Why "Auto"?** There are hundreds of model architectures (BERT, GPT, T5, Llama...). `AutoModel` reads the config file and loads the right architecture class automatically.

#### How These Layers Stack

```
pipeline("sentiment-analysis")          ← Easiest: task in, answer out
    ├── AutoTokenizer (text → numbers)
    ├── AutoModel (numbers → neural output)
    └── Post-processing (output → "POSITIVE 99.8%")
```

### Sentence Transformers — What Jarvis Actually Uses

Jarvis doesn't use the raw `transformers` library directly. It uses **Sentence Transformers** (`pip install sentence-transformers`), which is a **wrapper** built on top of Transformers specifically for computing **embeddings** (meaning-vectors):

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, runs on CPU

# One line to get an embedding:
embedding = model.encode("What is RAG?")
# → array of 384 numbers representing the meaning

# Compare two texts:
emb1 = model.encode("machine learning")
emb2 = model.encode("artificial intelligence")
emb3 = model.encode("banana smoothie")

from numpy import dot
from numpy.linalg import norm

similarity = lambda a, b: dot(a, b) / (norm(a) * norm(b))
print(similarity(emb1, emb2))  # → 0.72 (very similar!)
print(similarity(emb1, emb3))  # → 0.08 (unrelated)
```

**In Jarvis:** Every document chunk gets `model.encode(chunk_text)` at index time. Every search query gets `model.encode(query)` at search time. Qdrant finds the closest vectors. That's the entire retrieval pipeline.

### Quick Reference: When to Use What

| You want to... | Use |
|----------------|-----|
| Try AI on a task quickly | `pipeline("task-name")` |
| Understand how tokenization works | `AutoTokenizer` |
| Build a custom model pipeline | `AutoModel` |
| Compute text similarity / embeddings | `SentenceTransformer` (what Jarvis uses) |
| Re-rank search results by relevance | `CrossEncoder` (what Jarvis uses for reranking) |

## Suggested Learning Path

1. **Beginner:** Install `sentence-transformers`, encode two sentences, compute their similarity — see the numbers yourself
2. **Intermediate:** Compare models on MTEB, understand tokenization, try different pooling strategies
3. **Advanced:** Fine-tune embeddings on domain pairs, evaluate with BEIR, publish a model card

---

*Part of the [Jarvis Learning Series](../). See also: [RAG](../rag/), [LLM](../llm/), [Machine Learning](../machine-learning/)*
