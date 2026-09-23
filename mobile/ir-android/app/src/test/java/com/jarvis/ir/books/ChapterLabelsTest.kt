package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Test

class ChapterLabelsTest {
    @Test
    fun usesStoredTitle() {
        assertEquals("Leaders", ChapterLabels.label("Leaders", 0))
    }

    @Test
    fun blankTitleIsNumberedPassage() {
        assertEquals("第 1 段", ChapterLabels.label("", 0))
        assertEquals("第 2 段", ChapterLabels.label("   ", 1))
    }
}
