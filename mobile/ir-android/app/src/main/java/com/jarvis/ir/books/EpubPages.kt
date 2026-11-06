package com.jarvis.ir.books

import org.jsoup.Jsoup
import org.jsoup.parser.Parser
import java.io.ByteArrayInputStream
import java.io.File
import java.util.zip.ZipInputStream

object EpubPages {
    fun prepare(bytes: ByteArray, dest: File): List<String> {
        if (dest.exists()) dest.deleteRecursively()
        dest.mkdirs()
        val files = LinkedHashMap<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (entry.isDirectory) continue
                val name = entry.name.replace('\\', '/').trimStart('/')
                if (name.isEmpty() || name.split('/').any { it == ".." }) continue
                files[name] = zip.readBytes()
            }
        }
        val spine = spineHrefs(files)
        for ((name, data) in files) {
            val out = safeChild(dest, name) ?: continue
            out.parentFile?.mkdirs()
            val body = if (name.endsWith(".xhtml") || name.endsWith(".html") || name.endsWith(".htm")) {
                stripScripts(String(data, Charsets.UTF_8)).toByteArray()
            } else {
                data
            }
            out.writeBytes(body)
        }
        return spine
    }

    fun documentMime(path: String, detected: String?): String? {
        val ext = path.substringAfterLast('.', "").lowercase()
        if (ext == "xhtml" || ext == "html" || ext == "htm") return "text/html"
        return detected
    }

    fun documentStatus(statusCode: Int): Int = if (statusCode in 100..599) statusCode else 200

    fun visibleText(html: String): String {
        val doc = Jsoup.parse(html)
        val blocks = doc.select("h1, h2, h3, h4, h5, h6, p, li, div").filter { block ->
            block.children().none { child ->
                child.tagName() in setOf("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div")
            }
        }
        val lines = if (blocks.isEmpty()) listOf(doc.body()?.text().orEmpty()) else blocks.map { it.text() }
        return lines.filter { it.isNotBlank() }.joinToString("\n")
    }

    fun chapterFile(pages: List<String>, html: (String) -> String, title: String, excerpt: String): Int? {
        val texts = pages.map { href -> visibleText(html(href)) }
        return ChapterLocator.pageForChapter(texts, title, excerpt)
    }

    fun stripScripts(html: String): String {
        val doc = Jsoup.parse(html)
        doc.select("script, iframe, object, embed, base, form").remove()
        for (element in doc.allElements) {
            val names = element.attributes().map { it.key }
            for (name in names) {
                if (name.startsWith("on", ignoreCase = true)) element.removeAttr(name)
            }
        }
        doc.head().appendElement("style").text(columnCss)
        return restoreSvgAttrs(doc.outerHtml())
    }

    private const val columnCss =
        "html { background: #f6f1e7 !important; } " +
            "body { box-sizing: border-box; max-width: 40rem !important; width: min(100%, 40rem); margin-left: auto !important; margin-right: auto !important; padding: 1.4rem 1.5rem 3rem !important; background: #f6f1e7 !important; color: #1d1d1f; font-family: Georgia, Palatino, \"Songti SC\", \"Noto Serif CJK SC\", serif !important; font-size: 19px !important; line-height: 1.55 !important; text-align: justify; hyphens: auto; -webkit-hyphens: auto; } " +
            "p, li { font-family: inherit !important; font-size: 19px !important; line-height: 1.55 !important; text-align: justify; } " +
            "h1, h2, h3 { font-family: sans-serif !important; font-weight: 600; line-height: 1.25; text-align: left; } " +
            "h1 { font-size: 28px !important; } h2 { font-size: 23px !important; } " +
            "img, svg, video { display: block; max-width: 100%; height: auto; margin-left: auto; margin-right: auto; }"

    private fun restoreSvgAttrs(html: String): String {
        var out = html
        for ((lower, camel) in listOf("viewbox" to "viewBox", "preserveaspectratio" to "preserveAspectRatio")) {
            out = Regex("""\b$lower=""", RegexOption.IGNORE_CASE).replace(out, "$camel=")
        }
        return out
    }

    private fun spineHrefs(files: Map<String, ByteArray>): List<String> {
        val container = files.entries.firstOrNull { it.key.endsWith("META-INF/container.xml") }?.value
            ?: return files.keys.filter { it.endsWith(".xhtml") || it.endsWith(".html") }
        val root = Jsoup.parse(String(container, Charsets.UTF_8), "", Parser.xmlParser())
            .selectFirst("rootfile")?.attr("full-path")
            ?: return emptyList()
        val opfBytes = files[root] ?: return emptyList()
        val opfDir = root.substringBeforeLast('/', "").let { if (it.isEmpty()) "" else "$it/" }
        val opf = Jsoup.parse(String(opfBytes, Charsets.UTF_8), "", Parser.xmlParser())
        val hrefById = opf.select("manifest > item").associate { it.attr("id") to it.attr("href") }
        return opf.select("spine > itemref").mapNotNull { ref ->
            val href = hrefById[ref.attr("idref")] ?: return@mapNotNull null
            opfDir + href
        }
    }

    private fun safeChild(dest: File, name: String): File? {
        val child = File(dest, name)
        val root = dest.canonicalFile
        val resolved = child.canonicalFile
        if (resolved != root && !resolved.path.startsWith(root.path + File.separator)) return null
        return child
    }
}
