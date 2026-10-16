package com.jarvis.ir.analysis

object AnalysisShare {
    private val sectionStart = Regex(
        """^(?:#+\s*)?(?:\*{1,2})?\s*(?:\d+|[一二三四五六七八九十百千]+)[.、]""",
    )

    fun paragraphs(text: String, includeTail: Boolean): List<String> {
        val sections = sections(text)
        if (includeTail || sections.isEmpty()) return sections
        return sections.dropLast(1)
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

    private fun sections(text: String): List<String> {
        val blocks = mutableListOf<MutableList<String>>()
        var headed = false
        for (line in text.replace("\r\n", "\n").lines()) {
            if (line.isBlank()) {
                if (blocks.isNotEmpty()) blocks.last().add("")
                continue
            }
            if (isSectionStart(line) && headed) blocks.add(mutableListOf())
            if (blocks.isEmpty()) blocks.add(mutableListOf())
            if (isSectionStart(line)) headed = true
            blocks.last().add(line.trim())
        }
        return blocks.map { join(it) }.filter { it.isNotEmpty() }
    }

    private fun isSectionStart(line: String): Boolean = sectionStart.containsMatchIn(line.trim())

    private fun join(lines: List<String>): String {
        val out = StringBuilder()
        var blank = false
        for (line in lines) {
            if (line.isBlank()) {
                blank = true
                continue
            }
            if (out.isNotEmpty()) out.append(if (blank) "\n\n" else "\n")
            blank = false
            out.append(line)
        }
        return out.toString()
    }
}
