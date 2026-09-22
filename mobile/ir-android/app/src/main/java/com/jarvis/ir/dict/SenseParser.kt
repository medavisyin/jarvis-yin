package com.jarvis.ir.dict

data class Sense(
    val id: Int,
    val pos: String?,
    val translation: String,
)

object SenseParser {
    private val numbered = Regex("""^\s*\d+\.\s*""")
    private val posPrefix = Regex(
        """^(n|v|vt|vi|adj|adv|prep|conj|pron|art|num|int|aux)\.\s+""",
        RegexOption.IGNORE_CASE,
    )

    private val inflection = Regex("""^\[时态\]""")
    private val examTag = Regex("""^\([^()\n]*\d+/\d+[^()\n]*\)$""")

    fun parse(translation: String, posField: String?): List<Sense> {
        val lines = translation.split('\n').map { it.trim() }.filter { it.isNotEmpty() && !isHiddenLine(it) }
        return lines.mapIndexed { idx, raw ->
            val unnumbered = raw.replace(numbered, "")
            val match = posPrefix.find(unnumbered)
            val pos = match?.groupValues?.get(1)?.lowercase()
            val text = if (match != null) {
                unnumbered.substring(match.range.last + 1).trim()
            } else {
                unnumbered.trim()
            }
            Sense(id = idx, pos = pos, translation = text)
        }
    }

    private fun isHiddenLine(line: String): Boolean =
        inflection.containsMatchIn(line) || examTag.matches(line)
}
