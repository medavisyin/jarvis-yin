# Chapter 1: Getting Started with Hugging Face

This chapter is for readers who have never used Hugging Face or the Transformers library before. You will learn what pre-trained models are, how to install the tooling, run your first inference, read model names, load models explicitly, tell inference apart from training, work offline, and try a few tiny experiments.

---

## What Does "Pre-trained" Mean?

Training a large language model from scratch means exposing a neural network to enormous amounts of text over many compute steps so it learns statistical patterns of language: grammar, facts, style, and task-relevant signals. That process typically requires specialized hardware, long wall-clock time, and budgets that can reach millions of dollars for the largest systems. Most individuals and teams never train a foundation model from zero.

A **pre-trained** model is one that someone else already trained on large data and published. You download the weights (the learned parameters) and reuse them. Your job becomes choosing the right model, loading it, and either running inference (getting predictions) or further adapting it (fine-tuning), not inventing the base capability from scratch.

Think of it like hiring an experienced specialist versus training a new hire for years before they can contribute. Pre-training is the long apprenticeship; you start when the model already speaks the language of text.

Fine-tuning is still training, but it starts from pre-trained weights and updates them with a smaller, task-specific dataset. That is far cheaper than training from random initialization, yet it is not the same as pure inference. Throughout this learning track, focus first on loading and running published checkpoints; later chapters will revisit adaptation when it matters.

Public checkpoints vary in license and acceptable use. Before you depend on a model in a product, read its model card on the Hugging Face Hub for limitations, training data caveats, and bias discussions.

---

## Setting Up Your Environment

Use a virtual environment so dependency versions stay isolated from other Python projects on your machine. If you are new to that workflow, create an environment, activate it, then install packages inside it.

Install the core libraries with pip. A typical starting set looks like this:

```bash
pip install transformers torch sentence-transformers
```

**Transformers** provides model implementations and high-level APIs. **Torch** (PyTorch) is the most common backend for running those models. **Sentence-transformers** builds on Transformers and is convenient for embeddings and semantic similarity.

If you do not have a CUDA-capable NVIDIA GPU, the default PyTorch wheels still work; they run on CPU. When you later install GPU-enabled Torch, follow the official matrix that matches your CUDA driver version; mismatched CUDA stacks are a frequent source of import errors.

Version skew happens. If examples fail with confusing attribute errors, check that your `transformers` and `torch` installs are reasonably current and installed into the same environment you are executing.

**CPU versus GPU:** You can learn and prototype entirely on CPU. Many small models and short texts run acceptably on a laptop processor. A GPU speeds up matrix math dramatically and is important for larger models, long sequences, batch processing, or training. Start on CPU if that is what you have; move to GPU when latency or throughput becomes painful.

Apple Silicon Macs can use MPS acceleration in PyTorch for some workloads; behavior and speedups vary by model and operation support.

**Cache directory:** When you call `from_pretrained` or use pipelines, weights and configuration files download into a local cache. On Linux and macOS this often lives under `~/.cache/huggingface`. On Windows, Hugging Face tooling also uses a user cache under your profile (for example under `AppData` paths managed by the hub client). You do not need to memorize the exact path; the libraries resolve it consistently.

You can redirect caches with environment variables such as `HF_HOME` when corporate policy or disk layout requires a different location. Teams sometimes centralize a read-only cache on a shared drive for air-gapped runners.

**Disk space:** Small classification or embedding models might need tens to hundreds of megabytes. Base-sized transformer checkpoints are often hundreds of megabytes to a few gigabytes. Large language models can require many gigabytes or tens of gigabytes per variant. Plan free space before downloading big checkpoints.

Download sizes are separate from RAM requirements. A model might fit on disk yet still be too large to load comfortably into memory without quantization or sharding strategies reserved for advanced topics.

---

## Your First Model in 60 Seconds

Here is a minimal sentiment analysis example:

```python
from transformers import pipeline

classifier = pipeline("sentiment-analysis")
result = classifier("I finally understand pipelines!")
print(result)
```

When you run this the first time, several things happen in order:

