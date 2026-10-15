package com.jarvis.ir.notes

import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.explain.ExplainStatus

object NoteExplanation {
    fun text(card: ExplainCard?, glossLine: String?, glossLabel: String?): String {
        val parts = mutableListOf<String>()
        if (card != null) {
            when (card.status) {
                ExplainStatus.OK -> {
                    val dictionary = card.translation.trim()
                    if (dictionary.isNotEmpty()) parts.add(dictionary)
                }
                ExplainStatus.REFUSED -> parts.add("这次没法确定")
                ExplainStatus.NOT_IN_DICT -> Unit
            }
        }
        val gloss = glossLine?.trim().orEmpty()
        if (gloss.isNotEmpty() && !gloss.startsWith("正在")) {
            val labeled = if (glossLabel.isNullOrBlank()) gloss else "$glossLabel：$gloss"
            parts.add(labeled)
        }
        return parts.joinToString("\n\n")
    }
}
