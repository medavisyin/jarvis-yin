# Know-How: PDF Processing — pypdf & ReportLab

Jarvis works with PDFs in two directions: **reading** text in and **writing** briefings out. Two libraries cover those roles.

## Two PDF libraries, two purposes

| Library | Main job | Jarvis role |
|---------|----------|-------------|
| **pypdf** | **Read** PDFs, extract text (and basic manipulation) | Indexing pipelines |
| **ReportLab** | **Create** PDFs programmatically | Generating the briefing PDF layout |

## pypdf (reading)

**pypdf** reads PDF files and exposes page-level text extraction.

**Used in Jarvis by:** `index_briefing.py`, `index_custom.py` (and similar indexing flows).

### Simple API

```python
from pypdf import PdfReader

reader = PdfReader("ai-briefing.pdf")
for page in reader.pages:
    text = page.extract_text()
```

### Limitations

- **Scanned / image-only PDFs:** `extract_text()` cannot recover text from pure images; you need **OCR** (e.g. Tesseract, cloud OCR) for those.
- **Complex layouts:** Multi-column or heavily styled PDFs may produce jumbled text; you may need heuristics or different parsers for critical accuracy.

### Installation

```bash
pip install pypdf
```

Official project:

- [pypdf documentation](https://pypdf.readthedocs.io/)

## ReportLab (writing)

**ReportLab** builds PDFs from Python code: paragraphs, tables, images, headers/footers, page numbers, and custom canvases.

**Used in Jarvis by:** `scripts/output/briefing-template.py`.

### Capabilities (high level)

- Flowable text and styles (fonts, sizes, spacing)
- Tables and simple graphics
- **Unicode / CJK:** With **proper font registration** (TTF/OTF), Chinese and other scripts can render correctly; missing fonts produce gaps or tofu glyphs.

### Installation

```bash
pip install reportlab
```

Official docs:

- [ReportLab User Guide](https://www.reportlab.com/docs/reportlab-userguide.pdf)

## How Jarvis uses them

### `index_briefing.py`

Reads **`ai-briefing.pdf`**, splits content (for example on **numbered sections**), and produces **chunks** suitable for embedding and vector indexing.

### `index_custom.py`

Reads **personal PDF files**, extracts text per page, chunks, and feeds the same indexing path as other sources.

### `briefing-template.py`

Reads structured data (e.g. **`briefing-data.json`**) and generates **`ai-briefing.pdf`** with ReportLab—layout, typography, and any tables or sections your template defines.

```text
briefing-data.json  --ReportLab-->  ai-briefing.pdf
                         |
                         v
              index_briefing.py (pypdf read → chunks → embeddings)
```

## Practical checklist

- **Fonts:** For non-Latin text in ReportLab, confirm a font file is embedded/registered.
- **Extraction quality:** Spot-check `extract_text()` output before relying on chunk boundaries.
- **OCR:** If indexing yields empty text, the PDF may be image-based—switch strategy.

## Further reading

- [pypdf](https://pypdf.readthedocs.io/)
- [ReportLab](https://www.reportlab.com/)
