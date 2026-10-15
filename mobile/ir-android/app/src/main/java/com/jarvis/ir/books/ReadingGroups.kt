package com.jarvis.ir.books

object ReadingGroups {
    data class Page(
        val section: String,
        val article: String,
        val part: Int,
        val parts: Int,
        val magazine: Boolean,
    ) {
        val readKey: String
            get() = if (section.isEmpty()) article else "$section\u0000$article"

        val isLastPart: Boolean
            get() = magazine && article.isNotEmpty() && part == parts

        fun label(index: Int): String {
            if (article.isEmpty()) return "第 ${index + 1} 段"
            if (parts > 1) return "$article · $part/$parts"
            return article
        }
    }

    sealed class MenuRow {
        abstract val text: String
        data class Header(override val text: String) : MenuRow()
        data class Item(val index: Int, override val text: String) : MenuRow()
    }

    fun pages(titles: List<String>, texts: List<String>): List<Page> {
        val count = maxOf(titles.size, texts.size)
        if (count == 0) return emptyList()
        val found = linkedSetOf<String>()
        val sections = MutableList(count) { "" }
        var current = ""
        for (index in 0 until count) {
            val seen = sectionOnPage(titles.getOrElse(index) { "" }, texts.getOrElse(index) { "" })
            if (seen != null) {
                current = seen
                found.add(seen)
            }
            sections[index] = current
        }
        val magazine = found.size >= 2
        val articles = (0 until count).map { index ->
            val title = titles.getOrElse(index) { "" }.trim()
            if (magazine) stripPart(title) else title
        }
        val part = IntArray(count)
        val partCount = IntArray(count)
        var index = 0
        while (index < count) {
            val article = articles[index]
            val section = if (magazine) sections[index] else ""
            var end = index + 1
            if (article.isNotEmpty()) {
                while (
                    end < count &&
                    articles[end] == article &&
                    (if (magazine) sections[end] else "") == section
                ) {
                    end += 1
                }
            }
            val size = end - index
            for (cursor in index until end) {
                part[cursor] = cursor - index + 1
                partCount[cursor] = size
            }
            index = end
        }
        return (0 until count).map { cursor ->
            Page(
                section = if (magazine) sections[cursor] else "",
                article = articles[cursor],
                part = part[cursor],
                parts = partCount[cursor],
                magazine = magazine,
            )
        }
    }

    fun menu(pages: List<Page>, read: Set<String>): List<MenuRow> {
        val rows = mutableListOf<MenuRow>()
        var lastSection = ""
        pages.forEachIndexed { index, page ->
            if (page.magazine && page.section.isNotEmpty() && page.section != lastSection) {
                rows.add(MenuRow.Header(page.section))
                lastSection = page.section
            }
            val marked = page.magazine && page.article.isNotEmpty() && page.readKey in read
            val text = if (marked) "${page.label(index)}  已读" else page.label(index)
            rows.add(MenuRow.Item(index, text))
        }
        return rows
    }

    fun nextStart(pages: List<Page>, index: Int): Int? {
        val current = pages.getOrNull(index) ?: return null
        if (!current.magazine) return null
        return (index + 1 until pages.size).firstOrNull { cursor ->
            val page = pages[cursor]
            page.article.isNotEmpty() && page.readKey != current.readKey
        }
    }

    private val sectionNames = listOf(
        "Leaders",
        "Briefing",
        "United States",
        "The Americas",
        "Asia",
        "China",
        "Middle East & Africa",
        "Middle East",
        "Europe",
        "Britain",
        "International",
        "Business",
        "Finance & economics",
        "Science & technology",
        "Books & arts",
        "Graphic detail",
        "Obituary",
    )

    private val partSuffix = Regex("""\s*\(\d+\)\s*$""")
    private val spaces = Regex("""\s+""")
    private val ampersand = Regex("""\s*&\s*""")

    private fun stripPart(title: String): String = partSuffix.replace(title.trim(), "").trim()

    private fun canonicalSection(line: String): String? {
        val stripped = ampersand.replace(spaces.replace(line.trim(), " "), " & ")
        if (stripped.isEmpty()) return null
        return sectionNames.firstOrNull { it.equals(stripped, ignoreCase = true) }
    }

    private fun sectionOnPage(title: String, text: String): String? {
        canonicalSection(title)?.let { return it }
        val lines = text.replace("\r\n", "\n").split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        return lines.take(3).firstNotNullOfOrNull { canonicalSection(it) }
    }
}
