package com.jarvis.ir.books

data class BookSection(val title: String, val text: String)

data class MagazineChunk(val title: String, val text: String, val isToc: Boolean)

object MagazineChunker {
    private val tocHeading = Regex(
        """(?im)^\s*(table\s+of\s+contents|contents|index|目錄|目录)\s*$""",
    )
    private val pageDots = Regex("""\.{3,}\s*\d+\s*$""")
    private val trailingPage = Regex("""\s+\d{1,3}$""")
    private val navTrail = Regex(
        """(?:\s*\|\s*(?:Next|Previous|Section\s+menu|Main\s+menu|章节菜单|主菜单)\s*)+\s*\|?\s*$""",
        RegexOption.IGNORE_CASE,
    )
    private val weakTitle = Regex(
        """^(cover|contents|table\s+of\s+contents|magazine\s+articles|masthead|toc|copyright|imprint|illustration|photograph|photo\s*credit)\b|章节菜单|主菜单|\d{4}\s*PRICE|PRICE\s*\$|^\d*\s*the\s+new\s+yorker\b|the\s+new\s+yorker,\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b""",
        RegexOption.IGNORE_CASE,
    )
    private val sectionName = Regex(
        """^(Leaders|Briefing|United States|The Americas|Asia|China|Middle East(?:\s*&\s*Africa)?|Europe|Britain|International|Business|Finance\s*&\s*economics|Science\s*&\s*technology|Books\s*&\s*arts|Graphic detail|Obituary)$""",
        RegexOption.IGNORE_CASE,
    )
    private val pageMasthead = Regex(
        """^(?:\d+\s+)?(?:the\s+)?(?:new\s+yorker|economist|wired)\b|^\d{4}\s*PRICE\b|^(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s*\d{4}\s*PRICE\b|^(?:cover|contents|table\s+of\s+contents|masthead)\b""",
        RegexOption.IGNORE_CASE,
    )
    private val datePricePrefix = Regex(
        """^[A-Z]+\s+\d{1,2},\s*\d{4}\s*PRICE\s*\$?\d+(?:\.\d+)?\s*""",
        RegexOption.IGNORE_CASE,
    )
    private val smallWords = setOf(
        "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "from", "vs", "versus",
    )

    fun chunkText(text: String): List<MagazineChunk> {
        if (text.isBlank()) return emptyList()
        val lines = text.lines()
        val byIndex = linkedMapOf(0 to false)
        for (i in 1 until lines.size) {
            if (lines[i - 1].isNotBlank()) continue
            val (isHeading, hard) = isMagazineHeading(lines[i])
            if (isHeading) byIndex[i] = byIndex[i] == true || hard
        }
        val ordered = byIndex.entries.toList()
        val segments = ordered.mapIndexed { bi, (start, hard) ->
            val end = if (bi + 1 < ordered.size) ordered[bi + 1].key else lines.size
            val block = lines.subList(start, end)
            val title = block.firstOrNull { it.isNotBlank() }?.trim() ?: "Article ${bi + 1}"
            val body = block.joinToString("\n").trim()
            Triple(title, body, hard)
        }.filter { it.second.isNotEmpty() }

        val chunks = mutableListOf<MagazineChunk>()
        var pendingTitle = ""
        val pending = mutableListOf<String>()

        fun flush(minWords: Int = 25) {
            val textOut = pending.joinToString("\n\n").trim()
            pending.clear()
            if (textOut.isEmpty()) return
            if (wordCount(textOut) < minWords && !isTocText(textOut)) return
            chunks.add(
                MagazineChunk(
                    title = pendingTitle.ifBlank { "Article ${chunks.size + 1}" },
                    text = textOut,
                    isToc = isTocText(textOut),
                ),
            )
            pendingTitle = ""
        }

        for ((title, body, hardStart) in segments) {
            val words = wordCount(body)
            if (pending.isEmpty()) {
                pendingTitle = title
                pending.add(body)
                continue
            }
            val pendingWords = wordCount(pending.joinToString(" "))
            if (hardStart && pendingWords >= 25) {
                flush()
                pendingTitle = title
                pending.add(body)
                continue
            }
            if (pendingWords >= 40 && words >= 30) {
                flush()
                pendingTitle = title
                pending.add(body)
            } else {
                pending.add(body)
            }
        }
        flush()
        if (chunks.isEmpty()) {
            return Chunker.chunk(text, maxWords = 900).mapIndexed { index, part ->
                MagazineChunk("Article ${index + 1}", part, isTocText(part))
            }
        }
        return chunks
    }

