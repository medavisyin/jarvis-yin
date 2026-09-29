package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PassageWindowTest {
    @Test
    fun shortPassageIsUnchanged() {
        val slice = PassageWindow.slice("Hello.\n\nWorld.")
        assertEquals("Hello.\n\nWorld.", slice.text)
        assertFalse(slice.hasMore)
    }

    @Test
    fun longPassageStopsOnAParagraph() {
        val para = "A".repeat(100) + "\n\n"
        val passage = para.repeat(200)
        val slice = PassageWindow.slice(passage)
        assertTrue(slice.text.length <= 12000)
        assertTrue(slice.text.length >= 6000)
        assertTrue(slice.text.endsWith("\n\n"))
        assertTrue(slice.hasMore)
    }
}
