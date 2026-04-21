# AWS Certified AI Practitioner (AIF-C01) — Learning Roadmap

> **Exam Code:** AIF-C01 | **Level:** Foundational | **Duration:** 90 min | **Questions:** 65 (50 scored + 15 unscored) | **Passing Score:** 700 / 1000

---

## Domain 1: Fundamentals of AI and ML (20%)

### Task 1.1 — Explain basic AI concepts and terminologies
- **AI vs ML vs Deep Learning vs GenAI:** Hierarchy of AI fields, how they relate and differ
- **Neural network basics:** Input/hidden/output layers, weights, activation functions
- **Types of inferencing:** Real-time vs batch, use cases for each
- **Key terms:** Training, inferencing, bias, fairness, fit (underfit/overfit/good fit)

### Task 1.2 — Identify practical use cases for AI
- **NLP use cases:** Amazon Comprehend, Amazon Lex, Amazon Transcribe, Amazon Translate
- **Computer vision use cases:** Amazon Rekognition, Amazon Textract
- **Recommendation systems:** Amazon Personalize
- **Fraud detection:** Amazon Fraud Detector
- **Forecasting:** Amazon Forecast
- **Search:** Amazon Kendra (intelligent enterprise search)

### Task 1.3 — Describe the ML development lifecycle
- **ML pipeline stages:** Data collection → preparation → feature engineering → training → evaluation → deployment → monitoring
- **Data preparation:** Labeling, cleaning, splitting (train/validation/test)
- **Feature engineering:** Transforming raw data into model-ready features
- **Model training and tuning:** Hyperparameters, epochs, learning rate
- **Evaluation metrics:** Accuracy, precision, recall, F1, AUC-ROC, RMSE, confusion matrix
- **MLOps:** Model monitoring, retraining triggers, data drift, concept drift

### Task 1.4 — Understand ML approaches
- **Supervised learning:** Classification (labels are categories) and regression (labels are numbers)
- **Unsupervised learning:** Clustering, anomaly detection, dimensionality reduction
- **Reinforcement learning:** Agent-environment interaction, rewards, RLHF
- **Self-supervised learning:** Pretext tasks, used for foundation model training
- **Semi-supervised learning:** Combining labeled and unlabeled data

---

## Domain 2: Fundamentals of Generative AI (24%)

### Task 2.1 — Explain basic concepts of GenAI
- **Generative AI terminology:** Token, chunking, embedding, vector, prompt, transformer, foundation model
- **Transformer architecture:** Attention mechanism, encoder-decoder, self-attention
- **Foundation model types:** LLM, diffusion model, multimodal model, GAN
- **GenAI use cases:** Text generation, image generation, code generation, summarization, chatbots, translation

### Task 2.2 — Understand GenAI capabilities and limitations
- **Capabilities:** Content creation, code generation, analysis, summarization, translation
- **Limitations:** Hallucination, bias amplification, context window limits, training data cutoff
- **Hallucination mitigation:** RAG, grounding, temperature control, guardrails
- **Responsible use:** Content filtering, human-in-the-loop, watermarking

### Task 2.3 — Describe AWS infrastructure for GenAI
- **Amazon Bedrock:** Managed access to foundation models via API (Claude, Titan, Llama, Jurassic, Stable Diffusion)
- **Bedrock features:** Agents, Knowledge Bases, Guardrails, Model Evaluation, Provisioned Throughput
- **Amazon SageMaker:** Full ML platform — build, train, deploy custom models
- **SageMaker features:** JumpStart, Canvas, Ground Truth, Clarify, Model Monitor, Endpoints
- **Amazon Q:** AI assistant for developers (Q Developer) and business (Q Business)
- **Amazon Nova:** AWS's own foundation model family
- **PartyRock:** No-code GenAI app builder on Bedrock

---

## Domain 3: Applications of Foundation Models (28%)

### Task 3.1 — Design considerations for FM applications
- **Model selection criteria:** Cost, modality, latency, multi-lingual, model size, customization, context window
- **Inference parameters:** Temperature, top-p, top-k, max tokens, stop sequences
- **Cost optimization:** Provisioned throughput, prompt caching, token budgeting
- **When to use which service:** Bedrock (managed FMs) vs SageMaker (custom ML) vs Q (assistants)

### Task 3.2 — Prompt engineering techniques
- **Zero-shot prompting:** No examples, just the instruction
- **Few-shot prompting:** Include examples in the prompt
- **Chain-of-thought (CoT):** "Think step by step" reasoning
- **System prompts:** Setting role, tone, constraints, output format
- **Prompt templates:** Reusable patterns with variable placeholders
- **Negative prompting:** Specifying what NOT to include
- **Prompt injection prevention:** Input validation, guardrails, output filtering

### Task 3.3 — Training and fine-tuning techniques
- **Customization preference order:** Prompt engineering → RAG → Fine-tuning → Continued pre-training
- **RAG architecture:** Retrieve relevant documents, augment prompt, generate answer
- **Fine-tuning:** Adapt FM to domain-specific data (Bedrock custom model training)
- **Continued pre-training:** Further train FM on domain corpus
- **Domain adaptation:** Transfer learning for specific industries
- **RLHF:** Reinforcement Learning from Human Feedback — aligning model behavior
- **Knowledge Bases for Bedrock:** Managed RAG with S3 data sources and vector store