    fun fromSections(sections: List<BookSection>): List<MagazineChunk> {
        val chunks = mutableListOf<MagazineChunk>()
        for (section in sections) {
            val text = section.text.trim()
            if (text.isEmpty()) continue
            var title = normalizeTitle(section.title).ifBlank { "Article ${chunks.size + 1}" }
            val words = wordCount(text)
            val weak = isWeakTitle(title) || isTocText(text)
            if (weak && words >= 60) {
                val sub = chunkText(text)
                if (sub.size >= 2) {
                    chunks.addAll(sub.map { chunk -> retitleWeak(chunk, chunk.text) })
                    continue
                }
                if (sub.isNotEmpty()) {
                    val cand = retitleWeak(sub[0], text)
                    if (!isWeakTitle(cand.title)) {
                        chunks.add(cand)
                        continue
                    }
                }
                val parts = splitWords(text, 1200)
                parts.forEachIndexed { j, part ->
                    var partTitle = headlineFromText(part).ifBlank { "Article ${chunks.size + 1}" }
                    if (parts.size > 1) partTitle = "$partTitle (${j + 1})"
                    chunks.add(MagazineChunk(partTitle, part, isTocText(part)))
                }
                continue
            }
            if (weak) {
                val better = headlineFromText(text)
                if (better.isNotEmpty()) title = better
            }
            chunks.add(MagazineChunk(title, text, isTocText(text)))
        }
        return polish(splitOversized(chunks))
    }

    fun fromPages(pages: List<String>): List<MagazineChunk> {
        if (pages.isEmpty()) return emptyList()
        val grouped = pageChunks(pages)
        val raw = grouped.ifEmpty {
            chunkText(pages.filter { it.isNotBlank() }.joinToString("\n\n"))
        }
        return polish(splitOversized(raw))
    }

    fun selected(chunks: List<MagazineChunk>): List<MagazineChunk> {
        val readable = chunks.filter { !it.isToc && it.text.isNotBlank() }
        return readable.ifEmpty { chunks.filter { it.text.isNotBlank() } }
    }

    fun passages(chunks: List<MagazineChunk>): List<String> {
        val chosen = selected(chunks)
        return chosen.map { chunk ->
            val title = chunk.title.trim()
            val body = chunk.text.trim()
            if (title.isEmpty() || body.startsWith(title)) body else "$title\n\n$body"
        }
    }

    private fun pageChunks(pages: List<String>): List<MagazineChunk> {
        val boundaries = mutableListOf<Pair<Int, String>>()
        pages.forEachIndexed { index, page ->
            val heading = headingFromPage(page)
            if (heading.isNotEmpty()) boundaries.add(index to heading)
        }
        if (boundaries.isEmpty()) return emptyList()
        val merged = mutableListOf<Pair<Int, String>>()
        for ((start, title) in boundaries) {
            if (merged.lastOrNull()?.second.equals(title, ignoreCase = true)) continue
            merged.add(start to title)
        }
        val chunks = mutableListOf<MagazineChunk>()
        val firstStart = merged[0].first
        if (firstStart > 0) {
            val lead = pages.take(firstStart).filter { it.isNotBlank() }.joinToString("\n\n").trim()
            if (lead.isNotEmpty() && (isTocText(lead) || wordCount(lead) >= 25)) {
                chunks.add(MagazineChunk(if (isTocText(lead)) "Contents" else "Front matter", lead, isTocText(lead)))
            }
        }
        merged.forEachIndexed { i, (start, title) ->
            val end = if (i + 1 < merged.size) merged[i + 1].first else pages.size
            val text = pages.subList(start, end).filter { it.isNotBlank() }.joinToString("\n\n").trim()
            if (text.isNotEmpty()) {
                chunks.add(MagazineChunk(title, text, isTocText(text)))
            }
        }
        return chunks
    }

