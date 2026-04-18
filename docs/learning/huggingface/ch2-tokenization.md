# Chapter 2: Tokenization

**Track:** Hugging Face learning  
**Navigation:** [Previous: Chapter 1 — Getting started](ch1-getting-started.md) · [Next: Chapter 3 — Model selection](ch3-model-selection.md)

---

## Why Tokenization Matters

Neural networks do not read letters or words the way humans do. They operate on **numbers**: vectors, matrices, and integer IDs that index rows in embedding tables. **Tokenization** is the bridge that turns raw text into those integers (and sometimes into byte-level or subword units first).

If you tokenize incorrectly, use the wrong tokenizer for a checkpoint, or mishandle padding, the model receives **misaligned or meaningless inputs**. A single off-by-one boundary can shift every subsequent position. Treat tokenization as part of your **model contract**: same vocabulary, same rules, same special tokens as the model was trained with.

Downstream, `input_ids` has shape `(batch_size, sequence_length)`. Each integer is looked up in an embedding matrix so the network can mix information across positions. Whatever you put in that tensor is what the model “reads”—there is no hidden recovery of the original string if IDs are wrong.

---

## Word-Level vs Subword Tokenization

**Word-level** tokenization splits on whitespace (and maybe punctuation) so each word type gets one ID. That sounds simple, but it breaks down quickly:

- **Out-of-vocabulary (OOV) words:** Anything not seen during vocabulary construction becomes an unknown token, so "Covid-19" or a rare surname may collapse to a single generic symbol and lose detail.
- **Huge vocabulary:** To cover many languages and domains, you need millions of word types, which is heavy for memory and training.
- **Morphology:** "run", "runs", "running", "runner" are unrelated IDs even though they share structure.

**Subword** tokenizers split rare or long words into **shorter pieces** that appear often in the corpus. Unknown words become sequences of **known** pieces instead of one unknown blob.

Example (conceptual splits; real pieces depend on the trained merges):

- `"unhappiness"` → `["un", "happiness"]`
- `"unhappiness"` → `["un", "happi", "ness"]`

The model still sees integers, but those integers refer to reusable fragments, so **coverage** and **parameter efficiency** improve together.

---

## Subword Algorithms

Three families dominate modern Hugging Face models. The goal is intuition, not the full merge-training loop.

**BPE (Byte Pair Encoding)**  
Start from characters or bytes; repeatedly merge the **most frequent adjacent pair** in the training text into a new symbol. GPT-style models often use BPE (sometimes with a byte-level base so every Unicode character is representable). New words decompose into frequent pairs.

**WordPiece**  
Similar merge idea, but scoring favors pairs that **raise the likelihood** of the training data (roughly: high mutual information). BERT’s WordPiece marks **word-internal** pieces with a `##` prefix so the model can tell “start of word” vs “continuation”.

**SentencePiece**  
Treats the input as a **raw stream** (including spaces) and learns subwords from that stream. No dependency on a specific pre-tokenizer for “words”, which helps multilingual and space-less scripts. T5 and many Llama-family tokenizers use SentencePiece (or compatible pipelines).

| Aspect | BPE (GPT-style) | WordPiece (BERT) | SentencePiece (T5, Llama, etc.) |
|--------|-----------------|------------------|----------------------------------|
| Typical unit building | Frequent pair merges | Likelihood-oriented merges | Unigram or BPE on stream |
| Word-internal hint | Often none (model learns) | `##` on continuations | Depends on model; may use special prefixes |
| Space handling | Often pre-tokenized (regex) | Often pre-tokenized | Can encode spaces as tokens |
| Common in | GPT-2, GPT-Neo, many decoder LMs | BERT, DistilBERT | T5, Llama, mT5 |

Many GPT-2–style tokenizers use **byte-level BPE**: the vocabulary is built so that **any UTF-8 byte sequence** can be represented. That avoids an unknown-character hole where rare emoji or symbols would otherwise map to a single unknown-token sink.

---

## Special Tokens

Checkpoints ship with a **vocabulary** and **reserved IDs** for control symbols. Typical roles:

- **`[CLS]`** — In BERT-style encoders, a classification token placed at the start of the sequence; its final hidden state is often used for sentence-level classification.
- **`[SEP]`** — Separates segments (e.g., question and passage in QA, or two sentences in NLI) so the model knows where one span ends and another begins.
- **`[PAD]`** — Padding filler so every sequence in a batch has the same length. It carries no semantic content; downstream layers should **ignore** padded positions (via an attention mask).
- **`[MASK]`** — Used in BERT’s masked language modeling pretraining; fill-in-the-blank style prediction during training. You usually do not feed random `[MASK]` tokens at inference unless you have a specific probing setup.
- **`[BOS]`** — Beginning-of-sequence marker where the architecture expects an explicit start (decoder-only or seq2seq models often use this or an equivalent).
- **`[EOS]`** — End-of-sequence marker; training teaches the model to stop or to separate concatenated examples.

