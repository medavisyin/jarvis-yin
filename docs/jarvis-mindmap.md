# Jarvis

## Design & Architecture
### System Architecture
- System context (C4)
- 5-layer architecture
- Data flow diagrams
- Deployment view
- Tech stack map
- Key design decisions
- Data model
- Port map
- Security model
### RAG Agent Design
- Auto-RAG engine
- SSE streaming
- Tool system
- Benchmarks

## Getting Started
### Setup Guide
- Install Python
- Install Ollama & models
- Run briefing pipeline
- Start servers
### Backend Overview
- Scripts reference
- API endpoints
- Configuration
- Troubleshooting

## User Guides
### Stock Usage Guide (中文)
- 关注列表
- 数据获取
- 分析报告
- ML预测
- 决策参考
### Stock Knowledge Guide (中文)
- A股基础
- K线与指标
- 基本面
- 情绪分析
- ML预测
### Telegram Bot Guide
- /fetch 抓取
- /search 搜索
- /ask 问答
- /stock 股票
### Git & GitHub Guide
- Git basics
- GitHub workflow
- Branch management

## Implementation
### Tech Stack Overview
### RAG System
- agent.py — Auto-RAG, SSE, tools
- search_ui.py — Search, Qdrant, Flask
- index_briefing.py
- index_confluence.py
- index_codebase.py
- index_custom.py
- reindex_all.py
- Learning Features — AI, English, AWS, Notes
- Global Settings — Audio language
### Briefing Pipeline
- Pipeline Orchestration
- Fetcher Pattern (16 scripts)
- World News (6 sources)
- Output Generation (PDF, Audio, Video)
- Topic Deduplication
### Stock Module
- Architecture & Anti-overfitting
- Configuration & Paths
- Data Layer (AKShare, Watchlist)
- Analysis Engines (TA, Fundamental, Sentiment)
- ML Pipeline (XGBoost, Walk-forward)
- Market Signals (Fear & Greed, VIX)
- Scanner (5000→100→30→0-5, DeepSeek Layer 3)
- LLM Synthesis
- API Routes

## Learning Tracks
### RAG (12 docs)
- Ch.1 RAG Concepts
- Ch.2 Architecture Assessment
- Ch.3 Vector Search
- Ch.4 Framework Comparison
- Ch.5 ML Roadmap
- Ch.6 Advanced Techniques
- Ch.7 ML for Retrieval
- Ch.8 Learning Roadmap
- Ch.9 Evaluation
- RAG Architecture Guide
- Qdrant Vector DB Guide
- Hybrid Search Guide
### Machine Learning (5 docs)
- Ch.1 ML Fundamentals
- Ch.2 Training & Evaluation
- Ch.3 Data Preprocessing
- XGBoost Guide
- Feature Engineering Guide
### Hugging Face (4 docs)
- Ch.1 Getting Started
- Ch.2 Tokenization
- Ch.3 Model Selection
- Sentence Transformers Guide
### LLM (2 docs)
- Ollama Local LLM
- Prompt Engineering
### Python Web (3 docs)
- Flask Web Server
- Async & Concurrency
- Testing Python Apps
### Data Acquisition (3 docs)
- Playwright Scraping
- PDF Processing
- Edge TTS Speech
### DevOps & Tooling
- Git
- PowerShell
- Atlassian
### Stock Investing 股票投资 (10 chapters)
- Ch.1 市场基础
- Ch.2 读懂财报
- Ch.3 估值方法
- Ch.4 技术分析
- Ch.5 风险管理
- Ch.6 策略体系
- Ch.7 量化与ML
- Ch.8 Jarvis实战
- Ch.9 增强路线图
- Ch.10 A股深度解析

## Plans & Roadmaps
### Enhancement Plan (Active)
- Tier 0 Bug Fixes
- Tier 1 Testing & Scheduling
- Tier 2 Embeddings & Backtesting
- Tier 3 Docker & CI/CD
- Tier 4 New Agents
- Tier 5 Advanced Features
### Stock Prediction Plan (Completed)
### Advanced RAG Plan (Completed)
### ML Integration Plan (Phase 1-2 Done)
### Obsidian Enhancement Plan
- Canvas boards
- Tags & frontmatter

## Other
### AWS Cert Roadmap
- AIF-C01 Learning Path
### Session Memory
- Stock review notes
