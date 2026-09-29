package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisPromptsTest {
    @Test
    fun onlyVocabAndCulture() {
        assertEquals(listOf("vocab", "culture"), AnalysisPrompts.kinds)
    }

    @Test
    fun vocabSystemIsUniversityChinese() {
        val system = AnalysisPrompts.system("vocab")
        assertTrue(system.contains("university-level learner"))
        assertTrue(system.contains("Simplified Chinese"))
        assertTrue(system.contains("Do NOT explain elementary vocabulary"))
    }

    @Test
    fun cultureSystemUsesChineseSharedRules() {
        val system = AnalysisPrompts.system("culture")
        assertTrue(system.contains("literary anthropologist"))
        assertTrue(system.contains("Write the full analysis in Simplified Chinese."))
        assertTrue(!system.contains("Do not use Chinese."))
    }

    @Test
    fun userMessageQuotesTheSlice() {
        val user = AnalysisPrompts.user(
            kind = "culture",
            title = "Emma",
            chunkIndex = 2,
            passage = "She walked.",
            hasMore = false,
        )
        assertTrue(user.contains("Book/section: Emma"))
        assertTrue(user.contains("Analysis tab: culture"))
        assertTrue(user.contains("Chunk index: 2"))
        assertTrue(user.contains("\"\"\"\nShe walked.\n\"\"\""))
        assertTrue(user.contains("socio-cultural annotations"))
        assertTrue(user.contains("Simplified Chinese"))
    }
}
