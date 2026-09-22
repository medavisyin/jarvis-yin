package com.jarvis.ir.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class ReadingLayoutTest {
    @Test
    fun paragraphRangesKeepOriginalOffsets() {
        val passage = "Hello.\n\nWorld."
        assertEquals(listOf(0 until 6, 8 until 14), paragraphRanges(passage))
    }
}