### Task 3.4 — Evaluate FM performance
- **Text metrics:** ROUGE, BLEU, BERTScore, perplexity
- **Classification metrics:** Accuracy, precision, recall, F1, confusion matrix
- **Human evaluation:** Relevance, coherence, helpfulness, harmlessness
- **Bedrock Model Evaluation:** Built-in evaluation jobs, automatic and human-based
- **A/B testing:** Compare model versions in production
- **Benchmarking:** Compare against baseline models

---

## Domain 4: Guidelines for Responsible AI (14%)

### Task 4.1 — Develop responsible AI systems
- **FEPST framework:** Fairness, Explainability, Privacy, Safety, Transparency
- **Bias types:** Selection bias, measurement bias, confirmation bias, representation bias
- **Bias detection:** Amazon SageMaker Clarify — pre-training and post-training bias metrics
- **Explainability:** SageMaker Clarify SHAP values, feature importance
- **Human-in-the-loop:** Amazon A2I (Augmented AI) for review workflows

### Task 4.2 — Recognize AI safety and governance
- **Transparency principles:** Model cards, data sheets, documentation
- **Content safety:** Bedrock Guardrails — content filters, denied topics, word filters, PII redaction
- **Toxicity detection:** Content classification, profanity filters
- **Intellectual property:** Training data licensing, output attribution
- **Regulatory awareness:** GDPR, HIPAA, SOC 2, ISO 27001 considerations

### Task 4.3 — Evaluate responsible AI
- **Fairness metrics:** Disparate impact, equalized odds, demographic parity
- **Model monitoring:** Data drift detection, concept drift, performance degradation
- **Audit trails:** AWS CloudTrail for tracking API calls
- **AWS AI Service Cards:** Transparency documentation for AWS AI services

---

## Domain 5: Security, Compliance, and Governance (14%)

### Task 5.1 — Secure AI systems on AWS
- **IAM for AI:** Roles, policies, least-privilege access for Bedrock, SageMaker
- **Encryption:** AWS KMS (at rest), TLS (in transit), VPC endpoints
- **Data protection:** Amazon Macie (PII detection), AWS PrivateLink
- **Shared responsibility model:** AWS vs customer responsibilities for AI workloads
- **Prompt injection prevention:** Input sanitization, output validation, guardrails

### Task 5.2 — Data governance for AI
- **Data lineage:** Tracking data origin, transformations, usage
- **Data quality:** Validation, completeness, consistency, timeliness
- **Data privacy:** PII handling, data anonymization, consent management
- **Data lifecycle:** Collection → storage → processing → retention → deletion
- **AWS data services:** AWS Glue (ETL), AWS Lake Formation (data lake), AWS Data Exchange

### Task 5.3 — Compliance and regulation
- **AWS compliance programs:** SOC 1/2/3, ISO 27001, HIPAA, FedRAMP, GDPR
- **AWS Artifact:** Access compliance reports and agreements
- **AWS Audit Manager:** Continuous auditing and evidence collection
- **AWS Config:** Track resource configuration and compliance
- **AWS Trusted Advisor:** Best practice recommendations
- **Cost management:** AWS Budgets, Cost Explorer — monitor AI spending

---

## Exam Strategy & Key Points

### Top exam tips
- **Customization order:** Prompt Engineering → RAG → Fine-tuning → Pre-training (cheapest/fastest first)
- **Bedrock = managed FMs via API** (no infrastructure) | **SageMaker = full ML platform** (build/train/deploy)
- **Responsible AI = FEPST** (Fairness, Explainability, Privacy, Safety, Transparency)
- **Security = encrypt at rest (KMS) + in transit (TLS), IAM policies, Guardrails**
- **Domains 2+3 = 52% of exam** — focus on GenAI concepts and Bedrock/SageMaker
- Questions test *understanding of trade-offs* and *matching use cases to services* — not coding

### AWS services cheat sheet
| Service | One-liner |
|---------|-----------|
| Amazon Bedrock | Managed access to foundation models via API |
| Amazon SageMaker | Full ML platform: build, train, deploy, monitor |
| Amazon Q | AI assistant for developers and business users |
| Amazon Comprehend | NLP: sentiment, entities, key phrases, language detection |
| Amazon Lex | Conversational AI (chatbots, voice bots) |
| Amazon Polly | Text-to-speech |
| Amazon Rekognition | Image/video analysis (faces, objects, text, content moderation) |
| Amazon Textract | OCR + document analysis (forms, tables) |
| Amazon Transcribe | Speech-to-text |
| Amazon Translate | Neural machine translation |
| Amazon Personalize | Real-time personalization and recommendations |
| Amazon Fraud Detector | ML-based fraud detection |
| Amazon Kendra | Intelligent enterprise search |
| Amazon A2I | Human review workflows |
| SageMaker Clarify | Bias detection and explainability |
| SageMaker Ground Truth | Data labeling |
| Bedrock Guardrails | Content filtering, PII redaction, safety |
| Bedrock Knowledge Bases | Managed RAG with vector store |
