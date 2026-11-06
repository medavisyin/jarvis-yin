package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChapterSwipeTest {
    @Test
    fun horizontalSwipeTurnsTheChapter() {
        assertEquals(1, ChapterSwipe.delta(-120f, 10f, 72f))
        assertEquals(-1, ChapterSwipe.delta(120f, -8f, 72f))
        assertNull(ChapterSwipe.delta(-20f, 4f, 72f))
        assertNull(ChapterSwipe.delta(-40f, 130f, 72f))
    }
}
