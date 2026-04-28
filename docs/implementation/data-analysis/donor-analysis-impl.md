---
tags:
  - implementation
  - data-analysis
  - donor-analysis
category: data-analysis
status: current
last-updated: 2026-04-28
---

# Donor Analysis

> **Category**: DATA ANALYSIS | **Source**: `scripts/rag/agent.py` (donor routes, `_score_donor`), `scripts/tools/parse-cryos-donors.py`

## Overview

**parse-cryos-donors.py** turns a saved Cryos International search-results HTML page into structured JSON (per-donor fields, stock/MOT lines, profile URLs) and optionally **embeds donor text into the local RAG snapshot** (`SentenceTransformer` + `SNAPSHOT_PATH`). **agent.py** serves **REST APIs** to score donors against clinical-style weights, stream **SSE “AI reasoning”** over the top N via Ollama, and export a **ReportLab PDF** with ranked tables and criteria appendix.

## Architecture & Design

### System Context

```text
Cryos HTML ──► parse-cryos-donors.py ──► REPORTS_ROOT/{date}/cryos-donors.json
                              │
                              └──► RAG snapshot (item_type: donor_profile)

cryos-donors.json ──► GET /api/donor-analysis?recipient_cmv=
              ──► POST /api/donor-analysis/ai-reason (SSE)
              ──► POST /api/donor-analysis/pdf
```

### Data Flow

1. **Parse**: BeautifulSoup selects `[class*='filter-page-info-card']`, dedupes by `name=` query param, maps `KNOWN_KEYS` labels to snake_case fields, extracts `stock` array from `MOT*` tokens (`parse-cryos-donors.py` `run`).
2. **Persist**: Writes `OUTPUT_FILE = Path(REPORTS_ROOT) / TODAY / "cryos-donors.json"`.
3. **RAG**: `index_to_rag` builds text from donor properties + stock lines, skips duplicates by title `Cryos Donor {id}`, appends points to snapshot (`parse-cryos-donors.py` 199+).
4. **Score**: For each donor dict, `_score_donor` computes weighted components summing to **100** (`agent.py` 5475–5552).
5. **AI reason**: Top `top_n` donors serialized into prompt; `POST` to `{OLLAMA_HOST}/api/chat` with `OLLAMA_MODEL`, stream JSON lines as SSE `data: {...}` (`api_donor_ai_reason` 5650–5685).
6. **PDF**: ReportLab `SimpleDocTemplate`, optional `STSong-Light` for Chinese, table with hyperlink Paragraphs to Cryos profile URLs (`api_donor_analysis_pdf` 5716–5833).

### Key Design Decisions

- **CMV gating**: For `recipient_cmv=negative`, CMV match contributes 20 only if donor status contains `"neg"` (`_score_donor` 5497–5502).
- **Sperm quality**: MOT tier caps + IUI bonus capped into 30-point bucket (`5479–5495`).
- **Stock availability**: Sums integers parsed from MOT `details` strings for vial counts (`5508–5521`).
- **Data discipline**: AI prompt instructs not to invent data (`5639–5647`).

## Implementation Details

### Core Components

| Piece | Location | Role |
|-------|----------|------|
| `_score_donor` | `agent.py` ~5475 | Deterministic scoring breakdown + `total`. |
| `api_donor_analysis` | `agent.py` ~5555 | Load latest `cryos-donors.json`, attach `_scores`, sort. |
| `api_donor_ai_reason` | `agent.py` ~5594 | SSE stream from Ollama. |
| `api_donor_analysis_pdf` | `agent.py` ~5688 | ReportLab PDF path + `pdf_url` for toolbar fetch. |
| `parse-cryos-donors.run` | `scripts/tools/parse-cryos-donors.py` | HTML → JSON + RAG. |
| UI hooks | `agent.py` ~7040, 7346+, 8292+ | Modal, `loadDonorAnalysis`, table render. |

### API Surface

- `GET /api/donor-analysis?recipient_cmv=` — JSON `{ donors, count, source_file, scoring_weights }`.
- `POST /api/donor-analysis/ai-reason` — body: `top_n`, `recipient_cmv`; `text/event-stream` tokens.
- `POST /api/donor-analysis/pdf` — body: `top_n`, `recipient_cmv`, `reason_text`, `language` (`zh`/`en`); returns `pdf_path`, `pdf_url`.

### Configuration

- `REPORTS_ROOT` from `scripts/config` (imported in parse script via `sys.path`).
- `OLLAMA_HOST`, `OLLAMA_MODEL` (used in donor SSE route; same module as main agent).
- `SNAPSHOT_PATH`, `COLLECTION`, `VECTOR_SIZE` for donor RAG indexing (`parse-cryos-donors.py` 31–33).

### Error Handling & Edge Cases

- Missing JSON: **404** with message to run `parse-cryos-donors.py` first (`api_donor_analysis` 5566–5567).
- ReportLab missing: **500** `reportlab not installed` (`5719–5722`).
- RAG: graceful skip if `sentence_transformers` import fails (`parse-cryos-donors.py` 203–207).

## Code Walkthrough

- **Scoring weights (implementation)**

```5475:5552:scripts/rag/agent.py
def _score_donor(donor: dict, recipient_cmv: str = "negative") -> dict:
    """Score a donor based on clinical criteria. Returns score breakdown."""
    scores = {}
    total = 0.0
    ...
    scores["sperm_quality"] = round(min(mot_score, 3.5) / 3.5 * 30, 1)
    ...
    if recipient_cmv == "negative":
        scores["cmv_match"] = 20.0 if "neg" in cmv else 0.0
    ...
    scores["total"] = round(total, 1)
    return scores
```

- **SSE generation**

```5650:5678:scripts/rag/agent.py
    def generate():
        import requests as req
        try:
            resp = req.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a clinical donor analysis expert. Be thorough and precise."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "think": False,
                    "options": {"num_predict": 8192, "temperature": 0.3},
                },
                stream=True, timeout=600,
            )
            full_text = ""
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            full_text += token
                            yield f"data: {json.dumps({'type':'token','content':token})}\n\n"
```

- **Card extraction**

```128:162:scripts/tools/parse-cryos-donors.py
    for card in cards:
        link = card.find("a", href=re.compile(r"donor-profile"))
        if not link:
            continue
        ...
        while i < len(text_parts):
            low = text_parts[i].lower()
            if low in KNOWN_KEYS and i + 1 < len(text_parts):
                key = re.sub(r'[^a-z0-9_]', '_', low).strip('_')
                val = text_parts[i + 1]
                if val.lower() not in KNOWN_KEYS and val not in (
                    "Buy now", "Reserve for later", "Price coming soon",
                    "View more on profile"
                ):
                    donor[key] = val
                i += 2
            else:
                i += 1
```

## Improvement Ideas

### Short-term

- Persist last AI `reason_text` server-side for PDF regeneration without client resend.

### Medium-term

- Multi-bank comparison: generalize parser/score for non-Cryos exports with pluggable field maps.

### Long-term

- Recipient preference learning (weight vector from feedback); automated recommendation policies with explainability logs.

## References

- `scripts/rag/agent.py` (donor section ~5471–5837)
- `scripts/tools/parse-cryos-donors.py`
- `scripts/config.py` (`REPORTS_ROOT`, `SNAPSHOT_PATH`)
