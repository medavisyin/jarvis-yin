package com.jarvis.ir.glm

data class Slice(val text: String, val hasMore: Boolean)

object PassageWindow {
    const val WINDOW = 12000

    fun slice(passage: String, window: Int = WINDOW): Slice {
        if (passage.length <= window) return Slice(passage, false)
        val head = passage.substring(0, window)
        val minBreak = (head.length * 0.45).toInt()
        if (head.length > (window * 0.55).toInt()) {
            for (sep in listOf("\n\n", "\n", ". ", "? ", "! ")) {
                val idx = head.lastIndexOf(sep)
                if (idx > minBreak) return Slice(head.substring(0, idx + sep.length), true)
            }
        }
        return Slice(head, true)
    }
}
