package com.jarvis.ir.books

object ChapterLabels {
    fun label(title: String, index: Int): String {
        val trimmed = title.trim()
        if (trimmed.isNotEmpty()) return trimmed
        return "第 ${index + 1} 段"
    }
}
