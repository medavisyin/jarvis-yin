package com.jarvis.ir.ui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingChromeTest {
    @Test
    fun notesHidePageAndChapterControls() {
        assertFalse(showPageControls(showNotes = true, showShelf = false, hasChunks = true))
        assertTrue(showPageControls(showNotes = false, showShelf = false, hasChunks = true))
        assertFalse(showPageControls(showNotes = false, showShelf = true, hasChunks = true))
    }
}