    private fun headingFromPage(page: String): String {
        val nonempty = page.lines().map { it.trim() }.filter { it.isNotEmpty() }
        var i = 0
        while (i < nonempty.size && (
                pageMasthead.containsMatchIn(nonempty[i]) ||
                    isWeakTitle(nonempty[i]) ||
                    nonempty[i].matches(Regex("""\d{1,3}"""))
                )
        ) {
            i += 1
        }
        for (line in nonempty.drop(i).take(6)) {
            if (looksLikePageHeading(line)) return line
        }
        return ""
    }

    private fun looksLikePageHeading(line: String): Boolean {
        val stripped = line.replace(Regex("""\s+"""), " ").trim()
        if (stripped.isEmpty() || stripped.length > 80) return false
        if (stripped.last() in setOf('.', ';', ',', ':', '…')) return false
        if (pageMasthead.containsMatchIn(stripped) || isWeakTitle(stripped)) return false
        val words = stripped.split(" ")
        if (words.size !in 1..12) return false
        if (sectionName.matches(stripped)) return true
        var caps = 0
        var considered = 0
        for (word in words) {
            val core = word.filter { it.isLetter() || it == '\'' }
            if (core.isEmpty()) continue
            considered += 1
            if (core.lowercase() in smallWords || core[0].isUpperCase() || core.all { it.isUpperCase() }) {
                caps += 1
            }
        }
        if (caps < maxOf(1, words.size - 1)) return false
        val letters = stripped.filter { it.isLetter() }
        if (letters.isNotEmpty() && letters.count { it.isUpperCase() }.toDouble() / letters.length < 0.12) {
            return false
        }
        return considered > 0
    }

    private fun polish(chunks: List<MagazineChunk>): List<MagazineChunk> =
        chunks.mapIndexed { index, chunk ->
            val match = Regex("""\s*(\(\d+\))\s*$""").find(chunk.title)
            val suffix = match?.groupValues?.get(1)?.let { " $it" } ?: ""
            val core = if (match == null) chunk.title else chunk.title.removeRange(match.range).trim()
            if (!isWeakTitle(core)) chunk else {
                val better = headlineFromText(chunk.text)
                val title = if (better.isNotEmpty()) better + suffix else "Article ${index + 1}"
                chunk.copy(title = title)
            }
        }

    private fun retitleWeak(chunk: MagazineChunk, source: String): MagazineChunk {
        if (!isWeakTitle(chunk.title)) return chunk
        val better = headlineFromText(source)
        return if (better.isNotEmpty()) chunk.copy(title = better) else chunk
    }

    private fun splitOversized(chunks: List<MagazineChunk>, maxWords: Int = 1200): List<MagazineChunk> {
        val out = mutableListOf<MagazineChunk>()
        for (chunk in chunks) {
            if (wordCount(chunk.text) <= maxWords) {
                out.add(chunk)
                continue
            }
            val parts = splitWords(chunk.text, maxWords)
            parts.forEachIndexed { j, part ->
                var title = if (isWeakTitle(chunk.title)) headlineFromText(part).ifBlank { chunk.title } else chunk.title
                if (parts.size > 1) title = "$title (${j + 1})"
                out.add(MagazineChunk(title, part, chunk.isToc))
            }
        }
        return out
    }

    private fun splitWords(text: String, maxWords: Int): List<String> {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return emptyList()
        if (wordCount(trimmed) <= maxWords) return listOf(trimmed)
        val parts = mutableListOf<String>()
        val buf = mutableListOf<String>()
        var bufWords = 0
        for (para in trimmed.split(Regex("""\n\s*\n+"""))) {
            val p = para.trim()
            if (p.isEmpty()) continue
            val pw = wordCount(p)
            if (pw > maxWords) {
                if (buf.isNotEmpty()) {
                    parts.add(buf.joinToString("\n\n"))
                    buf.clear()
                    bufWords = 0
                }
                val words = p.split(Regex("""\s+""")).filter { it.isNotEmpty() }
                var i = 0
                while (i < words.size) {
                    parts.add(words.subList(i, minOf(i + maxWords, words.size)).joinToString(" "))
                    i += maxWords
                }
                continue
            }
            if (buf.isNotEmpty() && bufWords + pw > maxWords) {
                parts.add(buf.joinToString("\n\n"))
                buf.clear()
                bufWords = 0
            }
            buf.add(p)
            bufWords += pw
        }
        if (buf.isNotEmpty()) parts.add(buf.joinToString("\n\n"))
        return parts.ifEmpty { listOf(trimmed) }
    }

