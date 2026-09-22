package com.jarvis.ir.books

object Chunker {
    fun wordCount(text: String): Int {
        val spaced = text.split(Regex("""\s+""")).count { it.isNotEmpty() }
        val cjk = text.count { it.code in 0x4E00..0x9FFF }
        return if (cjk > spaced * 2) cjk.coerceAtLeast(spaced) else spaced
    }

    fun chunk(text: String, maxWords: Int = 1200): List<String> {
        val paragraphs = text.split(Regex("""\n\s*\n""")).map { it.trim() }.filter { it.isNotEmpty() }
        if (paragraphs.isEmpty()) return emptyList()
        val pieces = paragraphs.flatMap { splitToFit(it, maxWords) }
        return pack(pieces, maxWords, "\n\n")
    }

    private fun splitToFit(para: String, maxWords: Int): List<String> {
        if (wordCount(para) <= maxWords) return listOf(para)
        val sentences = para.split(Regex("""(?<=[.!?])\s+|(?<=[。！？])""")).filter { it.isNotBlank() }
        if (sentences.size <= 1) return splitWords(para, maxWords)
        return pack(sentences, maxWords, " ").flatMap { piece ->
            if (wordCount(piece) <= maxWords) listOf(piece) else splitWords(piece, maxWords)
        }
    }

    private fun splitWords(text: String, maxWords: Int): List<String> {
        val words = text.split(Regex("""\s+""")).filter { it.isNotEmpty() }
        if (words.isEmpty()) return emptyList()
        val size = maxWords.coerceAtLeast(1)
        if (words.size == 1 && wordCount(words[0]) > size) {
            return words[0].chunked(size)
        }
        return words.chunked(size).map { it.joinToString(" ") }
    }

    private fun pack(pieces: List<String>, maxWords: Int, separator: String): List<String> {
        val chunks = mutableListOf<String>()
        val current = mutableListOf<String>()
        var words = 0
        for (piece in pieces) {
            val pieceWords = wordCount(piece)
            if (current.isNotEmpty() && words + pieceWords > maxWords) {
                chunks.add(current.joinToString(separator))
                current.clear()
                words = 0
            }
            current.add(piece)
            words += pieceWords
        }
        if (current.isNotEmpty()) chunks.add(current.joinToString(separator))
        return chunks
    }
}
