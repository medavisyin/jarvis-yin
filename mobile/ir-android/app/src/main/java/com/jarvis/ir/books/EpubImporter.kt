package com.jarvis.ir.books

import org.jsoup.Jsoup
import org.jsoup.parser.Parser
import java.io.InputStream
import java.util.zip.ZipInputStream

object EpubImporter {
    fun extractText(input: InputStream): String {
        val (opfDir, spineHrefs, files) = spine(input)
        val parts = spineHrefs.mapNotNull { href ->
            htmlBytes(files, opfDir, href)?.let { htmlToParagraphs(String(it, Charsets.UTF_8)) }
        }
        return parts.filter { it.isNotBlank() }.joinToString("\n\n")
    }

    fun extractSections(input: InputStream): List<BookSection> {
        val (opfDir, spineHrefs, files) = spine(input)
        return spineHrefs.mapNotNull { href ->
            val bytes = htmlBytes(files, opfDir, href) ?: return@mapNotNull null
            val html = String(bytes, Charsets.UTF_8)
            val text = htmlToParagraphs(html)
            if (text.isBlank()) return@mapNotNull null
            val heading = Jsoup.parse(html).body()?.selectFirst("h1, h2, h3")?.text()?.trim().orEmpty()
            val fallback = href.substringAfterLast('/').substringBeforeLast('.')
            BookSection(heading.ifBlank { fallback }, text)
        }
    }

    private data class Spine(
        val opfDir: String,
        val hrefs: List<String>,
        val files: Map<String, ByteArray>,
    )

    private fun spine(input: InputStream): Spine {
        val files = HashMap<String, ByteArray>()
        ZipInputStream(input).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (entry.isDirectory) continue
                files[entry.name] = zip.readBytes()
            }
        }
        val container = files.entries.firstOrNull { it.key.endsWith("META-INF/container.xml") }?.value
            ?: error("epub missing container.xml")
        val containerDoc = Jsoup.parse(String(container, Charsets.UTF_8), "", Parser.xmlParser())
        val rootPath = containerDoc.selectFirst("rootfile")?.attr("full-path")
            ?: error("epub missing rootfile")
        val opfBytes = files[rootPath] ?: error("epub missing opf $rootPath")
        val opfDir = rootPath.substringBeforeLast('/', "").let { if (it.isEmpty()) "" else "$it/" }
        val opf = Jsoup.parse(String(opfBytes, Charsets.UTF_8), "", Parser.xmlParser())
        val hrefById = opf.select("manifest > item").associate { it.attr("id") to it.attr("href") }
        val spineHrefs = opf.select("spine > itemref").mapNotNull { hrefById[it.attr("idref")] }
        return Spine(opfDir, spineHrefs, files)
    }

    private fun htmlBytes(files: Map<String, ByteArray>, opfDir: String, href: String): ByteArray? {
        val path = opfDir + href
        return files[path] ?: files.entries.firstOrNull { it.key.endsWith(href) }?.value
    }

    private fun htmlToParagraphs(html: String): String {
        val body = Jsoup.parse(html).body() ?: return ""
        val blockTags = setOf("h1", "h2", "h3", "h4", "p", "li")
        val blocks = body.select("h1, h2, h3, h4, p, li")
            .filter { element -> element.parents().none { it.tagName() in blockTags } }
            .map { it.text().trim() }
            .filter { it.isNotEmpty() }
        return if (blocks.isEmpty()) body.text() else blocks.joinToString("\n\n")
    }

    fun importEpub(input: InputStream, maxWords: Int = 400): List<String> =
        Chunker.chunk(extractText(input), maxWords)
}
