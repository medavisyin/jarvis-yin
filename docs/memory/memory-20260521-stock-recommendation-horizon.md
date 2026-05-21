# Memory: Stock Recommendation Time Horizons and Direct Theme Recommendations

**Generated**: 2026-05-21 10:15
**Last updated**: 2026-05-21 10:15
**Project**: c:\jarvis
**Focus**: Update short-term and long-term stock scanners to support user-preferred time horizons and include direct stock recommendations in investment themes.

---

## Goal & Scope (required)

The user requested specific modifications to both short-term and long-term stock recommendation systems:
1. **Short-Term Recommendations**: Shift from generic timing to a specific holding window of **2 weeks to 2-3 months** with a **10%+ profit target**, adding deeper analysis (K-line volume-price correlation, fund divergence) when DeepSeek is enabled.
2. **Long-Term Recommendations**: Extend prediction horizon up to **6 months to 1 year** and add **direct stock recommendations** (대표개개/대표个股) underneath each long-term investment theme, which are especially enabled and high-quality when DeepSeek is enabled.

---

## Key Decisions (required)

1. **Prompt Alignment**: Instead of adding new fields to JSON outputs that could break frontend API parsing, we seamlessly integrated the target horizons (2 weeks to 2-3 months for short term; 6 months to 1 year for long term) and profit targets (10%+) directly into the LLM system prompts. This forces the model to factor these constraints into its scoring, reasoning, risks, and trading strategies.
2. **Theme Direct Stocks Matching**: In `long_term_scanner.py`, Step 3 (`_llm_theme_analysis`) now outputs a `recommended_stocks` list of objects. In Step 4, we extract these stocks first, clean/validate their symbols to make sure they are valid 6-digit A-share codes, and inject them as high-priority candidates to be assessed and filtered alongside sector-matched stocks. This resolves the limitation of relying purely on sector substring matching.
3. **Frontend Integration**: Modified `index.html`'s JS rendering loop for long-term themes to check for the presence of `recommended_stocks` and render them directly beneath each theme block in a stylized green/blue card layout.

---

## Confirmed Assumptions (required)

- Standard 6-digit A-share symbols (e.g. `600519`) are expected and used throughout the system. Suffixes (e.g. `.SH`, `SZ`) are cleaned during mapping.
- DeepSeek's powerful reasoning capability (`deepseek-v4-pro`) is ideal for both deep short-term quantitative and long-term qualitative macro A-share analysis.

---

## Key Discoveries (required)

- The short-term scanner's local prompt previously didn't instruct on any specific holding period or profit target, leading to generic "now buy" judgments.
- The long-term scanner's mapping was strictly reliant on substring matching between hot sectors and theme industries, making it prone to missing prime industry leaders. Directly injecting the LLM's recommended theme stocks as candidates dramatically enhances the selection pool.

---

## Runtime Evidence (include when relevant)

- Both modified Python scripts were compiled successfully using `py_compile` with zero syntax errors.
- Linter checks (`ReadLints`) returned clean.

---

## Current State (required)

- **Completed**: Short-term prompts (`scanner.py`) updated with 2 weeks to 2-3 months target horizon and 10%+ profit expectations, including deep-dive analysis guidelines. Completed code review fixes for conditional DeepSeek gating, type validation, and PDF formatting.
- **Completed**: Long-term scanner (`long_term_scanner.py`) updated to support up to 6 months to 1 year horizons, and direct stock recommendations under investment themes. Done code review fixes.
- **Completed**: Frontend `index.html` updated to render direct stock recommendations under each long-term theme block. Added XSS escaping.
- **Completed**: All changes verified, python compiled successfully, import tests passed. Code review loop closed and user accepted current state.

---

## Next Steps (required)

1. **New Feature Initialization**: Define and design the "Mid-day/Overnight Speculative Stock Scanner" (超短线午盘/隔夜套利策略).
2. [ ] Research data availability during the A-share mid-day break (11:30 - 13:00) for morning-session momentum analysis.
3. [ ] Propose and brainstorm technical architecture and metrics for 12:30/午盘 scanning.

---

## References (required)

- `scripts/stock/scanner.py` -- Short-term AI stock scanner
- `scripts/stock/long_term_scanner.py` -- Long-term AI stock scanner and trend analyzer
- `scripts/rag/templates/index.html` -- Frontend UI template with long-term rendering logic
