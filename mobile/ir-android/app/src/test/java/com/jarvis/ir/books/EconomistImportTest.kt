package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.coroutines.cancellation.CancellationException

class EconomistImportTest {
    @Test
    fun epubKeepsSpineSectionsAsSeparateArticles() {
        val policy = "Policy brief paragraph with enough words to count as body copy. ".repeat(8)
        val lab = "Lab notes and gadgets discussed in detail for readers at home. ".repeat(8)
        val bytes = epub(
            chapter(
                "c1.xhtml",
                "Leaders",
                "Something Must Be Done",
                policy,
            ),
            chapter(
                "c2.xhtml",
                "Science &amp; technology",
                "New Instruments",
                lab,
            ),
        )
        val chunks = EconomistImport.chunksFromEpub(bytes.inputStream())
        assertEquals(2, chunks.size)
        assertTrue(chunks[0].contains("Leaders"))
        assertTrue(chunks[0].contains("Policy brief"))
        assertFalse(chunks[0].contains("Lab notes"))
        assertTrue(chunks[1].contains("Science"))
        assertTrue(chunks[1].contains("Lab notes"))
    }

    @Test
    fun corruptEpubUsesImportMessage() {
        val error = runCatching { EconomistImport.chunksFromEpub("not-an-epub".byteInputStream()) }.exceptionOrNull()
        assertEquals(EconomistMessages.IMPORT, error?.message)
    }

    @Test
    fun cancellationIsNotRewrittenAsImportFailure() {
        val error = runCatching {
            EconomistImport.runImport { throw CancellationException("stop") }
        }.exceptionOrNull()
        assertTrue(error is CancellationException)
    }

    @Test
    fun bodyHeadingBeatsHtmlTitle() {
        val policy = "Policy brief paragraph with enough words to count as body copy. ".repeat(8)
        val bytes = epub(
            chapter(
                "c1.xhtml",
                "Leaders",
                "Something Must Be Done",
                policy,
                documentTitle = "Generic File Title",
            ),
        )
        val chunks = EconomistImport.chunksFromEpub(bytes.inputStream())
        assertTrue(chunks[0].contains("Leaders"))
        assertFalse(chunks[0].startsWith("Generic File Title"))
    }

    @Test
    fun epubTitlesFollowReadableArticles() {
        val policy = "Policy brief paragraph with enough words to count as body copy. ".repeat(8)
        val lab = "Lab notes and gadgets discussed in detail for readers at home. ".repeat(8)
        val contents = "Article one .... 1\nArticle two .... 2\nArticle three .... 3\nArticle four .... 4"
        val bytes = epub(
            chapter("toc.xhtml", "Contents", "Index", contents),
            chapter("c1.xhtml", "Leaders", "Something Must Be Done", policy),
            chapter("c2.xhtml", "Science &amp; technology", "New Instruments", lab),
        )
        val book = EconomistImport.readEpub(bytes.inputStream())
        assertEquals(book.chunks.size, book.titles.size)
        assertEquals(listOf("Leaders", "Science & technology"), book.titles)
        assertTrue(book.chunks[0].contains("Policy brief"))
        assertFalse(book.titles.any { it.equals("Contents", ignoreCase = true) })
    }

    @Test
    fun pdfTitlesFollowPageArticles() {
        val contents = "Contents\nArticle one .... 1\nArticle two .... 2\nArticle three .... 3\nArticle four .... 4"
        val page1 = "Leaders\n\n" + ("Markets opened higher and stayed there for the week. ".repeat(6))
        val page2 = "The rally continued into a second page of the same piece. ".repeat(6)
        val page3 = "Finance & economics\n\n" + ("Bond yields stayed high across the week. ".repeat(6))
        val book = EconomistImport.readPages(listOf(contents, page1, page2, page3))
        assertEquals(book.chunks.size, book.titles.size)
        assertEquals(listOf("Leaders", "Finance & economics"), book.titles)
        assertFalse(book.titles.any { it.equals("Contents", ignoreCase = true) })
    }

    @Test
    fun pdfPagesStaySeparateArticles() {
        val page1 = "Leaders\n\n" + ("Markets opened higher and stayed there for the week. ".repeat(6))
        val page2 = "The rally continued into a second page of the same piece. ".repeat(6)
        val page3 = "Finance & economics\n\n" + ("Bond yields stayed high across the week. ".repeat(6))
        val chunks = EconomistImport.chunksFromPages(listOf(page1, page2, page3))
        assertTrue(chunks.size >= 2)
        assertTrue(chunks[0].contains("second page"))
        assertTrue(chunks.any { it.contains("Bond yields") && !it.contains("Markets opened") })
    }

    private fun chapter(
        name: String,
        heading: String,
        sub: String,
        body: String,
        documentTitle: String? = null,
    ): Pair<String, String> {
        val html = """
            <?xml version="1.0" encoding="utf-8"?>
            <html xmlns="http://www.w3.org/1999/xhtml"><head>${documentTitle?.let { "<title>$it</title>" } ?: ""}</head><body>
            <h1>$heading</h1>
            <h2>$sub</h2>
            <p>$body</p>
            </body></html>
        """.trimIndent()
        return name to html
    }

    private fun epub(vararg chapters: Pair<String, String>): ByteArray {
        val manifest = chapters.mapIndexed { i, (name, _) ->
            """<item id="c$i" href="$name" media-type="application/xhtml+xml"/>"""
        }.joinToString("")
        val spine = chapters.indices.joinToString("") { """<itemref idref="c$it"/>""" }
        val container = """
            <?xml version="1.0"?>
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
            <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
            </container>
        """.trimIndent()
        val opf = """
            <?xml version="1.0"?>
            <package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Economist</dc:title></metadata>
            <manifest>$manifest</manifest>
            <spine>$spine</spine>
            </package>
        """.trimIndent()
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            fun put(path: String, text: String) {
                zip.putNextEntry(ZipEntry(path))
                zip.write(text.toByteArray())
                zip.closeEntry()
            }
            put("mimetype", "application/epub+zip")
            put("META-INF/container.xml", container)
            put("OEBPS/content.opf", opf)
            chapters.forEach { (name, html) -> put("OEBPS/$name", html) }
        }
        return out.toByteArray()
    }
}
