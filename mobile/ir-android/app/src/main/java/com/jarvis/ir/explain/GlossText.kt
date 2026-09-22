package com.jarvis.ir.explain

object GlossText {
    fun sentence(raw: String): String {
        var text = raw.trim()
        val end = text.lastIndexOf("</think>")
        if (end >= 0) {
            text = text.substring(end + "</think>".length).trim()
        } else if (text.startsWith("<think>")) {
            return ""
        }
        return text.removePrefix("中文：").removePrefix("中文:").trim()
    }

    fun chinese(raw: String): String {
        val text = sentence(raw)
        val firstHan = text.indexOfFirst { it.code in 0x4E00..0x9FFF }
        if (firstHan < 0) return ""
        return text.substring(firstHan).trim()
    }
}
