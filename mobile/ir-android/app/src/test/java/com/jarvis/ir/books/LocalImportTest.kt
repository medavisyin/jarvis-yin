package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocalImportTest {
    @Test
    fun lookupFailureUsesImportMessage() {
        val fromName = LocalImport.probe(
            name = { throw IllegalStateException("query") },
            mime = { "application/pdf" },
        )
        assertEquals(EconomistMessages.IMPORT, fromName.error)
        assertNull(fromName.kind)

        val fromMime = LocalImport.probe(
            name = { "issue.pdf" },
            mime = { throw IllegalStateException("type") },
        )
        assertEquals(EconomistMessages.IMPORT, fromMime.error)
        assertNull(fromMime.kind)
    }

    @Test
    fun unknownFormatStaysTheUnknownLine() {
        val probe = LocalImport.probe(name = { "sheet.docx" }, mime = { "application/octet-stream" })
        assertEquals(LocalImportMessages.UNKNOWN, probe.error)
        assertNull(probe.kind)
    }
}
