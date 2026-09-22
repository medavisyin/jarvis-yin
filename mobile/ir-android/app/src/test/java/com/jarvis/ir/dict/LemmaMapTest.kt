package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Test

class LemmaMapTest {
    @Test
    fun inflectedFormMapsToStem() {
        val map = LemmaMap.load(
            javaClass.classLoader!!.getResourceAsStream("lemma-fixture.txt")!!
                .bufferedReader()
                .readText(),
        )
        assertEquals("run", map.stem("running"))
        assertEquals("run", map.stem("Run"))
        assertEquals("bank", map.stem("banks"))
        assertEquals("ephemeral", map.stem("ephemeral"))
    }
}
