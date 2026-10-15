package com.jarvis.ir.books

import org.jsoup.Jsoup
import org.jsoup.parser.Parser
import java.net.URLDecoder

object BookChapters {
    data class Page(val title: String, val text: String)

    data class SpinePiece(val href: String, val text: String)

    data class TocRef(val title: String, val href: String)

    fun retitle(text: String, maxWords: Int = 400): List<Page>? {
        val pages = fromPlainText(text, maxWords)
        if (pages.none { it.title.isNotEmpty() }) return null
        return pages
    }

    fun fromPlainText(text: String, maxWords: Int = 400): List<Page> {
        val normalized = text.replace("\r\n", "\n").trim()
        if (normalized.isEmpty()) return emptyList()
        val lines = normalized.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.isEmpty()) return emptyList()
        val sections = contentsSplit(lines) ?: headingSplit(lines)
        if (sections == null || sections.count { it.title.isNotEmpty() } < 2) {
            return Chunker.chunk(normalized, maxWords).map { Page("", it) }
        }
        return sections.flatMap { section ->
            Chunker.chunk(section.text, maxWords).map { Page(section.title, it) }
        }
    }

    fun pagesFromSpine(pieces: List<SpinePiece>, toc: List<TocRef>, maxWords: Int): List<Page>? {
        val cuts = mutableListOf<Pair<Int, String>>()
        val used = mutableSetOf<Int>()
        for (ref in toc) {
            val index = pieces.indexOfFirst { sameHref(it.href, ref.href) }
            if (index < 0 || index in used) continue
            used.add(index)
            cuts.add(index to ref.title.trim())
        }
        if (cuts.size < 2) return null
        val ordered = cuts.sortedBy { it.first }
        val contentCuts = ordered.filter { (index, title) ->
            !isFrontMatter(pieces[index].href, title)
        }
        if (contentCuts.size < 2) return null
        val sections = mutableListOf<BookSection>()
        val firstCut = ordered.first().first
        if (firstCut > 0) {
            val front = pieces.subList(0, firstCut).joinToString("\n") { it.text }.trim()
            if (front.isNotEmpty()) sections.add(BookSection("", front))
        }
        for (index in ordered.indices) {
            val from = ordered[index].first
            val to = if (index + 1 < ordered.size) ordered[index + 1].first else pieces.size
            val body = pieces.subList(from, to).joinToString("\n") { it.text }.trim()
            if (body.isEmpty()) continue
            sections.add(BookSection(ordered[index].second, body))
        }
        if (sections.count { it.title.isNotEmpty() } < 2) return null
        return sections.flatMap { section ->
            Chunker.chunk(section.text, maxWords).map { Page(section.title, it) }
        }
    }

    fun pagesFromTocSources(
        pieces: List<SpinePiece>,
        sources: List<List<TocRef>>,
        maxWords: Int,
    ): List<Page>? {
        for (toc in sources) {
            val pages = pagesFromSpine(pieces, toc, maxWords) ?: continue
            return pages
        }
        return null
    }

    fun tocFromNcx(xml: String): List<TocRef> {
        val doc = Jsoup.parse(xml, "", Parser.xmlParser())
        return doc.select("navPoint").mapNotNull { point ->
            val title = point.selectFirst("navLabel")?.selectFirst("text")?.text()?.trim().orEmpty()
            val src = point.selectFirst("content")?.attr("src")?.trim().orEmpty()
            if (title.isEmpty() || src.isEmpty()) null else TocRef(title, src)
        }
    }

    fun tocFromNav(html: String): List<TocRef> {
        val doc = Jsoup.parse(html)
        val nav = doc.select("nav").firstOrNull { it.attr("epub:type").contains("toc") } ?: return emptyList()
        return nav.select("a").mapNotNull { link ->
            val title = link.text().trim()
            val href = link.attr("href").trim()
            if (title.isEmpty() || href.isEmpty()) null else TocRef(title, href)
        }
    }

    private fun contentsSplit(lines: List<String>): List<BookSection>? {
        val start = lines.indexOfFirst { contentsHeading.matches(it.replace(Regex("""\s+"""), " ").trim()) }
        if (start < 0) return null
        var cursor = start + 1
        val labels = mutableListOf<ContentLabel>()
        while (cursor < lines.size && shortEnough(lines[cursor])) {
            val forms = labelForms(lines[cursor])
            if (forms.isEmpty()) {
                cursor += 1
                continue
            }
            if (repeatsEarlier(forms, labels)) break
            labels.add(ContentLabel(forms))
            cursor += 1
        }
        if (labels.size < 2) return null
        val foundAt = mutableListOf<Int>()
        val foundLabels = mutableListOf<String>()
        var search = cursor
        for (label in labels) {
            val index = (search until lines.size).firstOrNull { line ->
                label.forms.any { sameTitle(lines[line], it) }
            } ?: continue
            foundAt.add(index)
            foundLabels.add(lines[index].replace(Regex("""\s+"""), " ").trim())
            search = index + 1
        }
        if (foundAt.size < 2) return null
        return sectionsAt(lines, foundAt, foundLabels)
    }

    private fun headingSplit(lines: List<String>): List<BookSection>? {
        val cuts = lines.mapIndexedNotNull { index, line ->
            if (isHeading(line)) index else null
        }
        if (cuts.size < 2) return null
        val titles = cuts.map { lines[it].replace("\n", " ").trim() }
        return sectionsAt(lines, cuts, titles)
    }

    private fun sectionsAt(
        lines: List<String>,
        cuts: List<Int>,
        titles: List<String>,
    ): List<BookSection> {
        val sections = mutableListOf<BookSection>()
        if (cuts.first() > 0) {
            sections.add(BookSection("", lines.subList(0, cuts.first()).joinToString("\n")))
        }
        for (index in cuts.indices) {
            val from = cuts[index]
            val to = if (index + 1 < cuts.size) cuts[index + 1] else lines.size
            sections.add(BookSection(titles[index], lines.subList(from, to).joinToString("\n")))
        }
        return sections
    }

    private fun isHeading(line: String): Boolean {
        val flat = line.replace("\n", " ").trim()
        if (flat.isEmpty() || !shortEnough(flat)) return false
        if (chineseHeading.matches(flat)) return true
        val match = chapterHeading.matchEntire(flat) ?: return false
        val token = match.groupValues[1]
        if (token.all { it.isDigit() }) return true
        return token.all { it.isUpperCase() } && isRoman(token)
    }

    private fun isRoman(token: String): Boolean {
        if (token.isEmpty()) return false
        return token.matches(roman)
    }

    private fun labelForms(line: String): List<String> {
        val raw = line.trim()
        if (raw.isEmpty()) return emptyList()
        val full = raw.replace(Regex("""\s+"""), " ")
        val extras = mutableListOf<String>()
        val dotted = raw.replace(Regex("""(?:\s*[.·]){2,}\s*\d+\s*$"""), "").trim()
        if (dotted != raw) extras.add(dotted.replace(Regex("""\s+"""), " "))
        val wideSpace = Regex("""^(.*?)\s{2,}\d+\s*$""").find(raw)
        if (wideSpace != null) extras.add(wideSpace.groupValues[1].trim().replace(Regex("""\s+"""), " "))
        val twoNumbers = Regex("""^(.*\d)\s+\d+\s*$""").find(full)
        if (twoNumbers != null) extras.add(twoNumbers.groupValues[1].trim())
        return (listOf(full) + extras).map { it.trim() }.filter { it.isNotEmpty() }.distinct()
    }

    private fun repeatsEarlier(forms: List<String>, labels: List<ContentLabel>): Boolean {
        val newLongest = forms.maxBy { it.length }
        return labels.any { earlier ->
            val oldLongest = earlier.forms.maxBy { it.length }
            forms.any { right ->
                earlier.forms.any { left ->
                    if (!sameTitle(left, right)) return@any false
                    val shared = left
                    val stub = shared.length < newLongest.length &&
                        shared.length < oldLongest.length &&
                        newLongest.startsWith(shared) &&
                        oldLongest.startsWith(shared)
                    !stub
                }
            }
        }
    }

    private fun shortEnough(line: String): Boolean {
        val cjk = line.count { it.code in 0x4E00..0x9FFF }
        val spaced = line.split(Regex("""\s+""")).count { it.isNotEmpty() }
        return if (cjk > spaced * 2) cjk <= CHINESE_HEADING_CHARS else spaced <= HEADING_WORDS
    }

    private fun sameTitle(paragraph: String, label: String): Boolean {
        val left = paragraph.replace(Regex("""\s+"""), " ").trim()
        val right = label.replace(Regex("""\s+"""), " ").trim()
        return left.equals(right, ignoreCase = true)
    }

    private fun isFrontMatter(href: String, title: String): Boolean {
        val blob = "$href $title".replace(Regex("""[^A-Za-z0-9]+"""), " ")
        return frontMatter.containsMatchIn(blob)
    }

    private fun sameHref(spineHref: String, tocHref: String): Boolean {
        val left = normalizeHref(spineHref) ?: return false
        val right = normalizeHref(tocHref) ?: return false
        return left == right || left.endsWith("/$right") || right.endsWith("/$left")
    }

    private fun normalizeHref(href: String): String? {
        val raw = href.substringBefore('#').substringBefore('?').trim()
        val decoded = decodePercent(raw) ?: return null
        return decoded.trim().trimStart('.', '/').replace('\\', '/')
    }

    private fun decodePercent(raw: String): String? {
        return try {
            URLDecoder.decode(raw.replace("+", "%2B"), Charsets.UTF_8.name())
        } catch (_: IllegalArgumentException) {
            null
        }
    }

    private data class ContentLabel(val forms: List<String>)

    private const val HEADING_WORDS = 20
    private const val CHINESE_HEADING_CHARS = 40

    private val contentsHeading = Regex("""(?i)^(table\s+of\s+contents|contents|目录)$""")
    private val chapterHeading = Regex(
        """^(?i:chapter)\s+(\d+|[IVXLCDM]+)(?:\s*[:：—–\-]\s*\S.*|\s+[A-Z][A-Za-z0-9'’\-]*(?:\s+[A-Z][A-Za-z0-9'’\-]*)*)?$""",
    )
    private val chineseHeading = Regex(
        """^第\s*[0-9０-９一二三四五六七八九十百千零]+\s*章(?:\s*[:：.\-—–]\s*\S.*|\s+\S.*)?$""",
    )
    private val roman = Regex("^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
    private val frontMatter = Regex("""(?i)\b(cover|titlepage|title page|copyright|contents|toc|imprint)\b""")
}
