package com.jarvis.ir.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WordSelectorTest {
    private val passage = "They sat on the river bank. Then they left."

    @Test
    fun tapInsideBankReturnsWordAndSentence() {
        val hit = WordSelector.at(passage, passage.indexOf("bank"))
        assertEquals("bank", hit!!.word)
        assertEquals("They sat on the river bank.", hit.sentence)
    }

    @Test
    fun stripsTrailingPunctuation() {
        val text = "Hello, bank."
        val hit = WordSelector.at(text, text.indexOf("bank"))
        assertEquals("bank", hit!!.word)
    }

    @Test
    fun outOfRangeIsNull() {
        assertNull(WordSelector.at(passage, -1))
        assertNull(WordSelector.at(passage, passage.length))
    }

    @Test
    fun dragFromRiverToBankSelectsPhrase() {
        val hit = WordSelector.span(passage, passage.indexOf("river") + 1, passage.indexOf("bank") + 1)!!
        assertEquals("river bank", hit.word)
        assertEquals("They sat on the river bank.", hit.sentence)
        assertEquals(passage.indexOf("river"), hit.start)
        assertEquals(passage.indexOf("bank") + "bank".length, hit.end)
    }

    @Test
    fun dragBackwardSelectsSamePhrase() {
        val hit = WordSelector.span(passage, passage.indexOf("bank"), passage.indexOf("river"))!!
        assertEquals("river bank", hit.word)
        assertEquals(passage.indexOf("river"), hit.start)
        assertEquals(passage.indexOf("bank") + "bank".length, hit.end)
    }

    @Test
    fun spanInsideOneWordStaysThatWord() {
        val hit = WordSelector.span(passage, passage.indexOf("bank") + 1, passage.indexOf("bank") + 2)!!
        assertEquals("bank", hit.word)
    }

    @Test
    fun releaseOnPeriodAfterPhraseStillEndsAtLastWord() {
        val period = passage.indexOf('.')
        val hit = WordSelector.span(passage, passage.indexOf("river"), period)!!
        assertEquals("river bank", hit.word)
        assertEquals(passage.indexOf("bank") + "bank".length, hit.end)
    }

    @Test
    fun longPressOnSpaceSelectsNothing() {
        val space = passage.indexOf(" river")
        assertNull(WordSelector.span(passage, space, space))
    }

    @Test
    fun dragIntoTheSpaceAfterRiverStaysOnRiver() {
        val river = passage.indexOf("river")
        val hit = WordSelector.span(passage, river, river + "river".length)!!
        assertEquals("river", hit.word)
    }
}
