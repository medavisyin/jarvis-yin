package com.jarvis.ir.explain

import com.jarvis.ir.dict.DictionaryRepository

enum class ExplainStatus { OK, NOT_IN_DICT, REFUSED }

data class ExplainCard(
    val status: ExplainStatus,
    val word: String = "",
    val pos: String? = null,
    val translation: String = "",
    val example: String = "",
    val uncertain: Boolean = false,
    val confidence: Double? = null,
)

class ExplainPipeline(
    private val dict: DictionaryRepository,
) {
    fun dictionaryCard(selected: String, sentence: String): ExplainCard? {
        val hit = dict.lookup(selected)
            ?: return ExplainCard(
                status = ExplainStatus.NOT_IN_DICT,
                word = selected,
                example = sentence,
            )
        val translation = hit.senses.joinToString("\n") { sense ->
            listOfNotNull(sense.pos?.takeIf { it.isNotBlank() }, sense.translation)
                .joinToString(" ")
        }
        return ExplainCard(
            status = ExplainStatus.OK,
            word = hit.word,
            pos = hit.senses.firstOrNull()?.pos,
            translation = translation,
            example = sentence,
        )
    }
}
