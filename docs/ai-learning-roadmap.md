# AI Learning Roadmap — LLM, RAG & AI Engineering

## Domain 1: LLM Foundations & Architecture

### Category: History of Language AI
- **Bag-of-Words**: Count-based text representation (1950s–2000s) — simple but no semantics
- **Word2Vec & Dense Embeddings**: Neural network–trained word vectors capturing meaning (2013)
- **Seq2Seq + Attention**: Encoder-decoder RNNs with attention mechanism (2014)
- **Transformer Architecture**: Self-attention only, parallel training, foundation of modern AI (2017)
- **BERT & GPT Era**: Pre-train → fine-tune paradigm, bidirectional vs autoregressive (2018–2020)
- **ChatGPT & Beyond**: RLHF alignment, instruction tuning, multimodal models (2022+)

### Category: Transformer Architecture
- **Self-Attention Mechanism**: Query/Key/Value computation, scaled dot-product attention
- **Multi-Head Attention**: Multiple parallel attention operations learning different relationships
- **Transformer Block**: FFN, layer norm, residual connections, positional encoding
- **KV Cache**: Caching keys/values for efficient autoregressive generation
- **Architecture Improvements**: GQA, RoPE, Flash Attention, Sliding Window, MoE

### Category: Model Types
- **Encoder-Only (BERT)**: Bidirectional, masked language modeling — for understanding tasks
- **Decoder-Only (GPT)**: Autoregressive, next-token prediction — for generation tasks
- **Encoder-Decoder (T5)**: Seq-to-seq — for translation, summarization
- **Open vs Proprietary Models**: Llama/Mistral/Qwen vs GPT-4/Claude/Gemini trade-offs

### Category: Foundation Models
- **Pretraining Pipeline**: Self-supervised learning on internet-scale data
- **Scaling Laws**: Chinchilla optimal — tokens should scale with parameters
- **Emergent Abilities**: Capabilities appearing only at sufficient scale (CoT, ICL)
- **Three-Phase Training**: Pretraining → SFT → Preference Alignment

### Category: Multimodal Models
- **CLIP**: Contrastive learning for text-image alignment, zero-shot classification
- **BLIP-2**: Bridge frozen image encoders to frozen LLMs via Q-Former
- **Vision-Language Models**: GPT-4V, Gemini, LLaVA — image understanding and generation

---

## Domain 2: Tokens, Embeddings & Representations

### Category: Tokenization
- **BPE (Byte Pair Encoding)**: Iterative merge of frequent character pairs — used by GPT, Llama
- **WordPiece & SentencePiece**: Alternatives for BERT and multilingual models
- **Vocabulary & Special Tokens**: CLS, SEP, EOS tokens and their roles
- **Multilingual Tokenization**: Non-English text uses more tokens — cost and context impact

### Category: Word & Text Embeddings
- **Static Embeddings (Word2Vec, GloVe)**: Fixed vectors per word, no context awareness
- **Contextualized Embeddings (BERT, ELMo)**: Different vectors based on surrounding context
- **Sentence Embeddings**: Single vector for entire text — mean pooling, CLS token
- **Similarity Metrics**: Cosine similarity, dot product, Euclidean distance

### Category: Embedding Models
- **Sentence-BERT (SBERT)**: Siamese networks for efficient sentence comparison
- **Contrastive Learning**: Positive/negative pairs, triplet loss, MNRL, InfoNCE
- **Domain Adaptation**: TSDAE, Augmented SBERT, GPL for custom embeddings
- **Embedding Model Selection**: MTEB leaderboard, dimension vs quality trade-offs

### Category: Dimensionality Reduction & Clustering
- **PCA, t-SNE, UMAP**: Techniques for visualization and preprocessing
- **HDBSCAN**: Density-based clustering without specifying K
- **BERTopic**: Modular topic modeling with embeddings + UMAP + HDBSCAN + c-TF-IDF

### Category: Text Classification
- **Embeddings + Classifier**: Logistic regression/SVM on sentence embeddings
- **Zero-Shot with LLMs**: Classify without training data using prompts or NLI models
- **Few-Shot with SetFit**: Strong results with 8–64 examples per class
- **Fine-Tuned BERT**: Best quality with labeled data, fast inference

---

## Domain 3: Prompt Engineering & Text Generation

### Category: Prompt Fundamentals
- **System vs User Prompts**: Role definition, constraints, output format
- **In-Context Learning**: Zero-shot, one-shot, few-shot — learning from prompt examples
- **Context Length & Efficiency**: Token limits, lost-in-the-middle effect, information placement

### Category: Advanced Prompting
- **Chain-of-Thought (CoT)**: Step-by-step reasoning for better accuracy
- **Self-Consistency**: Multiple reasoning paths + majority vote
- **Tree-of-Thought**: Explore and backtrack multiple reasoning branches
- **ReAct**: Interleave reasoning with tool-calling actions

### Category: Sampling & Decoding
- **Temperature**: Controls randomness — low for factual, high for creative
- **Top-p & Top-k**: Nucleus sampling and top-k filtering strategies
- **Structured Outputs**: JSON mode, function calling, grammar-based decoding
- **Beam Search**: Explore multiple generation paths for higher quality

