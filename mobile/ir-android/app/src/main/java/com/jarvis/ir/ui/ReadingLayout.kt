package com.jarvis.ir.ui

import androidx.compose.ui.graphics.Color

val readingPaper = Color(0xFFF6F1E7)
val readingInk = Color(0xFF2A261F)

fun paragraphRanges(passage: String): List<IntRange> {
    if (passage.isEmpty()) return emptyList()
    val ranges = mutableListOf<IntRange>()
    var start = 0
    while (start < passage.length) {
        val breakAt = passage.indexOf("\n\n", start)
        val end = if (breakAt < 0) passage.length else breakAt
        if (end > start) ranges.add(start until end)
        if (breakAt < 0) break
        start = breakAt + 2
    }
    return ranges
}
