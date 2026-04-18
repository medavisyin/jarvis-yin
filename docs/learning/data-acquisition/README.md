# Data Acquisition — Scraping, Feeds & Document Processing

> Learning track for web scraping, RSS feed parsing, PDF generation/extraction,
> and the data pipeline patterns used in the Jarvis briefing system.

---

## What This Covers

- **Playwright** (browser automation, headless scraping, proxy/SOCKS5, anti-detection)
- **RSS & feeds** (`feedparser`, structured data extraction, deduplication)
- **PDF processing** (extraction with `pypdf`, generation with `ReportLab`, template-based reports)
- **Text-to-Speech** (`edge-tts`, ffmpeg, podcast-style audio generation)
- **Pipeline orchestration** (multi-source collection, merge/dedup, validation, retry)

## How Jarvis Uses These

| Component | Technology | Script |
|-----------|-----------|--------|
| AI news collection | Playwright scrapers (arXiv, HF, blogs, feeds) | `scripts/fetchers/ai/` |
| World news collection | Playwright + RSS for global/China sources | `scripts/fetchers/news/` |
| PDF briefing | ReportLab template-based generation | `scripts/output/briefing-template.py` |
| PDF reading | pypdf for knowledge indexing | `scripts/rag/index_custom.py` |
| Audio podcast | Edge-TTS + ffmpeg | `scripts/output/` |
| Pipeline runner | ThreadPoolExecutor, validation, merge | `scripts/pipeline/run-all-sources.py` |

## Related Jarvis Docs

- [Playwright Scraping](playwright-scraping.md) — setup, proxy, anti-detection
- [PyPDF & ReportLab](pypdf-reportlab.md) — PDF read/write patterns
- [Edge-TTS Speech](edge-tts-speech.md) — text-to-speech generation
- [Pipeline Orchestration](../../implementation/briefing-pipeline/pipeline-orchestration-impl.md) — multi-source workflow

## Suggested Learning Path

1. **Beginner:** Write a Playwright scraper, parse an RSS feed, extract text from a PDF
2. **Intermediate:** Handle anti-scraping measures, build a merge/dedup pipeline, generate a PDF report
3. **Advanced:** Orchestrate parallel fetchers with retry/backoff, build audio output, add validation gates

---

*Part of the [Jarvis Learning Series](../). See also: [Python Web](../python-web/), [RAG](../rag/)*
