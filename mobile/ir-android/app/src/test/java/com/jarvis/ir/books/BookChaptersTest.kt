package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BookChaptersTest {
    @Test
    fun retitleFindsChaptersAndLeavesUntitledTextAlone() {
        val pages = BookChapters.retitle("Chapter 1\n\nLeft.\n\nChapter 2\n\nRight.")
        assertEquals(listOf("Chapter 1", "Chapter 2"), pages?.map { it.title })
        assertNull(BookChapters.retitle("Just a story about the river."))
    }

    @Test
    fun chapterHeadingsKeepTheTitleOnLaterPages() {
        val body = (1..100).joinToString(" ") { "word$it" }
        val text = "Chapter 1\n\n$body\n\nChapter 2\n\nEnd."
        val pages = BookChapters.fromPlainText(text, maxWords = 40)
        val first = pages.takeWhile { it.title == "Chapter 1" }
        assertTrue(first.size >= 2)
        assertTrue(first.first().text.contains("Chapter 1"))
        assertEquals("Chapter 2", pages.last().title)
        assertTrue(pages.last().text.contains("Chapter 2"))
        assertTrue(pages.last().text.contains("End."))
    }

    @Test
    fun chapterInsideASentenceDoesNotSplit() {
        val text = "He opened chapter 1 of the book.\n\nThen he slept."
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertEquals(1, pages.size)
        assertEquals("", pages[0].title)
        assertTrue(pages[0].text.contains("chapter 1"))
    }

    @Test
    fun proseThatStartsWithChapterIsNotAHeading() {
        val text = "Chapter Mix\n\nHello.\n\nChapter 1 was " +
            (1..30).joinToString(" ") { "long$it" } +
            "\n\nChapter 2\n\nEnd."
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertTrue(pages.all { it.title.isEmpty() })
        assertTrue(pages.joinToString("\n").contains("Chapter 2"))
    }

    @Test
    fun oneHeadingFallsBackToUntitledPages() {
        val pages = BookChapters.fromPlainText("Chapter 1\n\nHello bank.", maxWords = 400)
        assertEquals(1, pages.size)
        assertEquals("", pages[0].title)
        assertTrue(pages[0].text.contains("Chapter 1"))
        assertTrue(pages[0].text.contains("Hello bank."))
    }

    @Test
    fun romanAndChineseChapterHeadingsSplit() {
        val pages = BookChapters.fromPlainText(
            "CHAPTER IV\n\nLeft.\n\n第2章 河边\n\nRight.",
            maxWords = 400,
        )
        assertEquals(listOf("CHAPTER IV", "第2章 河边"), pages.map { it.title })
        assertTrue(pages[0].text.contains("CHAPTER IV"))
        assertTrue(pages[1].text.contains("Right."))
    }

    @Test
    fun contentsTitlesFoundLaterInTheBodySplitTheBook() {
        val filler = (1..30).joinToString(" ") { "pad$it" }
        val text = """
            Contents

            The River  12

            The Bank  40

            $filler

            The River

            Along the river.

            The Bank

            Along the bank.
        """.trimIndent()
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertEquals(listOf("The River", "The Bank"), pages.map { it.title }.filter { it.isNotEmpty() }.distinct())
        assertTrue(pages.first { it.title == "The River" }.text.contains("Along the river."))
        assertTrue(pages.first { it.title == "The Bank" }.text.contains("Along the bank."))
    }

    @Test
    fun contentsTitlesMissingFromTheBodyStayUntitled() {
        val filler = (1..30).joinToString(" ") { "pad$it" }
        val text = """
            Contents

            The River

            The Bank

            $filler

            Just a story.
        """.trimIndent()
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertTrue(pages.all { it.title.isEmpty() })
        assertTrue(pages.joinToString("\n").contains("Just a story."))
    }

    @Test
    fun spineTocCutsAtTwoDifferentFiles() {
        val pages = BookChapters.pagesFromSpine(
            pieces = listOf(
                BookChapters.SpinePiece("pre.xhtml", "Front matter."),
                BookChapters.SpinePiece("c1.xhtml", "Once upon a river."),
                BookChapters.SpinePiece("c2.xhtml", "Then a bank."),
            ),
            toc = listOf(
                BookChapters.TocRef("Chapter 1", "c1.xhtml"),
                BookChapters.TocRef("Chapter 2", "c2.xhtml#start"),
            ),
            maxWords = 400,
        )
        assertEquals(listOf("", "Chapter 1", "Chapter 2"), pages?.map { it.title })
        assertEquals("Once upon a river.", pages?.get(1)?.text)
    }

    @Test
    fun spineTocAnchorsInOneFileAreNotTwoChapters() {
        val pages = BookChapters.pagesFromSpine(
            pieces = listOf(BookChapters.SpinePiece("book.xhtml", "Chapter 1\n\nA.\n\nChapter 2\n\nB.")),
            toc = listOf(
                BookChapters.TocRef("Chapter 1", "book.xhtml#a"),
                BookChapters.TocRef("Chapter 2", "book.xhtml#b"),
            ),
            maxWords = 400,
        )
        assertNull(pages)
    }

    @Test
    fun ncxListsChapterSources() {
        val xml = """
            <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
              <navMap>
                <navPoint id="n1" playOrder="1">
                  <navLabel><text>Chapter 1</text></navLabel>
                  <content src="c1.xhtml"/>
                </navPoint>
                <navPoint id="n2" playOrder="2">
                  <navLabel><text>Chapter 2</text></navLabel>
                  <content src="c2.xhtml"/>
                </navPoint>
              </navMap>
            </ncx>
        """.trimIndent()
        assertEquals(
            listOf(
                BookChapters.TocRef("Chapter 1", "c1.xhtml"),
                BookChapters.TocRef("Chapter 2", "c2.xhtml"),
            ),
            BookChapters.tocFromNcx(xml),
        )
    }

    @Test
    fun contentsListImmediatelyFollowedByItsTitlesStillSplits() {
        val text = """
            Contents

            The River

            The Bank

            The River

            Along the river for more than twenty words so this body is long enough.

            The Bank

            Along the bank for more than twenty words as well.
        """.trimIndent()
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertEquals(listOf("The River", "The Bank"), pages.map { it.title }.filter { it.isNotEmpty() })
        assertTrue(pages.first { it.title == "The River" }.text.contains("Along the river"))
        assertTrue(pages.first { it.title == "The Bank" }.text.contains("Along the bank"))
    }

    @Test
    fun numberedContentsTitlesKeepTheirOwnNumber() {
        val text = """
            Contents

            Part 1

            Part 2

            Part 1

            Left side is a sentence of ordinary length here.

            Part 2

            Right side is a sentence of ordinary length here.
        """.trimIndent()
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertEquals(listOf("Part 1", "Part 2"), pages.map { it.title }.filter { it.isNotEmpty() })
    }

    @Test
    fun capitalizedSentenceAfterChapterNumberDoesNotSplit() {
        val text = "Chapter 1 Today was fine.\n\nChapter I Went home."
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertTrue(pages.all { it.title.isEmpty() })
    }

    @Test
    fun colonSubtitleStillStartsAChapter() {
        val pages = BookChapters.fromPlainText(
            "Chapter 1: The Beginning\n\nLeft.\n\nChapter 2\n\nRight.",
            maxWords = 400,
        )
        assertEquals(listOf("Chapter 1: The Beginning", "Chapter 2"), pages.map { it.title })
    }

    @Test
    fun doubleSpacedPartNumbersStillSplit() {
        val text = """
            Contents

            Part  1

            Part  2

            Part  1

            Left side.

            Part  2

            Right side.
        """.trimIndent()
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertEquals(listOf("Part 1", "Part 2"), pages.map { it.title }.filter { it.isNotEmpty() })
    }

    @Test
    fun longChineseChapterTitlesStillSplit() {
        val first = "第1章 " + "甲".repeat(22)
        val second = "第2章 " + "乙".repeat(22)
        val pages = BookChapters.fromPlainText("$first\n\nLeft.\n\n$second\n\nRight.", maxWords = 400)
        assertEquals(listOf(first, second), pages.map { it.title })
    }

    @Test
    fun shortSentencesThatStartWithChapterDoNotSplit() {
        val text = "Chapter 1 was a short day.\n\nChapter I went home.\n\n第1章讲完了。\n\n第2章也讲完了。"
        val pages = BookChapters.fromPlainText(text, maxWords = 400)
        assertTrue(pages.all { it.title.isEmpty() })
    }

    @Test
    fun singleNewlineChapterLinesStillSplit() {
        val body = (1..50).joinToString(" ") { "word$it" }
        val text = "Chapter 1\n$body\nChapter 2\nEnd."
        val pages = BookChapters.fromPlainText(text, maxWords = 40)
        assertEquals("Chapter 1", pages.first().title)
        assertEquals("Chapter 2", pages.last().title)
        assertTrue(pages.last().text.contains("End."))
    }

    @Test
    fun txtImportUsesThoseSameChapterLines() {
        val body = (1..50).joinToString(" ") { "word$it" }
        val bytes = "Chapter 1\n$body\nChapter 2\nEnd.".toByteArray()
        val pages = TxtImporter.importLocal(bytes, maxWords = 40)
        assertEquals("Chapter 1", pages.first().title)
        assertEquals("Chapter 2", pages.last().title)
    }

    @Test
    fun coverPlusOneBodyFileFallsThrough() {
        val pages = BookChapters.pagesFromSpine(
            pieces = listOf(
                BookChapters.SpinePiece("cover.xhtml", "Cover page."),
                BookChapters.SpinePiece("book.xhtml", "Chapter 1\n\nA.\n\nChapter 2\n\nB."),
            ),
            toc = listOf(
                BookChapters.TocRef("Cover", "cover.xhtml"),
                BookChapters.TocRef("Chapter 1", "book.xhtml#a"),
                BookChapters.TocRef("Chapter 2", "book.xhtml#b"),
            ),
            maxWords = 400,
        )
        assertNull(pages)
    }

    @Test
    fun ncxMissesThenNavIsUsed() {
        val pages = BookChapters.pagesFromTocSources(
            pieces = listOf(
                BookChapters.SpinePiece("c1.xhtml", "Once."),
                BookChapters.SpinePiece("c2.xhtml", "Then."),
            ),
            sources = listOf(
                listOf(
                    BookChapters.TocRef("Old", "missing1.xhtml"),
                    BookChapters.TocRef("Older", "missing2.xhtml"),
                ),
                listOf(
                    BookChapters.TocRef("Chapter 1", "c1.xhtml"),
                    BookChapters.TocRef("Chapter 2", "c2.xhtml"),
                ),
            ),
            maxWords = 400,
        )
        assertEquals(listOf("Chapter 1", "Chapter 2"), pages?.map { it.title })
    }

    @Test
    fun landmarksNavIsNotTheTableOfContents() {
        val html = """
            <nav epub:type="landmarks">
              <ol><li><a href="c1.xhtml">Start</a></li><li><a href="c2.xhtml">Other</a></li></ol>
            </nav>
        """.trimIndent()
        assertEquals(emptyList<BookChapters.TocRef>(), BookChapters.tocFromNav(html))
    }

    @Test
    fun plusInHrefStillMatchesAndBadEscapeDoesNotThrow() {
        val matched = BookChapters.pagesFromSpine(
            pieces = listOf(
                BookChapters.SpinePiece("my+book/c1.xhtml", "A."),
                BookChapters.SpinePiece("my+book/c2.xhtml", "B."),
            ),
            toc = listOf(
                BookChapters.TocRef("Chapter 1", "my+book/c1.xhtml"),
                BookChapters.TocRef("Chapter 2", "my+book/c2.xhtml"),
            ),
            maxWords = 400,
        )
        assertEquals(listOf("Chapter 1", "Chapter 2"), matched?.map { it.title })
        val skipped = BookChapters.pagesFromSpine(
            pieces = listOf(
                BookChapters.SpinePiece("c1.xhtml", "A."),
                BookChapters.SpinePiece("c2.xhtml", "B."),
            ),
            toc = listOf(
                BookChapters.TocRef("Chapter 1", "c1.xhtml"),
                BookChapters.TocRef("Chapter 2", "%zz"),
            ),
            maxWords = 400,
        )
        assertNull(skipped)
    }
}
