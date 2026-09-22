package com.jarvis.ir.books

import org.junit.Assert.assertTrue
import org.junit.Test

class EpubImporterTest {
    @Test
    fun extractsBodyTextFromFixture() {
        val stream = javaClass.classLoader!!.getResourceAsStream("sample.epub")!!
        val text = EpubImporter.extractText(stream)
        assertTrue(text.contains("river bank"))
    }
}
