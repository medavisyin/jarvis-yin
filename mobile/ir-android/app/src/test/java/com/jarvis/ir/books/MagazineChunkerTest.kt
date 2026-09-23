package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MagazineChunkerTest {
    @Test
    fun splitsOnArticleHeadings() {
        val text = """
            Leaders

            Something Must Be Done

            The first article body goes here with enough prose for a magazine piece. It continues across several sentences to look like a real article.

            Finance & economics

            Rates Stay Higher for Longer

            The second article discusses interest rates and bond markets in detail. Central banks remain cautious amid sticky inflation data worldwide.
        """.trimIndent()
        val chunks = MagazineChunker.chunkText(text)
        assertTrue(chunks.size >= 2)
        assertTrue(chunks.any { it.text.contains("first article", ignoreCase = true) })
        assertTrue(chunks.any { it.text.contains("interest rates", ignoreCase = true) })
    }

    @Test
    fun weakSpineTitleSplitsAndDropsPrice() {
        val body = "Contents\n\n" +
            "Leaders\n\n" +
            ("Policy brief paragraph with enough words to count as body copy. ".repeat(8)) +
            "\n\n" +
            "Science & technology\n\n" +
            ("Lab notes and gadgets discussed in detail for readers at home. ".repeat(8))
        val chunks = MagazineChunker.fromSections(
            listOf(BookSection(title = "MARCH 2, 2026PRICE $10.99", text = body)),
        )
        assertTrue(chunks.size >= 2)
        assertTrue(chunks.none { it.title.contains("PRICE", ignoreCase = true) })
        assertTrue(
            chunks.any { it.title.contains("Leaders") } ||
                chunks.any { it.title.contains("Science") },
        )
    }

    @Test
    fun passagesKeepStrongSectionsApart() {
        val policy = "Policy brief paragraph with enough words to count as body copy. ".repeat(8)
        val lab = "Lab notes and gadgets discussed in detail for readers at home. ".repeat(8)
        val passages = MagazineChunker.passages(
            MagazineChunker.fromSections(
                listOf(
                    BookSection("Leaders", "Something Must Be Done\n\n$policy"),
                    BookSection("Science & technology", "New Instruments\n\n$lab"),
                ),
            ),
        )
        assertEquals(2, passages.size)
        assertTrue(passages[0].contains("Leaders"))
        assertTrue(passages[0].contains("Policy brief"))
        assertFalse(passages[0].contains("Lab notes"))
        assertTrue(passages[1].contains("Science"))
        assertTrue(passages[1].contains("Lab notes"))
    }

    @Test
    fun pageHeadingsStartNewArticles() {
        val page1 = "Leaders\n\n" + ("Markets opened higher and stayed there for the week. ".repeat(6))
        val page2 = ("The rally continued into a second page of the same piece. ".repeat(6))
        val page3 = "Finance & economics\n\n" + ("Bond yields stayed high across the week. ".repeat(6))
        val chunks = MagazineChunker.fromPages(listOf(page1, page2, page3))
        assertTrue(chunks.size >= 2)
        assertTrue(chunks[0].text.contains("second page"))
        assertTrue(chunks.any { it.text.contains("Bond yields") && !it.text.contains("Markets opened") })
    }
}
