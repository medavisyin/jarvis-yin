package com.jarvis.ir.books

object ReadingPosition {
    fun token(chapterIndex: Int, title: String): String = "$chapterIndex\u0000${title.trim()}"

    fun keep(index: Int, title: String, appliedTitle: String): Boolean =
        title.isNotEmpty() && title == appliedTitle && index >= 0
}
