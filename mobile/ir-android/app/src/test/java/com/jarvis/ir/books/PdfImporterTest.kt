package com.jarvis.ir.books

import org.junit.Assert.assertTrue
import org.junit.Test

class PdfImporterTest {
    @Test
    fun fixtureExtractsKnownSentence() {
        val stream = javaClass.classLoader!!.getResourceAsStream("sample.pdf")!!
        val text = JvmPdfExtractor.extract(stream)
        assertTrue(text.contains("river bank"))
    }
}
