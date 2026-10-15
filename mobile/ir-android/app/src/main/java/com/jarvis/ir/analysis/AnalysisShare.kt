package com.jarvis.ir.analysis

object AnalysisShare {
    private val gap = Regex("""\n[ \t]*\n""")
    private val closedTail = Regex("""\n[ \t]*\n[ \t]*$""")

    fun paragraphs(text: String, includeTail: Boolean): List<String> {
        val normalized = text.replace("\r\n", "\n")
        val parts = normalized.split(gap).map { it.trim() }.filter { it.isNotEmpty() }
        if (parts.isEmpty()) return emptyList()
        if (includeTail || closedTail.containsMatchIn(normalized)) return parts
        return parts.dropLast(1)
    }

    fun openTail(text: String): String {
        val all = paragraphs(text, includeTail = true)
        val closed = paragraphs(text, includeTail = false)
        if (all.size == closed.size) return ""
        return all.last()
    }

    fun body(title: String, paragraph: String): String {
        val name = title.trim()
        return if (name.isEmpty()) paragraph else "$name\n$paragraph"
    }
}