### Category: Defensive Prompt Engineering
- **Prompt Injection & Jailbreaking**: Attack types and their mechanisms
- **Defense Strategies**: Input sanitization, instruction hierarchy, output filtering
- **Guardrails & Red Teaming**: Systematic protection and adversarial testing

### Category: LLM Chains & Memory
- **Chain Patterns**: Sequential, router, map-reduce for complex workflows
- **Conversation Memory**: Full history, windowed buffer, summary, vector-based retrieval
- **Frameworks**: LangChain, LlamaIndex abstractions and when (not) to use them

---

## Domain 4: RAG — Retrieval-Augmented Generation

### Category: RAG Fundamentals
- **RAG Pipeline**: Encode → Retrieve → Rerank → Augment → Generate
- **Why RAG**: Solve hallucination, outdated knowledge, and domain specificity
- **RAG vs Fine-Tuning vs Prompting**: Decision framework for when to use each
- **Mathematical Formulation**: P(y|x) ≈ Σ P(y|x,d_i)·P(d_i|x)

### Category: Retrieval Strategies
- **Dense Retrieval**: Embedding-based semantic search with vector databases
- **Sparse Retrieval (BM25)**: Keyword-based with TF-IDF scoring
- **Hybrid Search**: Dense + sparse fusion via RRF or weighted combination
- **Retrieval Metrics**: Recall@K, Precision@K, MRR, NDCG

### Category: Retrieval Optimization
- **Reranking**: Bi-encoder retrieval → cross-encoder reranking for precision
- **Query Rewriting**: Expansion, decomposition, HyDE, LLM-based reformulation
- **Chunking Strategies**: Fixed-size, paragraph, recursive, semantic chunking
- **Metadata Filtering**: Source, date, category filters for targeted retrieval

### Category: Advanced RAG
- **Naive → Advanced → Modular RAG**: Evolution of RAG paradigms
- **Self-RAG**: Model decides when to retrieve with special tokens
- **Corrective RAG (CRAG)**: Evaluate and correct bad retrievals with web fallback
- **Multi-Hop RAG**: Decompose complex questions into sequential sub-queries
- **Adaptive Retrieval**: Dynamic decision to retrieve, skip, or iterate

### Category: RAG Beyond Text
- **Multimodal RAG**: Retrieve and reason over images, tables, charts
- **Structured Data RAG**: Text-to-SQL, knowledge graphs, API-based retrieval

### Category: Agents & Tools
- **Agent Loop**: Observe → Think → Act → iterate until task complete
- **ReAct Pattern**: Reasoning + Action interleaving with tool calls
- **Tool Types**: Search, code interpreter, APIs, browser, file operations
- **Planning Strategies**: ReAct, plan-then-execute, iterative refinement, multi-agent
- **Agent Failure Modes**: Infinite loops, wrong tools, hallucinated tools, context overflow

---

## Domain 5: Fine-Tuning & Alignment

### Category: When & Why to Fine-Tune
- **Decision Framework**: When prompting isn't enough — style, format, domain
- **Fine-Tuning vs RAG**: RAG for knowledge, fine-tuning for behavior
- **Cost-Benefit Analysis**: Data requirements, compute cost, maintenance burden

### Category: Supervised Fine-Tuning (SFT)
- **Instruction Tuning**: Train on (instruction, response) pairs
- **Chat Templates**: Alpaca, ChatML — must match base model format
- **Dataset Quality**: Accuracy, diversity, consistency, deduplication, size (1K–50K)

### Category: Parameter-Efficient Fine-Tuning (PEFT)
- **LoRA**: Low-rank adapter matrices — train 0.1–1% of parameters
- **QLoRA**: LoRA + 4-bit quantization — fine-tune 7B on 24GB GPU
- **LoRA Configuration**: Rank, alpha, target modules, dropout tuning
- **Other PEFT**: Prefix tuning, adapter layers, IA3

### Category: Preference Alignment
- **RLHF**: SFT → Reward Model → PPO optimization (ChatGPT method)
- **DPO**: Direct preference optimization — simpler, no reward model needed
- **Preference Data**: Chosen/rejected pairs, quality gap importance
- **RLHF vs DPO**: Complexity, stability, memory, quality trade-offs

### Category: Dataset Engineering
- **Data Quality Hierarchy**: Accuracy > relevance > diversity > consistency > freshness
- **Data Acquisition**: Human annotation, synthetic generation, distillation, self-instruct
- **Data Processing Pipeline**: Inspect → deduplicate → clean → filter → format → validate

### Category: Model Merging
- **Merge Methods**: Linear interpolation, SLERP, TIES, DARE, model soup
- **Use Cases**: Combine coding + reasoning, multi-language, multi-task adapters

---

## Domain 6: AI Engineering & Production Systems

### Category: AI Engineering Architecture
- **Three-Layer Stack**: Application, Model, Infrastructure
- **Five-Step Pattern**: Context enhancement → Guardrails → Router/Gateway → Caching → Agents
- **Model Router**: Route by complexity — small model for simple, large for complex queries

