package com.jarvis.ir.analysis

import org.junit.Assert.assertEquals
import org.junit.Test

class AnalysisShareTest {
    @Test
    fun blankLinesSplitAndDropEmpties() {
        val text = "第一段\n\n\n\n第二段\n仍在这一段"
        assertEquals(listOf("第一段", "第二段\n仍在这一段"), AnalysisShare.paragraphs(text, includeTail = true))
    }

    @Test
    fun runningDropsTheUnclosedTail() {
        val text = "已经结束\n\n还在写"
        assertEquals(listOf("已经结束"), AnalysisShare.paragraphs(text, includeTail = false))
        assertEquals("还在写", AnalysisShare.openTail(text))
    }

    @Test
    fun closedTailStaysShareableWhileRunning() {
        val text = "只有一段\n\n"
        assertEquals(listOf("只有一段"), AnalysisShare.paragraphs(text, includeTail = false))
        assertEquals("", AnalysisShare.openTail(text))
    }

    @Test
    fun finishedTextKeepsTheLastParagraph() {
        assertEquals(listOf("整篇没有空行"), AnalysisShare.paragraphs("整篇没有空行", includeTail = true))
        assertEquals(emptyList<String>(), AnalysisShare.paragraphs("整篇没有空行", includeTail = false))
        assertEquals("整篇没有空行", AnalysisShare.openTail("整篇没有空行"))
    }

    @Test
    fun shareBodyStartsWithTheBookTitle() {
        assertEquals("Emma\n这一段", AnalysisShare.body("Emma", "这一段"))
        assertEquals("这一段", AnalysisShare.body("  ", "这一段"))
    }
}
