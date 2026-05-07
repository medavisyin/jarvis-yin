# AWS Certified AI Practitioner (AIF-C01) — Learning Roadmap

> **Exam Code:** AIF-C01 | **Level:** Foundational | **Duration:** 90 min | **Questions:** 65 (50 scored + 15 unscored) | **Passing Score:** 700 / 1000

---

## Domain 1: Fundamentals of AI and ML (20%)

### Category: Artificial Intelligence
- **What is AI:** Field of computer science for systems that exhibit intelligent behavior
- **How AI Processes Information:** Data collection → algorithm selection → training → testing → deployment
- **AI Architecture Layers:** Data layer, Model layer, Application layer
- **Applications of AI:** Chatbots, IDP, APM, predictive maintenance, medical research, business analytics
- **Limitations of AI:** Data quality, computational costs, ethical concerns, human oversight needed

### Category: Basic AI Terminologies
- **Machine Learning:** Subset of AI — algorithms improve through experience and data
- **Deep Learning:** Subset of ML using multi-layer neural networks
- **LLM:** Large Language Model — deep learning on extensive text data with transformers
- **Neural Networks:** Computing systems inspired by biological neurons
- **NLP:** Natural Language Processing — extracting meaning from text
- **Computer Vision:** Interpreting visual information from images and videos
- **Speech Recognition:** Deciphering human speech using deep learning
- **Generative AI:** Producing original content from instructions

### Category: AI vs ML vs Deep Learning vs GenAI
- **Comparison:** Definition, types, data dependency, applications, examples
- **Hierarchy:** AI ⊃ ML ⊃ Deep Learning ⊃ GenAI

### Category: Understanding Foundation Models
- **Features:** Adaptability, general-purpose nature
- **Applications:** Language processing, visual comprehension, code generation
- **Examples:** BERT, GPT, Amazon Titan, Claude, Llama, Stable Diffusion
- **Challenges:** High resource demands, integration complexity, comprehension issues
- **AWS Support:** Amazon Bedrock, SageMaker JumpStart

### Category: AI Models — Types
- **Computer Vision:** Amazon Rekognition
- **NLP:** Amazon Comprehend, Translate, Lex, Polly
- **Speech:** Amazon Transcribe
- **Document Processing:** Amazon Textract
- **Recommendations & Forecasting:** Amazon Personalize, Forecast
- **Search:** Amazon Kendra
- **Custom ML:** Amazon SageMaker
- **Generative AI:** Amazon Bedrock, SageMaker JumpStart
- **Edge AI:** AWS IoT Greengrass ML Inference
- **Hybrid AI:** Amazon Neptune ML

### Category: Machine Learning
- **Types:** Supervised (classification, regression), unsupervised (clustering, anomaly detection), reinforcement learning
- **Evaluation Metrics:** Accuracy, precision, recall, F1, AUC-ROC, RMSE, confusion matrix

### Category: ML Pipeline with AWS Services
- **Data Collection:** Amazon S3, AWS Glue, Amazon RDS
- **EDA:** SageMaker Studio, Amazon Athena
- **Pre-processing:** AWS Glue, SageMaker Data Wrangler, SageMaker Processing
- **Feature Engineering:** SageMaker Feature Store, Data Wrangler
- **Model Training:** Amazon SageMaker, AWS Deep Learning AMIs
- **Hyperparameter Tuning:** SageMaker Automatic Model Tuning
- **Model Evaluation:** SageMaker Debugger, Model Monitor
- **Deployment:** SageMaker Endpoints, Amazon EKS
- **Monitoring:** Amazon CloudWatch, SageMaker Model Monitor

### Category: Fundamentals of MLOps
- **Key Practices:** Experimentation, pipeline automation, scalable systems, version control
- **CI/CD:** AWS CodePipeline, Jenkins
- **Model Registry:** SageMaker Model Registry
- **Retraining:** Automated via SageMaker Pipelines and Step Functions

