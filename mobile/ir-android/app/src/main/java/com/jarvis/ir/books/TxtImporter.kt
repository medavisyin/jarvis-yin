package com.jarvis.ir.books

import java.nio.charset.StandardCharsets

object TxtImporter {
    fun importUtf8(bytes: ByteArray, maxWords: Int = 400): List<String> {
        val text = String(bytes, StandardCharsets.UTF_8).trim()
        return Chunker.chunk(text, maxWords)
    }
}
