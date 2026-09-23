package com.jarvis.ir.books

object BookOpen {
    fun errorIfEmpty(chunks: List<String>): String? =
        if (chunks.isEmpty()) EconomistMessages.IMPORT else null
}
