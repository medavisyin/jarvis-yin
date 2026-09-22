package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Test

class SenseParserTest {
    @Test
    fun splitsNewlinePosGlosses() {
        val senses = SenseParser.parse(
            translation = "n. 银行\nvt. 把钱存入银行",
            posField = "n:8/v:2",
        )
        assertEquals(2, senses.size)
        assertEquals("n", senses[0].pos)
        assertEquals("银行", senses[0].translation)
        assertEquals(0, senses[0].id)
        assertEquals("vt", senses[1].pos)
        assertEquals("把钱存入银行", senses[1].translation)
    }

    @Test
    fun numberedLinesKeepOrder() {
        val senses = SenseParser.parse(
            translation = "1. n. 岸\n2. n. 银行",
            posField = null,
        )
        assertEquals(listOf("岸", "银行"), senses.map { it.translation })
        assertEquals(listOf("n", "n"), senses.map { it.pos })
    }

    @Test
    fun dropsInflectionAndExamTag() {
        val senses = SenseParser.parse(
            translation = "n. 审视, 扫描\n[计] 网络软件目录\n[时态] scanned, scanning, scans\n(高研四六托雅宝 4031/5003)\n(19344/10263)",
            posField = "n",
        )
        assertEquals(listOf("审视, 扫描", "[计] 网络软件目录"), senses.map { it.translation })
    }

    @Test
    fun emptyTranslationIsEmptyList() {
        assertEquals(0, SenseParser.parse(translation = "  ", posField = null).size)
    }
}
