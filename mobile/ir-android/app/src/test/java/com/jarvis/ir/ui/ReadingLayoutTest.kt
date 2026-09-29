package com.jarvis.ir.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingLayoutTest {
    @Test
    fun paragraphRangesKeepOriginalOffsets() {
        val passage = "Hello.\n\nWorld."
        assertEquals(listOf(0 until 6, 8 until 14), paragraphRanges(passage))
    }

    @Test
    fun analysisSitsBesideThePassageOnlyWhenWide() {
        assertFalse(analysisBesidePassage(599))
        assertTrue(analysisBesidePassage(600))
    }
}
