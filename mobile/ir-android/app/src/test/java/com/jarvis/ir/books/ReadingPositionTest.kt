package com.jarvis.ir.books

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReadingPositionTest {
    @Test
    fun foldKeepsTheOpenPageUntilTheChapterChanges() {
        assertTrue(ReadingPosition.keep(4, "CHAPTER 1", "CHAPTER 1"))
        assertFalse(ReadingPosition.keep(4, "CHAPTER 2", "CHAPTER 1"))
        assertFalse(ReadingPosition.keep(0, "CHAPTER 1", ""))
        val here = ReadingPosition.token(2, "CHAPTER 1")
        val picked = ReadingPosition.token(9, "CHAPTER 1")
        assertTrue(ReadingPosition.keep(4, here, here))
        assertFalse(ReadingPosition.keep(4, picked, here))
    }
}
