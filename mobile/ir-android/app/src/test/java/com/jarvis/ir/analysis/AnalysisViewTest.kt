package com.jarvis.ir.analysis

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisViewTest {
    @Test
    fun openingAPageShowsSavedVocabWithoutRequesting() {
        val state = AnalysisView.openPage("saved words")

        assertEquals(AnalysisView.VOCAB, state.kind)
        assertEquals("saved words", state.text)
        assertTrue(state.saved)
        assertFalse(state.request)
    }

    @Test
    fun openingAPageWithNothingSavedStaysEmpty() {
        val state = AnalysisView.openPage("  ")

        assertEquals(AnalysisView.VOCAB, state.kind)
        assertEquals("", state.text)
        assertFalse(state.saved)
        assertFalse(state.request)
    }

    @Test
    fun switchingKindShowsOnlyThatSavedText() {
        val culture = AnalysisView.show(AnalysisView.CULTURE, "local culture")
        val missing = AnalysisView.show(AnalysisView.CULTURE, "")

        assertEquals("local culture", culture.text)
        assertFalse(culture.request)
        assertEquals("", missing.text)
        assertFalse(missing.saved)
        assertFalse(missing.request)
    }

    @Test
    fun generateWhenEmptyAndRewriteWhenSaved() {
        assertEquals("生成", AnalysisView.action(saved = false))
        assertEquals("重写", AnalysisView.action(saved = true))
    }

    @Test
    fun onlyTheSelectedKindIsBright() {
        assertTrue(AnalysisView.bright(AnalysisView.VOCAB, AnalysisView.VOCAB))
        assertFalse(AnalysisView.bright(AnalysisView.CULTURE, AnalysisView.VOCAB))
    }
}
