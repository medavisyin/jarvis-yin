package com.jarvis.ir.explain

import com.jarvis.ir.dict.DictRow
import com.jarvis.ir.dict.DictionaryRepository
import com.jarvis.ir.dict.LemmaMap
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ExplainPipelineTest {
    private val repo = DictionaryRepository(
        lemma = LemmaMap.load(""),
        lookupExact = { w ->
            when (w) {
                "bank" -> DictRow("bank", "n", "n. 岸\nn. 银行")
                else -> null
            }
        },
    )

    @Test
    fun dictionaryCardKeepsBothSenses() {
        val card = ExplainPipeline(repo).dictionaryCard(
            "bank",
            "They sat on the river bank.",
        )!!
        assertEquals(ExplainStatus.OK, card.status)
        assertTrue(card.translation.contains("岸"))
        assertTrue(card.translation.contains("银行"))
        assertEquals("They sat on the river bank.", card.example)
    }

    @Test
    fun dictionaryCardMissingPhraseKeepsSelectionAndSentence() {
        val card = ExplainPipeline(repo).dictionaryCard(
            "river bank",
            "They sat on the river bank.",
        )!!
        assertEquals(ExplainStatus.NOT_IN_DICT, card.status)
        assertEquals("river bank", card.word)
        assertEquals("They sat on the river bank.", card.example)
    }
}
