# Chapter 9: Evaluating RAG Systems

Retrieval-augmented generation connects search, prompting, and model behavior. Without evaluation, you are tuning blind: a new chunking rule, embedding model, or prompt tweak can quietly improve one failure mode while creating another. This chapter introduces practical metrics, how to build a small test set, and how to combine offline checks with signals from real users.

**Navigation:** Previous — [Chapter 8: Learning Roadmap](ch8-learning-roadmap.md)

---

## Why Evaluation Matters

You cannot improve reliably what you do not measure. RAG systems have many moving parts: document ingestion, cleaning, chunking, metadata, embedding models, vector indexes, filters, hybrid search, re-rankers, context assembly, system prompts, and the generator itself. A change in any layer can shift behavior in ways that are hard to predict from intuition alone.

Small changes often break things you did not expect. For example, switching to slightly longer chunks might improve recall for long policy documents but push more irrelevant text into the prompt, increasing hallucination risk. A new re-ranker might lift the right passage to rank two for most queries yet demote critical safety language for a narrow class of questions. Evaluation gives you a repeatable way to notice those regressions before they reach production.

Good evaluation also shortens feedback loops for your team. When everyone agrees on what “better” means—fewer wrong retrievals, fewer unsupported claims, faster answers—you can compare designs objectively instead of debating anecdotes.

Treat evaluation as a product habit, not a one-off science project. Capture a baseline when the system is “known good,” store the exact corpus snapshot and model versions with each run, and require at least one metric dashboard or report to move alongside every significant pull request.

---

## The Two Sides of RAG Evaluation

RAG quality is not a single number. It helps to split the problem into two complementary views.

**Retrieval quality** answers: did the system surface the right evidence? If retrieval fails, the model may still sound fluent by leaning on parametric knowledge or by guessing. In regulated or high-stakes settings, missing the canonical document is often worse than an awkward phrasing.

**Generation quality** answers: given whatever was retrieved, did the model produce a correct, useful, and well-grounded answer? Even perfect retrieval does not guarantee a good response if the prompt is confusing, the model over-condenses, or safety instructions are unclear.

In practice you evaluate both. Retrieval metrics judge the ranking step against labeled relevant documents. Generation metrics judge the final text against the question and, for faithfulness, against the retrieved context. Many teams start with retrieval because it is easier to label, then add generation checks as the product matures.

---

## Retrieval Metrics

Retrieval metrics assume you know which documents (or chunks) are relevant for each test question. That knowledge usually comes from human judgment or curated corpora. Once you have those labels, you can score how well your ranker orders candidates.

Most introductory examples use binary relevance (a chunk is either in the gold set or not). When your domain allows finer distinctions—partially on-topic versus fully authoritative—prefer graded labels and metrics like NDCG that respect those shades.

### Recall@K

**Recall@K** measures coverage: of all documents that should count as relevant for a query, how many appear in your top *K* results?

For a single query, let \(R\) be the set of relevant document IDs and \(S_K\) the set of IDs in your top *K* retrieved results. Then:

\[
\text{Recall@K} = \frac{|R \cap S_K|}{|R|}
\]

**Example:** Suppose there are four relevant chunks for a clinical policy question, and your system returns ten results. If three of the four relevant chunks appear somewhere in the top five positions, Recall@5 is \(3/4 = 0.75\).

**Why it matters for RAG:** If Recall@K is low, the model never sees key evidence, so no amount of clever prompting fixes the root cause. Recall@K is especially useful when multiple sources legitimately support an answer and you want to ensure none are systematically missing from the candidate set.

### Precision@K

**Precision@K** measures purity: of the *K* documents you retrieved, how many are actually relevant?

\[
\text{Precision@K} = \frac{|R \cap S_K|}{K}
\]

**Example:** Your top five results contain two relevant chunks and three irrelevant ones. Precision@5 is \(2/5 = 0.4\).

Precision@K highlights noise in the context window. Even when recall is acceptable, low precision means the model must sift through distractors, which can increase latency, cost, and hallucination risk.

Recall and precision trade off naturally as you widen or narrow retrieval. Reporting them together—or summarizing with an F-score at a fixed *K* after you understand the trade space—helps you avoid “fixing” recall by flooding the prompt with junk.

### MRR (Mean Reciprocal Rank)

**Mean Reciprocal Rank** focuses on how quickly the first relevant result appears. For one query, if the first relevant item appears at rank \(r\) (1-based), the reciprocal rank is \(1/r\). If none of the ranked results are relevant, the score is 0.

\[
\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \frac{1}{r_q}
\]

where \(Q\) is your set of test queries and \(r_q\) is the rank of the first relevant document for query \(q\).

**Example:** For three queries, the first relevant hit appears at ranks 1, 3, and 2. The reciprocal ranks are 1, \(1/3\), and \(1/2\). MRR is the average: \((1 + 1/3 + 1/2) / 3 \approx 0.61\).

MRR is valuable when users read results sequentially or when a single gold passage is enough to answer the question.

### NDCG (Normalized Discounted Cumulative Gain)

