package com.jarvis.ir.explain

object GlossPrompt {
    fun isPhrase(selected: String): Boolean =
        selected.trim().split(Regex("""\s+""")).count { it.isNotEmpty() } > 1

    fun user(word: String, sentence: String): String = """
        句子：$sentence
        「$word」在这句里是什么意思？只写一句中文，不要写英文。
        中文：
    """.trimIndent()

    fun userRetry(word: String, sentence: String): String = """
        句子：$sentence
        用汉字说明「$word」的意思。不要写英文。
        中文：
    """.trimIndent()

    fun phraseMeaning(phrase: String): String = """
        词组：$phrase
        这个词组本身是什么意思？只写一句中文，不要英文，不要举例。
        中文：
    """.trimIndent()

    fun phraseMeaningRetry(phrase: String): String = """
        词组：$phrase
        用汉字解释这个词组。不要写英文。
        中文：
    """.trimIndent()

    fun translation(sentence: String): String = """
        $sentence
        把上一句翻译成中文。只写中文，不要写英文。
        中文：
    """.trimIndent()

    fun translationRetry(sentence: String): String = """
        $sentence
        用汉字翻译上面这句。
        中文：
    """.trimIndent()
}