### Category: Amazon SageMaker
- **Prepare:** Feature Store, Data Wrangler, Geospatial ML
- **Build:** Notebooks, JumpStart, Studio Lab
- **Train:** Model Training, Experiments (MLflow), HyperPod
- **Deploy:** Endpoints, Pipelines
- **End-to-End:** MLOps, Canvas (no-code), Studio (full IDE)
- **Governance:** Clarify, Ground Truth, Model Cards

---

## Domain 2: Fundamentals of Generative AI (24%)

### Category: Generative AI
- **Definition:** AI that creates original content from instructions
- **How It Works:** Foundation models trained on massive datasets
- **GenAI Model Types:** Diffusion, GANs, VAEs, Transformer-based
- **Transformer Concepts:** Self-attention, attention heads, encoder/decoder, tokenization, embeddings
- **Inference Parameters:** Temperature, top-p, top-k, max tokens, stop sequences
- **Benefits:** Accelerates research, enhances CX, optimizes processes, boosts productivity
- **Limitations:** Security, creativity constraints, cost, explainability, hallucination, context windows

### Category: GenAI Security Scoping Matrix
- **Scope 1:** Consumer App — use public GenAI service
- **Scope 2:** Enterprise App — third-party enterprise with GenAI
- **Scope 3:** Pre-trained Models — use existing FM via API
- **Scope 4:** Fine-tuned Models — refine FM with your data
- **Scope 5:** Self-trained Models — build from scratch
- **Security Disciplines:** Governance, legal/privacy, risk management, controls, resilience

### Category: Amazon SageMaker JumpStart
- **Features:** Foundation models, built-in algorithms, prebuilt solutions
- **Use Cases:** FM integration, LLMs, text classification, image generation, no-code solutions

### Category: Amazon Bedrock
- **Core:** Managed serverless access to FMs via unified API
- **Capabilities:** Model choice, customization, RAG, agents
- **Model States:** Active, Legacy, EOL
- **Bedrock Agents:** Autonomous agents with data access, task orchestration, code execution, memory
- **Bedrock Guardrails:** Content filters, denied topics, PII redaction, grounding checks
- **PartyRock:** No-code GenAI playground (chat, text, image)

### Category: Amazon Q
- **Q Business:** Enterprise data assistant — answers, summaries, content generation
- **Q Developer:** Coding, testing, error diagnosis, security assessments, AWS optimization
- **Integrations:** QuickSight, Connect, Supply Chain

---

## Domain 3: Applications of Foundation Models (28%)

### Category: Prompt Engineering
- **Anatomy:** Instruction, context, input data, output indicator
- **Techniques:** Zero-shot, few-shot, chain-of-thought, tree-of-thought, self-refine
- **Advanced:** Maieutic, complexity-based, generated knowledge, least-to-most, directional-stimulus
- **Security:** Prompt injection, jailbreaking, prompt leaking, model poisoning

### Category: Retrieval Augmented Generation (RAG)
- **How It Works:** Create external data → embed → retrieve → augment prompt → generate
- **Key Components:** Embedding models, vector databases, Knowledge Bases for Bedrock
- **Benefits:** Cost-effective, current information, enhanced trust, developer control

### Category: RLHF
- **Process:** Data collection → supervised fine-tuning → reward model → optimization
- **AWS Service:** SageMaker Ground Truth for data labeling
- **ROUGE Metric:** Recall-oriented text evaluation (ROUGE-N, ROUGE-L, ROUGE-S)

### Category: Model Selection & Design
- **Criteria:** Cost, modality, latency, multi-lingual, model size, customization, context window
- **Cost Optimization:** Provisioned throughput, prompt caching, token budgeting, model distillation

### Category: Training and Fine-tuning
- **Customization Order:** Prompt Engineering → RAG → Fine-tuning → Continued Pre-training
- **Transfer Learning:** Reuse pre-trained model features for new tasks