**NDCG** rewards putting highly relevant items near the top and can represent graded relevance (for example: not relevant, partially relevant, highly relevant) instead of a binary label.

For a ranked list, the **Discounted Cumulative Gain** at position \(p\) is:

\[
\text{DCG@p} = \sum_{i=1}^{p} \frac{2^{rel_i} - 1}{\log_2(i+1)}
\]

where \(rel_i\) is the relevance grade of the item at rank \(i\). **NDCG@p** divides DCG@p by the ideal DCG@p you would get if the list were sorted perfectly by relevance:

\[
\text{NDCG@p} = \frac{\text{DCG@p}}{\text{IDCG@p}}
\]

**Example (simplified binary case):** Relevant items contribute 1, irrelevant items 0. If the ideal top three are all relevant, IDCG@3 is computed from that perfect ordering. Your system’s DCG@3 sums contributions only where relevant items appear, with positions discounted by \(\log_2(i+1)\). If your relevant item sits at rank 3 instead of rank 1, NDCG@3 will be lower than the ideal even though Recall@3 might still be 1 when only one gold document exists.

NDCG is helpful when some documents are “more right” than others or when you care about the full shape of the ranking, not only the first hit.

### When to use which metric

| Scenario | Metric to emphasize |
|----------|---------------------|
| You must not miss any of several required sources | Recall@K (choose K large enough for your UI) |
| Context window is tight; noise hurts answers | Precision@K or NDCG |
| Users scan results top-down; first good hit is enough | MRR |
| Relevance is graded (partial vs full match) | NDCG |
| Comparing two embedding models quickly on the same index | Recall@K and MRR together |

Most teams report a small bundle—**Recall@10** for coverage, **MRR** for “time to first good evidence,” and **NDCG@10** when labels have nuance—rather than optimizing a single number in isolation.

---

## Generation Metrics

Generation evaluation asks whether the answer is correct, helpful, and grounded in the evidence you intended to use.

Citations are a UX feature, not a complete substitute for faithfulness checks. A model can paste plausible-looking references while still paraphrasing beyond what those passages support, or it can omit citations for the riskiest sentences. Your evaluation should look at alignment between claims in the answer and the union of retrieved texts, not only at bracketed URLs.

### Faithfulness

**Faithfulness** (sometimes called **groundedness**) means the answer stays within the information supported by the retrieved context. If the passages say the follow-up interval is six months, the model should not claim twelve months unless another retrieved passage supports that exception.

Faithfulness is not the same as factual truth in the world. A faithful answer can still be wrong if the corpus is outdated. What you measure here is consistency between the model output and the provided context, which is the part of RAG you control most directly at inference time.

### Answer Relevance

**Answer relevance** measures whether the response actually addresses the user’s question, independent of whether every detail is grounded. A perfectly cited passage that does not answer the asked question should score poorly on this axis.

This metric often requires judging semantic alignment between question and answer, sometimes with human raters or LLM-based judges. Treat automated judges as assistants: spot-check them and watch for bias toward verbose or confident wording.

### Context Relevance

**Context relevance** evaluates whether the retrieved chunks are appropriate inputs for the question. You might have faithful generation relative to bad chunks—meaning the model loyally summarizes irrelevant material.

Low context relevance usually points to retrieval, filters, or metadata bugs rather than the generator. Fixing it by stricter prompting alone rarely works if the wrong documents keep appearing.

### RAGAS framework

**RAGAS** is an open-source Python framework that packages common RAG evaluation ideas into reproducible scores, often using LLM-assisted judgments for answers and contexts alongside classic retrieval statistics where labels exist.

Typical RAGAS-style scores align with the concepts above: faithfulness to context, answer relevance, context precision, and context recall, among others. It is useful as a starting toolkit and for dashboards, but you should still validate on domain-specific test sets and human review, especially in healthcare or compliance settings where generic judges can miss subtle requirements.

---

## Building a Test Set

A **test set** is a labeled dataset you run repeatedly whenever you change retrieval or generation. Without it, you compare today’s memory to last month’s demo.

A minimal row usually contains:

- **Question** (or user utterance) exactly as the system receives it.
- **Expected answer** or **answer rubric** describing acceptable points (full prose answers are optional if rubrics are clear).
- **Relevant document IDs** (or chunk IDs) that a competent expert would want the retriever to surface.

You can extend rows with metadata: tenant, language, product area, difficulty, or “requires filter X” to catch regressions in specialized slices.

**Creating one manually:** Start with real or realistic questions from logs, support tickets, or clinician workflows (respecting privacy and consent). For each question, ask a subject-matter expert to mark which chunks in your index are authoritative. Keep a changelog when corpus versions shift so you do not relabel the same text twice under different IDs.

**Minimum size:** There is no magic number, but twenty carefully chosen queries teach you little about long tails; fifty to two hundred labeled questions often expose major issues in early systems. Balance breadth: include paraphrases, negations, multi-hop needs, rare terms, and ambiguous phrasing. Add “toxic pairs” where two diseases or drugs look similar in text retrieval.

