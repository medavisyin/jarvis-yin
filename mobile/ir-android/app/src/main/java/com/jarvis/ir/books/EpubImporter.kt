package com.jarvis.ir.books

import org.jsoup.Jsoup
import org.jsoup.parser.Parser
import java.io.InputStream
import java.util.zip.ZipInputStream

object EpubImporter {
    fun extractText(input: InputStream): String {
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
        val parts = spineHrefs.mapNotNull { href ->
            val path = opfDir + href
            val html = files[path] ?: files.entries.firstOrNull { it.key.endsWith(href) }?.value
            html?.let { htmlToParagraphs(String(it, Charsets.UTF_8)) }
        }
        return parts.filter { it.isNotBlank() }.joinToString("\n\n")
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
