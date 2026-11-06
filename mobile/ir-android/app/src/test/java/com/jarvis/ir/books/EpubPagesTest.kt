package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class EpubPagesTest {
    @Test
    fun prepareKeepsImageAndDropsScript() {
        val root = Files.createTempDirectory("epub-pages").toFile()
        val zip = zip()
        val dest = File(root, "book")
        val spine = EpubPages.prepare(zip, dest)
        assertTrue(spine.contains("OEBPS/chap1.xhtml"))
        val html = File(dest, "OEBPS/chap1.xhtml").readText()
        assertFalse(html.contains("<script"))
        assertFalse(html.contains("onclick"))
        assertTrue(html.contains("harbour"))
        assertTrue(File(dest, "OEBPS/images/pic.png").isFile)
        root.deleteRecursively()
    }

    @Test
    fun coverKeepsSvgBoxAndCentersTheColumn() {
        val root = Files.createTempDirectory("epub-cover").toFile()
        val dest = File(root, "book")
        val spine = EpubPages.prepare(coverZip(), dest)
        assertTrue(spine.contains("titlepage.xhtml"))
        val html = File(dest, "titlepage.xhtml").readText()
        assertTrue(html.contains("viewBox="))
        assertTrue(html.contains("preserveAspectRatio="))
        assertTrue(html.contains("cover.jpeg"))
        assertTrue(html.contains("max-width: 40rem"))
        assertTrue(html.contains("font-size: 19px"))
        assertTrue(html.contains("#f6f1e7"))
        assertTrue(File(dest, "cover.jpeg").isFile)
        root.deleteRecursively()
    }

    @Test
    fun chapterDocumentsAreServedAsHtmlSoTheWebViewDoesNotUseXmlRules() {
        assertEquals("text/html", EpubPages.documentMime("OEBPS/xhtml/001_cover.xhtml", "application/xhtml+xml"))
        assertEquals("text/html", EpubPages.documentMime("/book/chap1.html", null))
        assertEquals("text/css", EpubPages.documentMime("OEBPS/styles/cover.css", "text/css"))
    }

    @Test
    fun chapterJumpUsesParagraphTextNotOnlyHeadings() {
        val cover = "<html><body><h1>Contents</h1><p>Chapter 2  12</p></body></html>"
        val chapter = "<html><body><p class='chtitle'>Chapter 2</p><p>The harbour was quiet that morning.</p></body></html>"
        val html = mapOf("cover.xhtml" to cover, "c2.xhtml" to chapter)
        val found = EpubPages.chapterFile(
            listOf("cover.xhtml", "c2.xhtml"),
            { html[it].orEmpty() },
            "Chapter 2",
            "The harbour was quiet",
        )
        assertEquals(1, found)
    }

    @Test
    fun rewrittenDocumentUsesAValidHttpStatus() {
        assertEquals(200, EpubPages.documentStatus(0))
        assertEquals(200, EpubPages.documentStatus(99))
        assertEquals(404, EpubPages.documentStatus(404))
    }

    private fun zip(): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            fun put(name: String, text: String) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(text.toByteArray())
                zip.closeEntry()
            }
            put(
                "META-INF/container.xml",
                """<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>""",
            )
            put(
                "OEBPS/content.opf",
                """<package><manifest><item id="c1" href="chap1.xhtml"/></manifest><spine><itemref idref="c1"/></spine></package>""",
            )
            put(
                "OEBPS/chap1.xhtml",
                """<html><body><p onclick="alert(1)">harbour</p><img src="images/pic.png"/><script>alert(1)</script></body></html>""",
            )
            zip.putNextEntry(ZipEntry("OEBPS/images/pic.png"))
            zip.write(byteArrayOf(1, 2, 3))
            zip.closeEntry()
        }
        return out.toByteArray()
    }

    private fun coverZip(): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        ZipOutputStream(out).use { zip ->
            fun put(name: String, text: String) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(text.toByteArray())
                zip.closeEntry()
            }
            put(
                "META-INF/container.xml",
                """<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>""",
            )
            put(
                "content.opf",
                """<package><manifest><item id="c" href="titlepage.xhtml"/></manifest><spine><itemref idref="c"/></spine></package>""",
            )
            put(
                "titlepage.xhtml",
                """<html xmlns="http://www.w3.org/1999/xhtml"><body><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 406 616" preserveAspectRatio="none" width="100%" height="100%"><image width="406" height="616" xlink:href="cover.jpeg"/></svg></body></html>""",
            )
            zip.putNextEntry(ZipEntry("cover.jpeg"))
            zip.write(byteArrayOf(-1, -40, -1))
            zip.closeEntry()
        }
        return out.toByteArray()
    }
}
