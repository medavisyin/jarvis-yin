package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.coroutines.runBlocking
import kotlin.coroutines.cancellation.CancellationException

class ChapterJumpTest {
    @Test
    fun cancelledScrollClearsThePendingPage() {
        val jump = ChapterJump()
        jump.request(4)
        val error = runBlocking {
            runCatching {
                jump.consume { throw CancellationException("stop") }
            }.exceptionOrNull()
        }
        assertTrue(error is CancellationException)
        assertNull(jump.target)
    }

    @Test
    fun resetDropsAPendingPage() {
        val jump = ChapterJump()
        jump.request(2)
        jump.reset()
        var scrolled: Int? = null
        runBlocking {
            jump.consume { scrolled = it }
        }
        assertNull(jump.target)
        assertNull(scrolled)
    }

    @Test
    fun newerRequestSurvivesCancelledScroll() {
        val jump = ChapterJump()
        jump.request(1)
        val error = runBlocking {
            runCatching {
                jump.consume {
                    jump.request(4)
                    throw CancellationException("stop")
                }
            }.exceptionOrNull()
        }
        assertTrue(error is CancellationException)
        assertEquals(4, jump.target)
    }
}
