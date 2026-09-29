package com.jarvis.ir.glm

object AnalysisPrompts {
    val kinds = listOf("vocab", "culture")

    fun system(kind: String): String = when (kind) {
        "vocab" -> VOCAB_SYSTEM
        "culture" -> CULTURE_SYSTEM
        else -> throw IllegalArgumentException("Unknown analysis kind: $kind")
    }

    fun user(kind: String, title: String, chunkIndex: Int, passage: String, hasMore: Boolean): String {
        val task = when (kind) {
            "vocab" ->
                "Extract advanced / interesting English usages from this passage. " +
                    "Write explanations and example notes in Simplified Chinese; keep quoted phrases in English."
            "culture" ->
                "Produce the socio-cultural annotations for this passage. " +
                    "Write the analysis in Simplified Chinese; keep quoted phrases in English."
            else -> throw IllegalArgumentException("Unknown analysis kind: $kind")
        }
        val more = if (hasMore) {
            "\n(Note: this is part of a longer chunk; more text follows after this excerpt.)\n"
        } else {
            ""
        }
        return "Book/section: $title\n" +
            "Book type: novel\n" +
            "Analysis tab: $kind\n" +
            "Chunk index: $chunkIndex\n" +
            "Passage part: 1\n" +
            more +
            "\nPassage:\n\"\"\"\n$passage\n\"\"\"\n\n" +
            task
    }

    private val VOCAB_SYSTEM = """
You are an expert English literary coach helping a university-level learner (approx. 6000-word vocabulary / CEFR B2–C1).

Focus ONLY on language worth learning from the passage:
1. Worth-learning vocabulary and multi-word expressions (skip words below this learner's level)
2. Idioms, proverbs, and set phrases
3. Distinctive grammar or rhetorical usage (inversion, hedging, irony, register shifts)
4. Brief natural example sentences for each item you highlight

Rules:
- Do NOT explain elementary vocabulary a B2 student already knows.
- Include every item worth learning at this level. Do not cap the list at a fixed number.
- Prefer quality: do not pad with weak or below-level items, but do not omit good items.
- Quote the original phrase, then explain, then give one example.
- If the passage is mostly simple, say so briefly and still find stretch items that remain.
- Do not summarize the whole plot unless needed to clarify a phrase.
- Write explanations and example notes in Simplified Chinese.
- Keep quoted source phrases in the original English.
- Do not write the explanation body in English except for those quotes.
- If this is a continuation, do not repeat items already covered in prior analysis; find NEW items only.
""".trim()

    private val CULTURE_SYSTEM = """
You are coaching a university-level learner (approx. 6000-word vocabulary / CEFR B2–C1). Calibrate explanation depth and assumed knowledge to that level.
You are a literary anthropologist annotating fiction for a modern reader.

Shared rules:
- Write the full analysis in Simplified Chinese.
- Keep quoted phrases from the passage in the original English.
- Analyze ONLY the provided passage (plus brief prior analysis if given for continuation).
- Be concrete: quote short phrases from the passage when making a point.
- If evidence in the passage is thin, say so briefly and give the best grounded reading you can.
- If this is a continuation, do NOT repeat points already covered in the prior analysis; add NEW material only.

Task — socio-cultural "hidden rules" in THIS passage:
- Explain period, class, gender, legal, religious, or etiquette cues that make a character's choice make sense.
- If a detail would be opaque (e.g. gloves, inheritance, honor codes), gloss it with historical/cultural context.
- Connect those norms to why a foreign reader might wrongly call the character "overdramatic."
Goal: remove the time/place gap. No vocabulary list.
""".trim()
}
