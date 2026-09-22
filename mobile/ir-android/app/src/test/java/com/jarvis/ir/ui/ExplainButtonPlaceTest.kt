package com.jarvis.ir.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class ExplainButtonPlaceTest {
    @Test
    fun placesBelowSelectionWhenTheLineIsOnScreen() {
        assertEquals(
            120f,
            explainButtonTop(
                selectionTop = 80f,
                selectionBottom = 112f,
                viewportTop = 0f,
                viewportBottom = 800f,
                buttonHeight = 48f,
                gap = 8f,
            ),
        )
    }

    @Test
    fun placesAboveSelectionWhenBelowWouldLeaveTheScreen() {
        assertEquals(
            700f,
            explainButtonTop(
                selectionTop = 760f,
                selectionBottom = 792f,
                viewportTop = 400f,
                viewportBottom = 820f,
                buttonHeight = 48f,
                gap = 12f,
            ),
        )
    }
}
