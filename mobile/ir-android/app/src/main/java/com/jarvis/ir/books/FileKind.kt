package com.jarvis.ir.books

object FileKind {
    fun detect(name: String?, mime: String?): String? {
        val trimmed = name?.trim().orEmpty()
        val dot = trimmed.lastIndexOf('.')
        if (dot > 0 && dot < trimmed.lastIndex) {
            return when (trimmed.substring(dot + 1).lowercase()) {
                "txt" -> "txt"
                "epub" -> "epub"
                "pdf" -> "pdf"
                else -> null
            }
        }
        val base = mime?.substringBefore(';')?.trim()?.lowercase().orEmpty()
        return when (base) {
            "text/plain" -> "txt"
            "application/epub+zip" -> "epub"
            "application/pdf" -> "pdf"
            else -> null
        }
    }
}
