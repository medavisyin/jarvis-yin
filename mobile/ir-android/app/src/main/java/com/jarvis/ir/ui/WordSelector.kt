package com.jarvis.ir.ui

data class WordHit(
    val word: String,
    val sentence: String,
    val start: Int = 0,
    val end: Int = 0,
)

object WordSelector {
    fun at(text: String, index: Int): WordHit? {
        if (index < 0 || index >= text.length) return null
        return span(text, index, index)
    }

    fun span(text: String, anchor: Int, focus: Int): WordHit? {
        if (text.isEmpty()) return null
        val anchorIndex = anchor.coerceIn(0, text.lastIndex)
        if (!text[anchorIndex].isLetter()) return null
        val focusIndex = focus.coerceIn(0, text.lastIndex)
        val endIndex = if (text[focusIndex].isLetter()) {
            focusIndex
        } else {
            nearestLetterToward(text, focusIndex, anchorIndex) ?: anchorIndex
        }
        val anchorBounds = wordBounds(text, anchorIndex) ?: return null
        val endBounds = wordBounds(text, endIndex) ?: return null
        val from = minOf(anchorBounds.first, endBounds.first)
        val to = maxOf(anchorBounds.last, endBounds.last) + 1
        val word = text.substring(from, to).trim()
        if (word.isEmpty()) return null
        return WordHit(
            word = word,
            sentence = sentenceContaining(text, from),
            start = from,
            end = to,
        )
    }

    private fun nearestLetterToward(text: String, from: Int, toward: Int): Int? {
        val step = if (toward < from) -1 else 1
        var index = from
        while (index != toward) {
            if (text[index].isLetter()) return index
            index += step
        }
        return if (text[toward].isLetter()) toward else null
    }

    private fun wordBounds(text: String, index: Int): IntRange? {
        if (!text[index].isLetter()) return null
        var start = index
        while (start > 0 && text[start - 1].isLetter()) start--
        var end = index
        while (end + 1 < text.length && text[end + 1].isLetter()) end++
        return start..end
    }

    private fun sentenceContaining(text: String, index: Int): String {
        var from = index
        while (from > 0 && text[from - 1] != '.' && text[from - 1] != '?' && text[from - 1] != '!') {
            from--
        }
        while (from < text.length && text[from].isWhitespace()) from++
        var to = index
        while (to < text.length && text[to] != '.' && text[to] != '?' && text[to] != '!') {
            to++
        }
        if (to < text.length) to++
        return text.substring(from, to).trim()
    }
}