1. **Resolution:** The library picks a default model appropriate for the `sentiment-analysis` task.
2. **Download:** Weights, tokenizer files, and `config.json` are fetched into your cache if they are not already present.
3. **Tokenization:** Your string is split into subword tokens and converted to numeric IDs the model understands.
4. **Inference:** The neural network runs a forward pass and produces logits for each label (for example positive versus negative).
5. **Post-processing:** Logits become probabilities; the highest-scoring label is returned in a structured Python object.

Subsequent runs reuse the cached files, so startup is faster unless you clear the cache or change models.

You can pin a specific checkpoint with the `model=` argument even when using `pipeline`, which removes ambiguity about which default the library might choose in a future release.

If the first download feels slow, remember that you are copying a full checkpoint across the network once. Local runs afterward should avoid that cost.

The returned structure is a Python list of dictionaries for many pipelines. Keys usually include `label` and `score`, where `score` is a probability after softmax for classification heads.

---

## Understanding Model Names

Model identifiers on the Hugging Face Hub look like paths, for example `bert-base-uncased`. Reading them left to right:

- **Family or architecture:** `bert` refers to the BERT architecture (bidirectional encoder Transformer).
- **Size tier:** `base` indicates a mid-sized public BERT checkpoint (as opposed to `tiny`, `small`, or `large`).
- **Variant:** `uncased` means text was lowercased during pre-training; rules for normalization differ in `cased` variants.

Not every name follows the same pattern, but many combine **architecture**, **scale**, and **training or normalization details**.

**Model size versus quality versus speed (rule of thumb):**

| Scale (typical label) | Relative quality | Relative speed | Relative memory |
|----------------------|------------------|----------------|-------------------|
| Tiny / Mini          | Lower            | Fastest        | Lowest            |
| Small / Base         | Balanced         | Moderate       | Moderate          |
| Large                | Higher           | Slower         | Higher            |
| Very large / XL      | Highest          | Slowest        | Highest           |

Exact trade-offs depend on architecture, quantization, hardware, and batch size. Use the table as intuition, not a guarantee.

**Common families you will see:**

- **BERT and relatives (RoBERTa, DistilBERT):** Encoder-focused; strong for classification, token tagging, and sentence pair tasks.
- **GPT-style models:** Decoder-focused; strong for generation and continuation.
- **T5 and BART:** Encoder-decoder designs; strong for summarization, translation, and text-to-text formulations.
- **Llama and similar open LLMs:** Large decoder stacks for general chat and completion when you need broad capability.
- **MiniLM and other distilled models:** Smaller student models trained to mimic bigger teachers; good when you need speed and smaller downloads.

Organization namespaces on the Hub help you understand provenance. Names like `google/` or `FacebookAI/` indicate publisher accounts, not magical quality guarantees. Always read the model card.

Some repositories ship multiple weights formats. Transformers typically consumes PyTorch checkpoints with `*.bin` or `*.safetensors` files. The Hub page usually states which files are authoritative for Transformers users.

---

## Loading Models Explicitly

