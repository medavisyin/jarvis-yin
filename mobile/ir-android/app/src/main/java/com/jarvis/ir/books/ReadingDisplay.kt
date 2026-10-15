package com.jarvis.ir.books

object ReadingDisplay {
    data class Passage(val heading: String?, val body: String)

    data class Chrome(val section: String?, val article: String?)

    fun shelfLine(pages: List<ReadingGroups.Page>, index: Int, read: Set<String>): String? {
        if (pages.isEmpty()) return null
        if (pages.any { it.magazine }) {
            val count = pages
                .filter { it.article.isNotEmpty() && it.readKey in read }
                .map { it.readKey }
                .distinct()
                .size
            return "已读 $count 篇"
        }
        val page = pages.getOrNull(index) ?: return null
        if (page.article.isEmpty()) return null
        return page.label(index)
    }

    fun show(page: ReadingGroups.Page, text: String): Passage {
        if (page.magazine) return Passage(null, stripLead(text, page.section))
        if (page.part == 1 && page.article.isNotEmpty()) return liftHeading(text, page.article)
        return Passage(null, text)
    }

    fun chrome(page: ReadingGroups.Page, index: Int): Chrome {
        if (page.magazine) {
            return Chrome(
                section = page.section.ifEmpty { null },
                article = if (page.article.isNotEmpty()) page.label(index) else null,
            )
        }
        if (page.parts > 1 && page.article.isNotEmpty()) return Chrome(null, page.label(index))
        return Chrome(null, null)
    }

    fun allowsEdge(magazine: Boolean): Boolean = !magazine

    fun edgeDelta(x: Float, width: Float, band: Float): Int? {
        if (width <= 0f || band <= 0f) return null
        if (x < band) return -1
        if (x > width - band) return 1
        return null
    }

    fun turnedIndex(current: Int, delta: Int, count: Int): Int? {
        if (count <= 1) return null
        val next = current + delta
        if (next !in 0 until count) return null
        return next
    }

    private val months =
        "january|february|march|april|may|june|july|august|september|october|november|december"

    private val magazineNameLine = Regex(
        """^(?:\d+\s+)?(?:the\s+)?(?:new\s+yorker|economist|wired)\b[\s\p{Punct}]*$""",
        RegexOption.IGNORE_CASE,
    )

    private val datePriceLine = Regex(
        """^(?:$months)\s+\d{1,2},\s*\d{4}\s*PRICE\b(?:\s*\$?\d+(?:\.\d+)?)?[\s\p{Punct}]*$""",
        RegexOption.IGNORE_CASE,
    )

    private val yearPriceLine = Regex(
        """^\d{4}\s*PRICE\b(?:\s*\$?\d+(?:\.\d+)?)?[\s\p{Punct}]*$""",
        RegexOption.IGNORE_CASE,
    )

    private val coverLine = Regex(
        """^(?:cover|contents|table\s+of\s+contents|masthead)\b[\s\p{Punct}]*$""",
        RegexOption.IGNORE_CASE,
    )

    private val datePricePrefix = Regex(
        """^(?:$months)\s+\d{1,2},\s*\d{4}\s*PRICE\s*\$?\d+(?:\.\d+)?\s*""",
        RegexOption.IGNORE_CASE,
    )

    private val spaces = Regex("""\s+""")

    private fun stripLead(text: String, section: String): String {
        val lines = text.replace("\r\n", "\n").split('\n')
        val start = lines.indexOfFirst { it.trim().isNotEmpty() }.coerceAtLeast(0)
        var index = start
        while (index < lines.size) {
            val trimmed = lines[index].trim()
            if (trimmed.isEmpty() || isFurniture(trimmed) || sameLine(trimmed, section)) {
                index += 1
                continue
            }
            val stripped = stripPricePrefix(trimmed)
            if (stripped.isEmpty() || sameLine(stripped, section)) {
                index += 1
                continue
            }
            if (index == start && stripped == trimmed) return text
            val kept = ArrayList<String>()
            kept.add(if (stripped == trimmed) lines[index] else stripped)
            if (index + 1 < lines.size) kept.addAll(lines.subList(index + 1, lines.size))
            val body = kept.joinToString("\n").trim()
            return body.ifEmpty { text }
        }
        return text
    }

    private fun liftHeading(text: String, article: String): Passage {
        val lines = text.replace("\r\n", "\n").split('\n')
        val first = lines.indexOfFirst { it.trim().isNotEmpty() }
        if (first >= 0 && sameLine(lines[first], article)) {
            val body = lines.drop(first + 1).joinToString("\n").trim()
            return Passage(lines[first].trim(), body)
        }
        return Passage(article, text)
    }

    private fun isFurniture(line: String): Boolean =
        magazineNameLine.matches(line) ||
            datePriceLine.matches(line) ||
            yearPriceLine.matches(line) ||
            coverLine.matches(line)

    private fun stripPricePrefix(line: String): String {
        val match = datePricePrefix.find(line) ?: return line
        if (match.range.first != 0) return line
        return line.substring(match.range.last + 1).trim()
    }

    private fun sameLine(line: String, title: String): Boolean {
        if (title.isEmpty()) return false
        return spaces.replace(line.trim(), " ").equals(spaces.replace(title.trim(), " "), ignoreCase = true)
    }
}