### Category: Inference Optimization
- **Prefill vs Decode**: Compute-bound vs memory-bandwidth-bound phases
- **Quantization**: FP32 → FP16 → INT8 → INT4 — memory/speed/quality trade-offs
- **Speculative Decoding**: Draft with small model, verify with large model — no quality loss
- **GGUF Format**: Standard for local deployment with llama.cpp/Ollama

### Category: Serving & Deployment
- **Inference Engines**: vLLM, Ollama, llama.cpp, TGI, TensorRT-LLM compared
- **Deployment Patterns**: Online (sync), async, batch, edge/local
- **Local vs Cloud**: Privacy, cost, quality, latency, maintenance trade-offs

### Category: MLOps & LLMOps
- **MLOps Principles**: Reproducibility, automation, monitoring, versioning, testing
- **LLMOps Differences**: Prompt management, LLM-as-judge eval, inference cost focus
- **FTI Architecture**: Feature Pipeline → Training Pipeline → Inference Pipeline
- **Experiment Tracking**: Hyperparameters, metrics, data versions, checkpoints

### Category: Data Engineering for LLMs
- **Data Collection Pipeline**: Crawl → store raw → process → chunk → embed → index
- **Vector Database Operations**: Indexing, search, filtering, upsert, delete
- **Production Challenges**: Stale data, quality, deduplication, scale, privacy

### Category: Observability & Feedback Loops
- **Prompt Monitoring**: Track inputs, outputs, tokens, cost, latency
- **Feedback Types**: Explicit (ratings), implicit (behavior), conversational, comparative
- **Improvement Loop**: Deploy → Monitor → Feedback → Analyze → Improve → Deploy

---

## Domain 7: Evaluation, Safety & Responsible AI

### Category: Evaluation Methodology
- **Language Modeling Metrics**: Perplexity, cross entropy, bits-per-byte
- **Exact Metrics**: BLEU, ROUGE, BERTScore, Pass@k for code
- **Human Evaluation**: Absolute scoring, comparative evaluation, task completion

### Category: AI-as-a-Judge
- **Pointwise & Pairwise Evaluation**: Single-output scoring vs comparison
- **Judge Limitations**: Position bias, verbosity bias, self-preference, capability ceiling
- **Model Ranking**: Elo rating, Bradley-Terry, Swiss tournament systems

### Category: System Evaluation
- **RAG Evaluation**: Retrieval metrics + generation faithfulness + end-to-end correctness
- **Evaluation Frameworks**: RAGAS, TruLens, DeepEval for automated RAG evaluation
- **Benchmark Landscape**: MMLU, HumanEval, GSM8K, HELM, MT-Bench, Chatbot Arena, BEIR, MTEB

### Category: Responsible AI
- **Core Principles**: Fairness, transparency, accountability, privacy, safety, reliability
- **Bias Types**: Training data, selection, confirmation, reporting bias
- **Hallucination Types**: Factual, fabrication, inconsistency, unfaithful (RAG)
- **Mitigation**: RAG grounding, guardrails, red teaming, RLHF/DPO, Constitutional AI

### Category: Security & Compliance
- **Threat Model**: Prompt injection, data poisoning, model extraction, PII leakage
- **Data Privacy**: Training data filtering, local inference, retention policies, encryption
- **Content Safety**: Input classifiers → safety-tuned models → output classifiers → application rules

---

## Domain 8: AI Industry & Recent Developments

### Category: LLM Releases & Model Updates
- **New Model Releases**: Latest LLMs, benchmarks, capabilities, and comparisons
- **Open-Source Milestones**: Community-driven models, quantization breakthroughs
- **Model Architecture Trends**: Emerging architectures and training innovations

### Category: AI Agents & Coding Tools
- **Coding Assistants**: Copilot, Cursor, Claude Code, Devin — capabilities and workflows
- **Agent Frameworks**: MCP, tool calling, managed agents, SDKs
- **Autonomous Agents**: Long-running tasks, multi-step reasoning, permission models

### Category: RAG, Search & Information Retrieval
- **RAG Advances**: New retrieval techniques, embedding models, evaluation methods
- **Search Infrastructure**: Vector DB improvements, hybrid search, production patterns

### Category: AI Safety, Ethics & Regulation
- **Policy & Governance**: EU AI Act, industry standards, responsible AI initiatives
- **Safety Research**: Red teaming results, alignment breakthroughs, guardrail techniques

### Category: AI Infrastructure & Deployment
- **Hardware & Compute**: GPU trends, inference acceleration, cost optimization
- **Serving Frameworks**: New engines, optimization techniques, cloud offerings

### Category: AI Products & Applications
- **Industry Launches**: Major product releases, API updates, platform changes
- **Enterprise AI**: Adoption trends, integration patterns, ROI case studies
- **Startups & Funding**: Notable AI startups, acquisitions, partnerships

### Category: Research & Papers
- **Key Papers**: Significant publications, novel methods, benchmark results
- **Training Advances**: Pre-training, fine-tuning, and alignment breakthroughs
