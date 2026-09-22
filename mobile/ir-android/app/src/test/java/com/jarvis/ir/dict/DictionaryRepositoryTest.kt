package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DictionaryRepositoryTest {
    private val lemma = LemmaMap.load("run -> running, ran, runs\n")
    private val rows = mapOf(
        "run" to DictRow(word = "run", pos = "v", translation = "n. 奔跑\nv. 跑步"),
        "bank" to DictRow(word = "bank", pos = "n", translation = "n. 岸\nn. 银行"),
    )
    private val repo = DictionaryRepository(
        lemma = lemma,
        lookupExact = { word -> rows[word.lowercase()] },
    )

    @Test
    fun inflectedWordUsesStem() {
        val hit = repo.lookup("running")!!
        assertEquals("run", hit.word)
        assertEquals(2, hit.senses.size)
    }

    @Test
    fun unknownWordIsNull() {
        assertNull(repo.lookup("xyzzy-not-a-word"))
    }

    @Test
    fun bankHasTwoSenses() {
        assertEquals(listOf("岸", "银行"), repo.lookup("bank")!!.senses.map { it.translation })
    }
}
