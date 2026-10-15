package com.jarvis.ir.analysis

import com.jarvis.ir.books.ShelfStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class PageAnalysisStoreTest {
    @Test
    fun vocabAndCultureStayOnTheirOwnPages() {
        val root = Files.createTempDirectory("analysis").toFile()
        val store = PageAnalysisStore(root)
        assertEquals("", store.load("book", 0, "vocab"))
        assertTrue(store.save("book", 0, "vocab", "good words"))
        assertTrue(store.save("book", 0, "culture", "the city"))
        assertTrue(store.save("book", 1, "vocab", "next page"))
        val again = PageAnalysisStore(root)
        assertEquals("good words", again.load("book", 0, "vocab"))
        assertEquals("the city", again.load("book", 0, "culture"))
        assertEquals("next page", again.load("book", 1, "vocab"))
        assertEquals("", again.load("book", 1, "culture"))
        root.deleteRecursively()
    }

    @Test
    fun blankTextAndUnknownKindDoNotWrite() {
        val root = Files.createTempDirectory("analysis-blank").toFile()
        val store = PageAnalysisStore(root)
        assertTrue(store.save("book", 0, "vocab", "keep"))
        assertFalse(store.save("book", 0, "vocab", "  "))
        assertFalse(store.save("book", 0, "plot", "no"))
        assertEquals("keep", store.load("book", 0, "vocab"))
        assertEquals("", store.load("book", 0, "plot"))
        root.deleteRecursively()
    }

    @Test
    fun corruptFileIsLeftAlone() {
        val root = Files.createTempDirectory("analysis-corrupt").toFile()
        val file = File(root, "book.analyses.json")
        file.writeText("{")
        val store = PageAnalysisStore(root)
        assertEquals("", store.load("book", 0, "vocab"))
        assertFalse(store.save("book", 0, "vocab", "new"))
        assertEquals("{", file.readText())
        root.deleteRecursively()
    }

    @Test
    fun retitleAndDeleteDropTheSavedPages() {
        val root = Files.createTempDirectory("analysis-shelf").toFile()
        val shelf = ShelfStore(root)
        val saved = shelf.save("River", "txt", listOf("a", "b"), now = 10)
        val store = PageAnalysisStore(root)
        assertTrue(store.save(saved.id, 0, "vocab", "words"))
        shelf.replace(saved.id, listOf("Left.", "Right."), listOf("Chapter 1", "Chapter 2"), now = 30)
        assertFalse(File(root, "${saved.id}.analyses.json").exists())
        assertEquals("", PageAnalysisStore(root).load(saved.id, 0, "vocab"))
        assertTrue(store.save(saved.id, 0, "culture", "city"))
        shelf.delete(saved.id)
        assertFalse(File(root, "${saved.id}.analyses.json").exists())
        root.deleteRecursively()
    }

    @Test
    fun saveDoesNotTouchTheBookFile() {
        val root = Files.createTempDirectory("analysis-book").toFile()
        val shelf = ShelfStore(root)
        val saved = shelf.save("River", "txt", listOf("page"), titles = listOf("Chapter 1"), now = 10)
        assertTrue(shelf.markRead(saved.id, "Chapter 1"))
        val book = File(root, "${saved.id}.json")
        val before = book.readText()
        assertTrue(PageAnalysisStore(root).save(saved.id, 0, "vocab", "words"))
        assertTrue(PageAnalysisStore(root).save(saved.id, 0, "culture", "city"))
        assertEquals(before, book.readText())
        root.deleteRecursively()
    }
}
