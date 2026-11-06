package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChapterLocatorTest {
    @Test
    fun headingPageSkipsTheContentsList() {
        val pages = listOf(
            "Contents\nChapter 1    12\nChapter 2    30",
            "CHAPTER 1\n\nIt was very dark.",
            "The trail went on.\nChapter 1 was behind them.",
        )
        assertEquals(1, ChapterLocator.pageForHeading(pages, "CHAPTER 1"))
        assertEquals(1, ChapterLocator.pageForHeading(pages, "Chapter 1 (2)"))
        assertNull(ChapterLocator.pageForHeading(pages, "Missing"))
    }

    @Test
    fun longTitleAndExcerptFindTheOpeningPage() {
        val pages = listOf(
            "项塔兰\n前言\n第一章\n第二章",
            "第一章\n我花了很长的岁月，走过大半个世界，才真正学到什么是爱与命运",
            "You Don’t Know What’s in My Heart\nWE WERE FRACTIOUS AND overpaid.",
        )
        val longTitle = "第一章 我花了很长的岁月，走过大半个世界，才真正学到什么是爱与命运，以及我们所做的抉择"
        assertEquals(1, ChapterLocator.pageForChapter(pages, longTitle))
        assertEquals(2, ChapterLocator.pageForChapter(pages, "Chapter 1 (1)", "WE WERE FRACTIOUS AND overpaid."))
        assertNull(ChapterLocator.pageForChapter(pages, "Chapter 1"))
    }
}
