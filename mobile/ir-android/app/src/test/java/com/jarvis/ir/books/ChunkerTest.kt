package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChunkerTest {
    @Test
    fun emptyInputIsEmpty() {
        assertEquals(emptyList<String>(), Chunker.chunk(""))
    }

    @Test
    fun doesNotSplitInsideParagraph() {
        val para = (1..400).joinToString(" ") { "word$it" }
        val chunks = Chunker.chunk(para)
        assertEquals(1, chunks.size)
        assertEquals(para, chunks[0])
    }

    @Test
    fun packsParagraphsUntilWordBudget() {
        val small = (1..100).joinToString(" ") { "a$it" }
        val text = "$small\n\n$small\n\n$small"
        val chunks = Chunker.chunk(text, maxWords = 250)
        assertEquals(2, chunks.size)
        assertTrue(chunks[0].contains("a1"))
        assertTrue(chunks[1].contains("a201").not())
        assertTrue(Chunker.wordCount(chunks[0]) <= 250 || chunks[0] == "$small\n\n$small")
        assertEquals(200, Chunker.wordCount(chunks[0]))
        assertEquals(100, Chunker.wordCount(chunks[1]))
    }

    @Test
    fun splitsAChapterSizedParagraphOnSentences() {
        val sentence = "The river bank was quiet today."
        val chapter = (1..80).joinToString(" ") { sentence }
        val chunks = Chunker.chunk(chapter, maxWords = 40)
        assertTrue(chunks.size > 1)
        chunks.forEach { assertTrue(Chunker.wordCount(it) <= 40) }
    }

    @Test
    fun splitsALongSentenceByWords() {
        val sentence = (1..30).joinToString(" ") { "word$it" }
        val chunks = Chunker.chunk(sentence, maxWords = 10)
        assertEquals(3, chunks.size)
        assertEquals(10, Chunker.wordCount(chunks[0]))
    }

    @Test
    fun splitsUnspacedChineseBySentence() {
        val chapter = "河岸很长。草是湿的。水是冷的。"
        val chunks = Chunker.chunk(chapter, maxWords = 5)
        assertTrue(chunks.size > 1)
        chunks.forEach { assertTrue(Chunker.wordCount(it) <= 5) }
    }
}