Pipelines hide details. In real projects you often load a tokenizer and model yourself:

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model_name = "distilbert-base-uncased-finetuned-sst-2-english"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
```

**Why "Auto":** Classes prefixed with `Auto` inspect `config.json` inside the checkpoint to determine which concrete architecture (BERT, DistilBERT, and so on) to instantiate. That means your code can stay stable when you swap compatible checkpoints.

`from_pretrained` downloads once, then reads from the local cache on later calls with the same identifier. You can pin revisions for reproducibility in serious workflows.

After loading, a minimal forward pass on token IDs returns logits. Training scripts add loss computation and optimizers; for now, treat logits as intermediate scores you can convert to probabilities with a softmax when the head is classification-shaped.

Tokenizer outputs include `input_ids`, `attention_mask`, and sometimes `token_type_ids` for sentence-pair models. Pipelines assemble these tensors for you; explicit code must keep keys aligned with what the model expects.

Trust boundaries matter on the Hub. Avoid `trust_remote_code=True` unless you understand why a repository requires custom Python and you trust the publisher. Default loading paths execute standard library implementations only.

---

## Inference vs Training

**Inference** means using existing weights without updating them. You pass inputs through the model, read outputs (class probabilities, generated tokens, embeddings), and stop. Memory use is dominated by the forward pass. This is what production services usually do at scale.

**Training** means computing a loss, running backward passes, and adjusting weights with an optimizer. It needs labeled or self-supervised data, more memory (activations for gradients unless you use tricks), and often GPUs.

**When you need each:** Use inference when a published model already does what you need, or after you have finished training elsewhere. Use training or fine-tuning when your domain, labels, or style are not represented well by off-the-shelf weights.

**What Jarvis does:** Jarvis uses inference only. All models are pre-trained (and possibly fine-tuned elsewhere). The application does not mutate model weights at runtime.

Batching is an inference concern too. Sending many inputs in one forward pass improves throughput when memory allows, but it does not imply training; gradients remain disabled unless you explicitly enable training mode and a backward step.

Evaluative metrics you see in blog posts often reflect specific benchmarks. Your application text distribution differs, so always measure on realistic inputs from your domain when choosing between two close checkpoints.

---

## Offline Mode

If you want to block network access after you have cached assets, set environment variables before starting Python:

```bash
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
```

On Linux or macOS, use `export` instead of `set`.

With these flags, the libraries refuse to reach the network and read only local caches. That fails if something is missing, which is the point: you discover gaps before you depend on connectivity.

**Workflow:** Download the models you need while online, run a smoke test, then enable offline mode in restricted environments.

**Why Jarvis uses this:** Some deployments must not phone home or depend on external availability. Offline flags make accidental network calls less likely and keep behavior predictable in locked-down networks.

If offline mode fails immediately, read the stack trace: missing tokenizer files, incomplete downloads, or mistyped model IDs are common causes. Fix the cache while online, verify the forward pass, then retry offline.

CI systems benefit from the same discipline. Pre-populate caches in an earlier pipeline stage so tests never depend on the public internet at test time.

---

## Quick Experiments

Try these three short exercises on your machine. Keep text small while learning.

**1. Sentiment analysis**

```python
from transformers import pipeline
p = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
print(p("This guide is clear and practical."))
print(p("I am frustrated and confused."))
```

**2. Text embedding similarity**

```python
from sentence_transformers import SentenceTransformer, util
model = SentenceTransformer("all-MiniLM-L6-v2")
a = model.encode("batch inference saves time", convert_to_tensor=True)
b = model.encode("processing many inputs together is efficient", convert_to_tensor=True)
c = model.encode("penguins cannot fly", convert_to_tensor=True)
print(float(util.cos_sim(a, b)))
print(float(util.cos_sim(a, c)))
```

Higher cosine similarity between vectors means the model places the sentences closer in semantic space.

**3. Fill-mask**

```python
from transformers import pipeline
fill = pipeline("fill-mask", model="bert-base-uncased")
print(fill("The capital of France is [MASK]."))
```

Masked language modeling scores candidate words at the placeholder.

If an exercise errors with out-of-memory on CPU, switch to a smaller model from the same family or shorten the input text. If downloads fail behind a corporate proxy, configure system proxy variables or ask IT for allowlisted domains used by the Hugging Face Hub.

As a stretch goal after the three exercises, open the Hub page for each model you used and read the model card top to bottom. Notice vocabulary size, training objective, and intended use cases; those facts explain behavior you observe locally.

---

## Summary

Pre-trained models let you stand on the work of large-scale training without paying its full cost. Install `transformers`, `torch`, and optionally `sentence-transformers`, expect downloads into a user cache, and remember that CPU is enough to begin. The `pipeline` API demonstrates end-to-end behavior: resolve a model, tokenize, infer, and format results. Model names encode architecture, scale, and variant. Explicit loading with `AutoTokenizer` and `AutoModel*` pairs clarity with flexibility. Inference uses fixed weights; training changes them; Jarvis stays on the inference side with pre-trained checkpoints. Offline environment variables ensure Hugging Face code uses only local files after you have populated the cache.

You are now equipped with a mental model of the lifecycle from Hub identifier to local tensors, and you know where to look when something fails: cache contents, environment flags, hardware fit, and the model card. Chapter 2 zooms into tokenization, the bridge between raw strings and numeric representations.

---

**Next:** [Chapter 2: Tokenization](ch2-tokenization.md)
