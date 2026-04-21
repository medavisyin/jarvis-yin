# Reader knowledge scope

Use this file so the briefing and agent features stay aligned with **what you already know**, **what you are building toward**, and **your daily workflow**.

## Professional profile

| Field | Your notes |
|--------|------------|
| Name | Rong Yin |
| Primary role | Java backend developer |
| Domain | Medical imaging / medtech (DICOM, FHIR, radiology, PACS, clinical workflows) — but briefing focus should be **developer-centric** (tools, APIs, architecture, engineering tradeoffs), not medical/clinical inference |
| Stack | Java, Spring, Vaadin, FHIR, DICOM |
| Other technical areas | ~20 years software delivery: Java ecosystem, architecture, CI/CD, general backend and project lifecycle — **strong general engineering literacy** |
| Projects location | `D:\projects` — mostly Java projects |

## Team context

| Member | Role |
|--------|------|
| Raymond Shen | Team leader |
| Belen Liu | Developer |
| Eason Li | Developer |
| Johnny Yang | Developer |
| Rong Yin | Developer (you) |

- **Jira project:** Portal4med
- **Confluence spaces:** *(unknown — update when identified)*
- **Git repos:** All under `D:\projects`, configured in `agent.py` `REPO_CONFIG`

## Language & media

| Field | Your notes |
|--------|------------|
| Native / strongest language | 中文 (Chinese) — but input and data are mostly English |
| English (reading) | Can read and communicate; **lectures / fast spoken technical talks are hard to follow** — prefer clear, slower explanations in briefings |
| English (listening) | Same as above: conversational OK; dense native-speed technical audio without structure is tiring |
| Preferred briefing language | Chinese podcast narration with **technical tokens in English** (per skill rules) |

## AI / ML familiarity

- **Already comfortable with:** Everyday concepts: **LLM**, **context** / context window, using **AI coding tools (e.g. Cursor)**; prompting at a practical level. Basic understanding of **RAG**, **embedding**, and vector search through building and using Jarvis.
- **Growing but still learning:** Deeper patterns (retrieval design, hybrid search, re-ranking), training objectives (**RLHF**, distillation details), algorithm/math-heavy treatments, research paper jargon. Have completed most AI **terminology** and foundational **LLM/RAG** knowledge through Jarvis learning modes.
- **Have used lightly:** Cursor and similar tools for day-to-day development.
- **Want to avoid in explanations:** Unnecessary linear algebra unless a story truly depends on it — tie ideas to **systems, APIs, and engineering tradeoffs** first.
- **Self-assessment:** Still at a foundational level overall; learning steadily.

## Learning goals (6–12 months)

- **Primary aim:** Steadily **build and deepen AI knowledge** on top of a strong developer background — from vocabulary and trends to architecture and safe use in regulated/medical IT contexts.
- **Certification goal:** Pass the **AWS Certified AI Practitioner (AIF-C01)** exam — structured learning through Jarvis with teach/quiz modes, drawing from indexed study books (Tom Taulli guides, Slides v16) and structured notes. *(See `docs/aws-cert-learning-roadmap.md` for the exam roadmap.)*
- **Future ambition:** Apply AI/ML knowledge to **Chinese A-share stock prediction** — this requires accumulating knowledge in AI models, financial models, time-series analysis, sentiment analysis, and stock market fundamentals. *(See `docs/stock-prediction-plan.md` for the feature roadmap.)*

## Personal interests & motivations

- Strong interest in both **making money** and **AI knowledge** — Jarvis was built to serve both goals.
- Future feature: Chinese A-share individual stock prediction (data fetching, technical analysis, fundamental analysis, AI model prediction).
- Donor analysis (Cryos) is a personal tool already integrated into Jarvis.

## Daily routine & workflow

| Time | Activity |
|------|----------|
| ~09:00–10:00 | Run **Daily Fetch** to pull AI news, world news, commits, Jira reports |
| Morning | Review news briefing, check team's yesterday work (commits, Jira, wiki) |
| Throughout day | Use Jarvis chat for questions, Audio from Knowledge for learning, Explain This for deep dives |

## Network & infrastructure

| Setting | Value |
|---------|-------|
| Proxy | `socks5://localhost:10808` (hardcoded in pipeline scripts; can add additional proxies if needed) |
| Ollama | Local instance, default model `qwen3.5:4b`, fast model `qwen3:1.7b` |
| Qdrant | In-memory mode with JSON snapshot (`.rag-store.json`) |
| Reports root | `C:/reports/ai` |
| Jarvis root | `C:/jarvis` |

## Analyst note calibration

When the skill writes **Analyst notes**, it should pitch explanations here:

- **Assume I know:** Software engineering (Java, services, CI/CD, integration), general product delivery.
- **Spell out more:** New acronyms and techniques the first time they appear; **RAG**, evaluation methodology, training/fine-tuning subtleties — short analogy + "why it matters for industry" is better than textbook depth.
- **Perspective:** Always frame through a **developer lens** — how does this affect the tools I use, the code I write, the systems I build? Medical domain is my work context but I'm the engineer, not the clinician. Avoid framing me as someone doing medical inference or diagnosis.

---

*Edit this file anytime; the briefing skill and agent features read it for personalization.*
