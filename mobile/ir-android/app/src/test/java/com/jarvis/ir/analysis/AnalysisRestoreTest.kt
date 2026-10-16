package com.jarvis.ir.analysis

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisRestoreTest {
    @Test
    fun unsuccessfulRunRestoresTheSavedTextForThatPage() {
        val state = AnalysisRestore.screen(
            startedBook = "book",
            startedPage = 7,
            startedKind = AnalysisView.VOCAB,
            currentBook = "book",
            currentPage = 7,
            currentKind = AnalysisView.VOCAB,
            saved = "kept words",
        )

        assertEquals("kept words", state?.text)
        assertTrue(state!!.saved)
    }

    @Test
    fun doesNotRestoreOntoAnotherPageOrKind() {
        assertNull(
            AnalysisRestore.screen(
                startedBook = "book",
                startedPage = 7,
                startedKind = AnalysisView.VOCAB,
                currentBook = "book",
                currentPage = 8,
                currentKind = AnalysisView.VOCAB,
                saved = "kept words",
            ),
        )
        assertNull(
            AnalysisRestore.screen(
                startedBook = "book",
                startedPage = 7,
                startedKind = AnalysisView.VOCAB,
                currentBook = "book",
                currentPage = 7,
                currentKind = AnalysisView.CULTURE,
                saved = "kept words",
            ),
        )
    }
}
