package com.jarvis.ir.dict

data class DictRow(val word: String, val pos: String?, val translation: String)

data class DictHit(val word: String, val senses: List<Sense>)

class DictionaryRepository(
    private val lemma: LemmaMap,
    private val lookupExact: (String) -> DictRow?,
) {
    fun lookup(raw: String): DictHit? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        val stem = lemma.stem(trimmed)
        val row = lookupExact(stem) ?: lookupExact(trimmed.lowercase()) ?: return null
        val senses = SenseParser.parse(row.translation, row.pos)
        if (senses.isEmpty()) return null
        return DictHit(word = row.word, senses = senses)
    }
}