Exact strings vary by model (`<s>`, `</s>`, `<pad>`, etc.). Always read `tokenizer.special_tokens_map` for your checkpoint.

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
print(tokenizer.special_tokens_map)
```

---

## Padding and Truncation

**Batching** stacks tensors along a batch dimension. That requires **identical sequence lengths** per batch (unless you use a rare variable-length path). Short sequences are **padded** by appending **`[PAD]`** (or the checkpoint’s configured pad symbol) until every row matches the target length. Long sequences are **truncated** so they do not exceed the model’s context or your chosen cap.

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

texts = [
    "Short.",
    "A much longer example that might exceed limits if we keep adding words " * 20,
]

encoded = tokenizer(
    texts,
    padding=True,
    truncation=True,
    max_length=512,
    return_tensors="pt",
)

print(encoded["input_ids"].shape)
print(encoded["attention_mask"].shape)
```

`max_length=512` matches `bert-base-uncased`’s typical cap; other models may use 1024, 2048, 8192, or more. Exceeding the checkpoint’s trained context causes errors or undefined behavior unless the model explicitly supports extension (e.g., some RoPE scaling setups).

---

## Attention Mask

The **attention mask** is a tensor of **1** and **0** (or bool) aligned with each input token position:

- **1** — Real token; attend normally.
- **0** — Padding position; should **not** influence self-attention scores (implementation scales or masks logits so padded keys are ignored).

Without it, padding rows would participate in softmax and **blur** representations.

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
batch = tokenizer(
    ["hi", "hello there"],
    padding=True,
    return_tensors="pt",
)

print(batch["attention_mask"])
```

When you call `model(**batch)`, Transformers passes the mask through to attention layers automatically.

---

## Token Count vs Word Count

**Word count** splits on whitespace (roughly). **Token count** depends on merges, language, casing, punctuation, and URLs. English often lands near **0.75–1.3 tokens per word** for subword models, but code, Chinese without spaces, or German compounds can **diverge sharply**.

Implications:

- LLM **context windows** are measured in **tokens**, not words. A “8k context” budget is eaten faster by verbose code or compact languages with long tokens.
- Pricing and rate limits for APIs are often **per token**.

Quick experiment:

```python
from transformers import AutoTokenizer

def show_lengths(model_id, samples):
    tok = AutoTokenizer.from_pretrained(model_id)
    for s in samples:
        ids = tok.encode(s, add_special_tokens=True)
        words = len(s.split())
        print(f"{model_id}\n  text: {s[:60]}{'...' if len(s) > 60 else ''}")
        print(f"  words: {words}, tokens: {len(ids)}\n")

samples = [
    "The quick brown fox jumps.",
    "Tokenization handles unknownwordsby splitting them.",
    "def fib(n):\n    return n if n < 2 else fib(n-1)+fib(n-2)",
]

show_lengths("gpt2", samples)
show_lengths("bert-base-uncased", samples)
```

Run this locally after `pip install transformers`. Compare the same string across models to see **tokenizer-dependent** lengths.

If you later study **chat templates** on the LLM track, remember that user-visible “messages” are still flattened to token IDs. The template chooses where `[BOS]`, `[EOS]`, and role markers go; the hard limit is always on **tokens**, not on characters or chat turns.

---

## Inspecting tokens

Seeing raw IDs is rarely enough during debugging. Use `convert_ids_to_tokens` to print the pieces the model actually consumes, and `decode` to verify lossless-ish round trips (normalization may change casing or whitespace for some checkpoints).

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
text = "Tokenization is not reversible word-for-word."
enc = tokenizer(text, add_special_tokens=True)

print(enc["input_ids"])
print(tokenizer.convert_ids_to_tokens(enc["input_ids"]))
print(tokenizer.decode(enc["input_ids"]))
```

For paired inputs (question, context), pass two strings to `tokenizer(text_a, text_b, ...)` so `[SEP]` placement matches pretraining.

---

## Practical Tips

- **Match tokenizer to checkpoint** — Use `AutoTokenizer.from_pretrained("same/repo/as/model")`. Mismatched vocabs produce wrong IDs even if tensor shapes line up.
- **Never mix tokenizers across pipelines** — Training with one BPE file and inferencing with another is a silent quality killer.
- **Confirm `model_max_length`** — `tokenizer.model_max_length` documents the architecture default; some checkpoints override config. For long documents, plan chunking or a long-context model.
- **Pad token on decoder-only models** — Some GPT-style configs lack a dedicated pad token; training scripts often set `pad_token` to `eos_token`. Know what your script did.
- **Decode to sanity-check** — `tokenizer.decode(ids)` catches accidental double-encoding or truncation mid-word before you spend GPU hours.

```python
from transformers import AutoTokenizer

name = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(name)
print(name, "model_max_length:", tokenizer.model_max_length)
```

---

## Summary

Tokenization maps text to the **integer space** models actually use. Subword methods (BPE, WordPiece, SentencePiece) trade vocabulary size for **coverage** and **fertility** (tokens per word). Special tokens structure tasks; **padding** enables batching; the **attention mask** keeps padding from polluting attention. Token counts govern **context limits** and cost—measure them on **your** data with **your** model’s tokenizer, and keep tokenizer and checkpoint **paired** for the entire lifecycle.

When something looks wrong in fine-tuning or generation, **inspect tokens first**: wrong repo, wrong `max_length`, or a missing pad token explains a surprising number of “the model is dumb” reports. Chapter 3 will connect these constraints to picking a model family that fits your sequence lengths and deployment constraints.

**Navigation:** [Previous: Chapter 1 — Getting started](ch1-getting-started.md) · [Next: Chapter 3 — Model selection](ch3-model-selection.md)