    private fun headlineFromText(text: String): String {
        for (line in text.lines()) {
            val raw = line.replace(Regex("""\s+"""), " ").trim()
            if (raw.length < 10) continue
            val stripped = stripMasthead(raw)
            if (stripped.length < 10) continue
            if (isWeakTitle(stripped) && stripped.split(" ").size <= 14) continue
            if (stripped.length > 110) {
                val words = stripped.split(" ")
                if (words.size >= 5) {
                    val probe = words.take(12).joinToString(" ").trim(' ', ',', ';', '-')
                    if (probe.length >= 15 && !isWeakTitle(probe)) return probe.take(100)
                }
                continue
            }
            if (isWeakTitle(stripped) || isTocText(stripped)) continue
            val wc = stripped.split(" ").size
            if (wc < 3 || wc > 20) continue
            if (stripped.last() in setOf(',', ';', ':')) continue
            return stripped
        }
        for (line in text.lines()) {
            val stripped = stripMasthead(line.replace(Regex("""\s+"""), " ").trim())
            if (stripped.isEmpty() || isWeakTitle(stripped)) continue
            val words = stripped.split(" ")
            if (words.size < 5) continue
            val probe = words.take(12).joinToString(" ").trim(' ', ',', ';', '-')
            if (probe.length >= 15 && !isWeakTitle(probe)) return probe.take(100)
        }
        return ""
    }

    private fun stripMasthead(value: String): String {
        var out = value.trim()
        var prev: String? = null
        while (out.isNotEmpty() && out != prev) {
            prev = out
            out = datePricePrefix.replace(out, "").trim()
        }
        return out
    }

    private fun isMagazineHeading(line: String): Pair<Boolean, Boolean> {
        val stripped = line.trim()
        if (stripped.isEmpty() || stripped.length > 80) return false to false
        if (stripped.last() in setOf('.', ';', ',')) return false to false
        val words = stripped.split(Regex("""\s+""")).filter { it.isNotEmpty() }
        if (words.size !in 1..12) return false to false
        if (sectionName.matches(stripped)) return true to true
        if (stripped == pythonTitle(stripped) || stripped.all { !it.isLetter() || it.isUpperCase() } && stripped.any { it.isLetter() }) {
            return true to false
        }
        return false to false
    }

    private fun pythonTitle(value: String): String =
        value.split(" ").joinToString(" ") { word ->
            word.replaceFirstChar { ch -> if (ch.isLowerCase()) ch.titlecase() else ch.toString() }
                .let { titled ->
                    if (titled.isNotEmpty() && titled.drop(1).any { it.isLowerCase() }) {
                        titled[0] + titled.drop(1).lowercase()
                    } else {
                        titled
                    }
                }
        }

    fun isTocText(text: String): Boolean {
        if (text.isBlank()) return false
        val sample = text.trim().take(2000)
        if (tocHeading.containsMatchIn(sample)) return true
        val lines = sample.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.size < 4) return false
        val dotted = lines.count { pageDots.containsMatchIn(it) || trailingPage.containsMatchIn(it) }
        val short = lines.count { it.length < 60 }
        if (dotted >= 3 && dotted.toDouble() / lines.size >= 0.35) return true
        if (tocHeading.containsMatchIn(sample.take(200)) && short.toDouble() / lines.size >= 0.7) return true
        return false
    }

    private fun isWeakTitle(title: String): Boolean {
        val t = normalizeTitle(title)
        if (t.isEmpty() || t.length < 6) return true
        if (weakTitle.containsMatchIn(t)) return true
        if (t.count { it == '|' } >= 2) return true
        if (t.length > 90 && t.count { it == ' ' } >= 12 && !Regex("""[.!?]""").containsMatchIn(t)) return true
        return false
    }

    private fun normalizeTitle(title: String): String {
        var t = title.replace(Regex("""\s+"""), " ").trim()
        var prev: String? = null
        while (t != prev) {
            prev = t
            t = navTrail.replace(t, "").trim().trim('|').trim()
        }
        return t
    }

    private fun wordCount(text: String): Int =
        text.split(Regex("""\s+""")).count { it.isNotEmpty() }
}
