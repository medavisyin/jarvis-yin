package com.jarvis.ir.analysis

object AnalysisView {
    const val VOCAB = "vocab"
    const val CULTURE = "culture"

    data class State(
        val kind: String,
        val text: String,
        val saved: Boolean,
        val request: Boolean,
    )

    fun openPage(savedVocab: String): State = show(VOCAB, savedVocab)

    fun show(kind: String, saved: String): State {
        val text = saved.trim()
        return State(kind = kind, text = text, saved = text.isNotEmpty(), request = false)
    }

    fun action(saved: Boolean): String = if (saved) "重写" else "生成"

    fun bright(kind: String, selected: String): Boolean = kind == selected
}
