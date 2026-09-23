package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FileKindTest {
    @Test
    fun suffixWinsOverMime() {
        assertEquals("txt", FileKind.detect("notes.TXT", "application/pdf"))
        assertEquals("epub", FileKind.detect("issue.epub", "application/octet-stream"))
        assertEquals("pdf", FileKind.detect("issue.PDF", "application/octet-stream"))
    }

    @Test
    fun mimeUsedWhenThereIsNoSuffix() {
        assertEquals("txt", FileKind.detect("notes", "text/plain"))
        assertEquals("epub", FileKind.detect("book", "application/epub+zip"))
        assertEquals("pdf", FileKind.detect("issue", "application/pdf"))
    }

    @Test
    fun unknownFormatsStayNull() {
        assertNull(FileKind.detect("sheet.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        assertNull(FileKind.detect("blob", "application/octet-stream"))
        assertNull(FileKind.detect(null, null))
        assertNull(FileKind.detect("  ", "  "))
    }

    @Test
    fun unknownFileMessageIsTheApprovedLine() {
        assertEquals("无法识别这个文件", LocalImportMessages.UNKNOWN)
    }
}
