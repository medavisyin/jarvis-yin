package com.jarvis.ir.analysis

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisShareTest {
    @Test
    fun chineseNumberedSectionsKeepTheTitleWithTheFirst() {
        val text = """
            ## 段落文化注解

            ### 一、机构与时代坐标

            本段出自白厅。

            ### 二、潜规则

            不说比说更重要。
        """.trimIndent()

        assertEquals(
            listOf(
                "## 段落文化注解\n\n### 一、机构与时代坐标\n\n本段出自白厅。",
                "### 二、潜规则\n\n不说比说更重要。",
            ),
            AnalysisShare.paragraphs(text, includeTail = true),
        )
    }

    @Test
    fun arabicItemsKeepBlankLinesAndRulesInsideTheItem() {
        val text = """
            ## 本段值得学习的表达

            ---

            **1. less-than-completely straightforward replies**
            正话反说。

            ---

            **2. answered evasively**
            含糊其辞。
        """.trimIndent()
        val parts = AnalysisShare.paragraphs(text, includeTail = true)

        assertEquals(2, parts.size)
        assertTrue(parts[0].startsWith("## 本段值得学习的表达"))
        assertTrue(parts[0].contains("正话反说。"))
        assertTrue(parts[0].contains("---"))
        assertTrue(parts[1].startsWith("**2. answered evasively**"))
        assertFalse(parts[1].contains("本段值得学习的表达"))
    }

    @Test
    fun unnumberedHeadingStaysWithThePreviousItem() {
        val text = """
            **1. less-than-completely straightforward replies**
            正话反说。

            ### 补充说明

            语域对比。

            **22. I had no wish to retire**
            还在写
        """.trimIndent()

        assertEquals(
            listOf("**1. less-than-completely straightforward replies**\n正话反说。\n\n### 补充说明\n\n语域对比。"),
            AnalysisShare.paragraphs(text, includeTail = false),
        )
        assertEquals("**22. I had no wish to retire**\n还在写", AnalysisShare.openTail(text))
    }

    @Test
    fun runningHidesTheSectionStillBeingWritten() {
        val text = """
            一、已经写完

            正文

            二、还在写
        """.trimIndent()

        assertEquals(listOf("一、已经写完\n\n正文"), AnalysisShare.paragraphs(text, includeTail = false))
        assertEquals("二、还在写", AnalysisShare.openTail(text))
    }

    @Test
    fun blankLinesDoNotSplitOneItem() {
        val text = "第一段\n\n\n\n仍在这一条"
        assertEquals(listOf("第一段\n\n仍在这一条"), AnalysisShare.paragraphs(text, includeTail = true))
    }

    @Test
    fun finishedTextWithoutNumbersIsOneShare() {
        assertEquals(listOf("整篇没有编号"), AnalysisShare.paragraphs("整篇没有编号", includeTail = true))
        assertEquals(emptyList<String>(), AnalysisShare.paragraphs("整篇没有编号", includeTail = false))
        assertEquals("整篇没有编号", AnalysisShare.openTail("整篇没有编号"))
    }

    @Test
    fun shareBodyStartsWithTheBookTitle() {
        assertEquals("Emma\n这一段", AnalysisShare.body("Emma", "这一段"))
        assertEquals("这一段", AnalysisShare.body("  ", "这一段"))
    }
}