### Category: Evaluating FM Performance
- **Text Metrics:** ROUGE (recall), BLEU (precision), BERTScore (semantic), perplexity (confidence)
- **Classification:** Accuracy, precision, recall, F1, confusion matrix
- **Human Evaluation:** Relevance, coherence, helpfulness, harmlessness
- **Bedrock:** Model Evaluation with automatic and human-based methods

### Category: Responsible AI
- **FEPST:** Fairness, Explainability, Privacy, Safety, Transparency
- **Additional:** Controllability, veracity/robustness, governance
- **Bias Types:** Selection, measurement, confirmation, representation

### Category: Amazon SageMaker Clarify
- **Bias Detection:** Pre-training, post-training, runtime monitoring
- **Explainability:** SHAP values, feature importance
- **Fairness Metrics:** Disparate impact, equalized odds, demographic parity

### Category: Amazon SageMaker Model Monitor
- **Monitoring Types:** Data quality, model quality, bias drift, feature attribution drift
- **Model Cards:** Standardized model documentation for governance

---

## Domain 4: Guidelines for Responsible AI (14%)

### Category: Responsible AI Principles
- **FEPST Framework:** Fairness, Explainability, Privacy/Security, Safety, Transparency
- **Risks of GenAI:** Toxicity, hallucination, IP issues, bias amplification, privacy violations
- **Hallucination Mitigation:** RAG, lower temperature, guardrails, human review, citations

### Category: Bias Detection and Mitigation
- **SageMaker Clarify:** Pre-training, post-training, and runtime bias detection
- **SHAP Values:** Explain individual predictions with feature importance
- **Fairness Metrics:** Disparate impact, equalized odds, demographic parity

### Category: Human-in-the-Loop
- **Amazon A2I:** Human review workflows for low-confidence predictions
- **Integrations:** Textract, Rekognition, Comprehend, Transcribe, custom SageMaker

### Category: Safety and Governance
- **Bedrock Guardrails:** Content filters, denied topics, PII redaction, grounding checks
- **Model Cards:** Standardized model documentation
- **AI Service Cards:** Transparency documentation for AWS AI services

---

## Domain 5: Security, Compliance, and Governance (14%)

### Category: Security for AI Systems
- **IAM:** Least privilege, roles, policies for Bedrock and SageMaker
- **Encryption:** AWS KMS (at rest), TLS (in transit), VPC endpoints
- **Data Protection:** Amazon Macie (PII), AWS PrivateLink (private connectivity)
- **Shared Responsibility Model:** AWS secures infrastructure; customer secures data and access

### Category: Data Governance
- **Data Lifecycle:** Collection → storage → processing → retention → deletion
- **Data Quality:** Completeness, consistency, accuracy, timeliness, validity
- **Data Lineage:** Tracking origin, transformations, usage
- **AWS Services:** AWS Glue (ETL), Lake Formation (data lakes), Data Exchange

### Category: Compliance and Regulation
- **Standards:** HIPAA, GDPR, SOC 1/2/3, ISO 27001, FedRAMP
- **AWS Tools:** Artifact (reports), Audit Manager (continuous auditing), Config (compliance tracking)
- **Audit:** CloudTrail (API logs), Trusted Advisor (best practices)
- **Cost:** AWS Budgets, Cost Explorer

---

## Exam Strategy & Key Points

### Top Exam Tips
- **Customization order:** Prompt Engineering → RAG → Fine-tuning → Pre-training (cheapest first)
- **Bedrock = managed FMs via API** (no infrastructure) | **SageMaker = full ML platform**
- **Responsible AI = FEPST** (Fairness, Explainability, Privacy, Safety, Transparency)
- **Security = KMS + TLS + IAM + Guardrails**
- **Domains 2 + 3 = 52%** — focus on GenAI and Bedrock/SageMaker
- Questions test *understanding of trade-offs* and *matching use cases to services*

### AWS Services Cheat Sheet
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
