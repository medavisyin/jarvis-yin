package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.charset.StandardCharsets

class TxtImporterTest {
    @Test
    fun readsUtf8AndChunks() {
        val bytes = "Hello bank.\n\nSecond paragraph.".toByteArray(StandardCharsets.UTF_8)
        val chunks = TxtImporter.importUtf8(bytes)
        assertEquals(1, chunks.size)
        assertTrueish(chunks[0], "Hello bank.")
    }

    private fun assertTrueish(haystack: String, fragment: String) {
        org.junit.Assert.assertTrue(haystack.contains(fragment))
    }
}