When two experts disagree on relevance, resolve the definition of “relevant” before you chase model changes. Document tie-break rules (for example: prefer the newest guideline version unless the question names a year) so future labelers stay consistent.

Treat the test set like production code: version it, avoid leaking it into training prompts for the same model you evaluate, and expand it when new failure modes appear in production.

---

## A Simple Evaluation Pipeline

The following sketch wires together retrieval and a basic offline check. It assumes you already store labeled relevant IDs per query.

Before you interpret the printed table, fix random seeds where applicable, pin dependency versions, and log the embedding model name, index build timestamp, and prompt template identifier next to each run. Small nondeterminism in vector search or decoding makes numbers drift enough to confuse comparisons across days.

```python
import json
from typing import List, Set, Dict


def recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    top_k = set(retrieved[:k])
    hits = len(relevant & top_k)
    return hits / len(relevant) if relevant else 0.0


def run_retrieval(query: str) -> List[str]:
    raise NotImplementedError


def run_generation(query: str, contexts: List[str]) -> str:
    raise NotImplementedError


def main():
    rows: List[Dict] = json.load(open("rag_eval_set.json"))
    scores = []
    for row in rows:
        q = row["question"]
        relevant: Set[str] = set(row["relevant_doc_ids"])
        retrieved = run_retrieval(q)
        scores.append(recall_at_k(retrieved, relevant, k=5))
        contexts = [load_doc_text(doc_id) for doc_id in retrieved[:5]]
        answer = run_generation(q, contexts)
        print({"question": q, "recall@5": scores[-1], "answer": answer})
    print("mean recall@5", sum(scores) / len(scores))


def load_doc_text(doc_id: str) -> str:
    raise NotImplementedError


if __name__ == "__main__":
    main()
```

Faithfulness is intentionally left as a human or separate automated review step: experts read the retrieved passages alongside the answer, or you plug in a RAGAS-style judge with auditing. Starting simple avoids pretending you have calibrated automation before you do.

---

## Online Evaluation

Offline metrics on a static test set miss drift: new documents, new user phrasing, and seasonal topics. **Online evaluation** listens to what happens when real people use the system.

**Explicit feedback** such as thumbs up and down is a direct quality signal. In Jarvis-style assistants, lightweight voting after an answer helps teams prioritize failure clusters and validate fixes on live traffic patterns, provided you handle privacy and avoid incentivizing noisy clicks.

**Implicit signals** include which suggested sources users open (**click-through**), how long they spend reading, and whether they immediately reformulate the query. Sudden drops in click-through on citations may indicate retrieval regressions even when free-text answers look fine.

**Query abandonment**—users leaving without a successful follow-up—can flag confusion, latency, or trust issues. Pair abandonment traces with session context carefully; abandonment is noisy and not always about answer quality.

Online signals should complement, not replace, offline tests. They tell you where to look; labeled sets tell you whether you actually fixed the problem.

Where traffic allows, run controlled experiments: show half of users candidate set A versus B, or toggle a re-ranker for a cohort, and compare both human feedback and implicit signals. Always pair online experiments with guardrails so a retrieval regression cannot silently ship while headline engagement looks flat.

---

## Common Pitfalls

**Evaluating on training data** (or on examples that appear in few-shot prompts) inflates scores. Hold out a separate set and refresh it as the product evolves.

**Using only accuracy** on end-to-end QA can hide retrieval failure if the model answers from memorized knowledge. Separate retrieval metrics and groundedness checks surface the true bottleneck.

**Ignoring latency and cost** invites “improvements” that users hate in practice. A heavier re-ranker might lift NDCG slightly while pushing p95 latency past acceptable thresholds.

**Not testing edge cases**—empty retrieval, contradictory passages, multilingual queries, or garbled OCR—leaves you fragile. Build a small “stress rack” of adversarial rows and run it on every release candidate.

**Optimizing the metric instead of the user experience** is easy when incentives misalign. If engineers are rewarded only for Recall@10, someone may retrieve enormous chunks that technically contain the answer but read like noise to clinicians. Pair quantitative metrics with qualitative review sessions on sampled transcripts.

**Underpowered slices** hide systematic failures: a macro-average can look green while pediatric or billing-domain queries fail. Report metrics broken out by metadata tags, not only globally.

---

## Summary

RAG evaluation splits naturally into **retrieval** (did we fetch the right evidence?) and **generation** (did we answer well and stay grounded?). Retrieval metrics like **Recall@K**, **Precision@K**, **MRR**, and **NDCG** describe ranking behavior under different assumptions. Generation quality combines **faithfulness**, **answer relevance**, and **context relevance**, with frameworks like **RAGAS** offering packaged implementations you must still validate in your domain.

Build a **versioned test set** with questions, relevant IDs, and rubrics, then run a **repeatable pipeline** after each change. Layer **online feedback**—including Jarvis-style thumbs and behavioral signals—to catch drift. Avoid textbook mistakes: leakage from training data, over-trusting a single accuracy number, forgetting latency, and skipping edge cases. Measurement will not replace judgment, but it makes judgment scalable.
