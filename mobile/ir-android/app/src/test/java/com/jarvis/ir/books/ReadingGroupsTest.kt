package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingGroupsTest {
    @Test
    fun magazineGroupsBySectionAndNumbersSplitArticles() {
        val titles = listOf("Fed shift (1)", "Fed shift (2)", "A new railway")
        val texts = listOf(
            "Leaders\n\nThe Fed moved.",
            "The second half of the Fed piece.",
            "Britain\n\nA railway opens.",
        )
        val pages = ReadingGroups.pages(titles, texts)
        assertTrue(pages.all { it.magazine })
        assertEquals(listOf("Leaders", "Leaders", "Britain"), pages.map { it.section })
        assertEquals("Fed shift · 1/2", pages[0].label(0))
        assertEquals("Fed shift · 2/2", pages[1].label(1))
        assertEquals("A new railway", pages[2].label(2))
        assertTrue(pages[1].isLastPart)
        assertFalse(pages[0].isLastPart)
        assertTrue(pages[2].isLastPart)
        assertEquals(2, ReadingGroups.nextStart(pages, 0))
        val menu = ReadingGroups.menu(pages, setOf(pages[1].readKey))
        assertEquals(
            listOf("Leaders", "Fed shift · 1/2  已读", "Fed shift · 2/2  已读", "Britain", "A new railway"),
            menu.map { it.text },
        )
    }

    @Test
    fun oneSectionAndAMentionInsideTheBodyAreNotAMagazine() {
        val titles = listOf("Chapter 1", "Chapter 1", "Chapter 2")
        val texts = listOf(
            "Leaders\n\nOnce there was a river.",
            "China appears only after the opening.\n\nMore.\n\nStill more.\n\nChina",
            "The end.",
        )
        val pages = ReadingGroups.pages(titles, texts)
        assertTrue(pages.none { it.magazine })
        assertEquals("Chapter 1 · 1/2", pages[0].label(0))
        assertEquals("Chapter 1 · 2/2", pages[1].label(1))
        assertEquals("Chapter 2", pages[2].label(2))
        assertNull(ReadingGroups.nextStart(pages, 0))
        assertFalse(pages[1].isLastPart)
    }

    @Test
    fun untitledPagesStayNumbered() {
        val pages = ReadingGroups.pages(listOf("", ""), listOf("a", "b"))
        assertEquals("第 1 段", pages[0].label(0))
        assertEquals("第 2 段", pages[1].label(1))
        assertEquals(listOf("第 1 段", "第 2 段"), ReadingGroups.menu(pages, emptySet()).map { it.text })
    }
}
