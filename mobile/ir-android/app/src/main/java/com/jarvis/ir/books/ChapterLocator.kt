package com.jarvis.ir.books

object ChapterLocator {
    fun pageForHeading(pages: List<String>, title: String): Int? {
        val want = key(title)
        if (want.isEmpty()) return null
        var fallback: Int? = null
        for ((index, text) in pages.withIndex()) {
            val lines = text.lineSequence().map { key(it) }.filter { it.isNotEmpty() }.toList()
            if (want !in lines) continue
            if (isContents(text)) {
                if (fallback == null) fallback = index
                continue
            }
            return index
        }
        return fallback
    }

    fun pageForChapter(pages: List<String>, title: String, excerpt: String = ""): Int? {
        pageForHeading(pages, title)?.let { return it }
        if (key(title).length > 24) {
            pageForExcerpt(pages, title)?.let { return it }
        }
        return pageForExcerpt(pages, excerpt)
    }

    private fun pageForExcerpt(pages: List<String>, excerpt: String): Int? {
        val needle = compact(excerpt).take(20)
        if (needle.length < 12) return null
        var fallback: Int? = null
        for ((index, text) in pages.withIndex()) {
            if (!compact(text).contains(needle)) continue
            if (isContents(text)) {
                if (fallback == null) fallback = index
                continue
            }
            return index
        }
        return fallback
    }

    private fun compact(value: String): String = value.replace(Regex("""\s+"""), "").lowercase()

    fun key(value: String): String {
        return value.replace(Regex("""\s*\(\d+\)\s*$"""), "")
            .trim()
            .replace(Regex("""\s+"""), " ")
            .lowercase()
    }

    private fun isContents(text: String): Boolean {
        val sample = text.trim().take(2000)
        if (Regex("""(?im)^\s*(table\s+of\s+contents|contents|index)\s*$""").containsMatchIn(sample)) {
            return true
        }
        val lines = sample.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }.toList()
        if (lines.size < 4) return false
        val dotted = lines.count { Regex("""\s+\d{1,3}$""").containsMatchIn(it) }
        return dotted >= 3 && dotted.toDouble() / lines.size >= 0.35
    }
}
