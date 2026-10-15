package com.jarvis.ir.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class ExplainWindowTest {
    @Test
    fun theWindowStopsAtEightyPercentOfTheScreen() {
        assertEquals(800, ExplainWindow.maxHeightDp(1000))
    }
}
