package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingDisplayTest {
    @Test
    fun magazineShelfCountsASplitArticleOnce() {
        val pages = magazine()
        val read = setOf(pages[0].readKey)
        assertEquals("已读 1 篇", ReadingDisplay.shelfLine(pages, 0, read))
        assertEquals("已读 0 篇", ReadingDisplay.shelfLine(pages, 1, emptySet()))
    }

    @Test
    fun novelShelfShowsTheChapterPosition() {
        val pages = novel()
        assertEquals("Chapter 1 · 1/2", ReadingDisplay.shelfLine(pages, 1, emptySet()))
        assertEquals("Chapter 1 · 2/2", ReadingDisplay.shelfLine(pages, 2, emptySet()))
        assertEquals("Chapter 2", ReadingDisplay.shelfLine(pages, 3, emptySet()))
        assertNull(ReadingDisplay.shelfLine(pages, 0, emptySet()))
    }

    @Test
    fun untitledBookLeavesTheShelfLineToThePageCount() {
        val pages = ReadingGroups.pages(listOf("", ""), listOf("a", "b"))
        assertNull(ReadingDisplay.shelfLine(pages, 0, emptySet()))
    }

    @Test
    fun magazineOpeningDropsTheMastheadAndTheSectionLine() {
        val page = magazinePage(section = "Britain", article = "A railway")
        val shown = ReadingDisplay.show(
            page,
            "October 11, 2026 PRICE \$9.99\n\nThe Economist\n\nBritain\n\nA railway opens.",
        )
        assertNull(shown.heading)
        assertEquals("A railway opens.", shown.body)
    }

    @Test
    fun magazineKeepsAPriceThatIsPartOfTheSentence() {
        val page = magazinePage(section = "Britain", article = "Oil")
        val shown = ReadingDisplay.show(page, "The PRICE of oil rose.\n\nMore.")
        assertTrue(shown.body.contains("PRICE"))
        assertTrue(shown.body.startsWith("The PRICE"))
    }

    @Test
    fun magazineKeepsTheOriginalWhenOnlyMastheadRemains() {
        val page = magazinePage(section = "Britain", article = "Empty")
        val text = "The Economist\nOctober 11, 2026 PRICE \$9.99"
        val shown = ReadingDisplay.show(page, text)
        assertEquals(text, shown.body)
    }

    @Test
    fun dateAndPriceAtTheStartOfALineLeaveTheArticle() {
        val page = magazinePage(section = "Britain", article = "Budget")
        val shown = ReadingDisplay.show(page, "October 11, 2026 PRICE \$9.99 The budget failed.")
        assertEquals("The budget failed.", shown.body)
    }

    @Test
    fun magazineDropsOtherMastheadLinesOnlyAtTheOpening() {
        val page = magazinePage(section = "Britain", article = "Piece")
        val shown = ReadingDisplay.show(
            page,
            "The New Yorker\nWired\n2024 PRICE\nCover\nContents\nMasthead\nTable of contents\nBritain\n\nThe piece starts.\n\nThe Economist\nContents",
        )
        assertEquals("The piece starts.\n\nThe Economist\nContents", shown.body)
    }

    @Test
    fun magazineKeepsNearMissHeadings() {
        val page = magazinePage(section = "Britain", article = "Piece")
        val text = "The Economist reported the merger.\n\nCover story\n\nContents of the bill"
        assertEquals(text, ReadingDisplay.show(page, text).body)
    }

    @Test
    fun aSectionMentionInsideTheFirstSentenceStays() {
        val page = magazinePage(section = "Britain", article = "Change")
        val shown = ReadingDisplay.show(page, "Britain is changing.\n\nMore.")
        assertEquals("Britain is changing.\n\nMore.", shown.body)
    }

    @Test
    fun novelFirstPageLiftsAMatchingChapterLine() {
        val page = novelPage(article = "Chapter 1", part = 1, parts = 2)
        val shown = ReadingDisplay.show(page, "CHAPTER 1\n\nOnce there was a river.")
        assertEquals("CHAPTER 1", shown.heading)
        assertEquals("Once there was a river.", shown.body)
    }

    @Test
    fun novelFirstPageAddsAHeadingWhenTheBodyDoesNotStartWithIt() {
        val page = novelPage(article = "Chapter 1", part = 1, parts = 2)
        val text = "Once there was a river."
        val shown = ReadingDisplay.show(page, text)
        assertEquals("Chapter 1", shown.heading)
        assertEquals(text, shown.body)
    }

    @Test
    fun laterChapterPagesDoNotLiftTheTitle() {
        val page = novelPage(article = "Chapter 1", part = 2, parts = 2)
        val text = "Chapter 1\n\nMore of the river."
        val shown = ReadingDisplay.show(page, text)
        assertNull(shown.heading)
        assertEquals(text, shown.body)
    }

    @Test
    fun chromePutsTheSectionAboveASinglePageArticle() {
        val pages = magazine()
        val chrome = ReadingDisplay.chrome(pages[2], 2)
        assertEquals("Britain", chrome.section)
        assertEquals("A railway", chrome.article)
        val novelChrome = ReadingDisplay.chrome(novel()[3], 3)
        assertNull(novelChrome.section)
        assertNull(novelChrome.article)
        assertEquals("Chapter 1 · 2/2", ReadingDisplay.chrome(novel()[2], 2).article)
    }

    @Test
    fun edgeBandIsOnlyTheOuterStrip() {
        assertEquals(-1, ReadingDisplay.edgeDelta(10f, 400f, 56f))
        assertNull(ReadingDisplay.edgeDelta(56f, 400f, 56f))
        assertNull(ReadingDisplay.edgeDelta(200f, 400f, 56f))
        assertNull(ReadingDisplay.edgeDelta(344f, 400f, 56f))
        assertEquals(1, ReadingDisplay.edgeDelta(345f, 400f, 56f))
        assertNull(ReadingDisplay.edgeDelta(10f, 0f, 56f))
    }

    @Test
    fun edgeTurnsOnlyNovelsAndStopsAtTheEnds() {
        assertFalse(ReadingDisplay.allowsEdge(magazine = true))
        assertTrue(ReadingDisplay.allowsEdge(magazine = false))
        assertNull(ReadingDisplay.turnedIndex(0, -1, 5))
        assertEquals(1, ReadingDisplay.turnedIndex(0, 1, 5))
        assertNull(ReadingDisplay.turnedIndex(4, 1, 5))
    }

    private fun magazine(): List<ReadingGroups.Page> {
        return ReadingGroups.pages(
            listOf("Fed shift (1)", "Fed shift (2)", "A railway"),
            listOf("Leaders\n\nThe Fed moved.", "The second half.", "Britain\n\nA railway opens."),
        )
    }

    private fun novel(): List<ReadingGroups.Page> {
        return ReadingGroups.pages(
            listOf("", "Chapter 1", "Chapter 1", "Chapter 2"),
            listOf("Front.", "Once.", "More.", "End."),
        )
    }

    private fun magazinePage(section: String, article: String) = ReadingGroups.Page(
        section = section,
        article = article,
        part = 1,
        parts = 1,
        magazine = true,
    )

    private fun novelPage(article: String, part: Int, parts: Int) = ReadingGroups.Page(
        section = "",
        article = article,
        part = part,
        parts = parts,
        magazine = false,
    )
}
