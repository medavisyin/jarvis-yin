package com.jarvis.ir.explain

import org.junit.Assert.assertTrue
import org.junit.Test

class GlossPromptTest {
    @Test
    fun asksForOneChineseSentenceUsingTheWordAndContext() {
        val text = GlossPrompt.user("bank", "They sat on the river bank.")
        assertTrue(text.contains("bank"))
        assertTrue(text.contains("They sat on the river bank."))
        assertTrue(text.contains("一句"))
        assertTrue(text.indexOf("They sat on the river bank.") < text.lastIndexOf("bank"))
        assertTrue(text.trimEnd().endsWith("中文："))
        assertTrue(!text.contains("苹果"))
        assertTrue(!text.contains("apple"))
    }

    @Test
    fun phraseAsksForTheExpressionThenTheSentence() {
        assertTrue(GlossPrompt.isPhrase("river bank"))
        assertTrue(!GlossPrompt.isPhrase("bank"))
        val meaning = GlossPrompt.phraseMeaning("river bank")
        assertTrue(meaning.contains("river bank"))
        assertTrue(meaning.contains("词组本身"))
        assertTrue(!meaning.contains("They sat"))
        assertTrue(meaning.trimEnd().endsWith("中文："))
    }

    @Test
    fun translationAsksForTheWholeSentenceInChinese() {
        val text = GlossPrompt.translation("They sat on the river bank.")
        assertTrue(text.contains("They sat on the river bank."))
        assertTrue(text.contains("翻译"))
        assertTrue(text.trimEnd().endsWith("中文："))
        assertTrue(text.indexOf("They sat on the river bank.") < text.lastIndexOf("中文："))
        assertTrue(!text.contains("苹果"))
    }
}
