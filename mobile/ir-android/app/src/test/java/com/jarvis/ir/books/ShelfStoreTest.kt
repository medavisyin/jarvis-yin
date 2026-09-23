package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class ShelfStoreTest {
    @Test
    fun remembersTitleChunksAndLastPage() {
        val root = Files.createTempDirectory("shelf").toFile()
        val store = ShelfStore(root)
        val saved = store.save("River", "txt", listOf("page one", "page two"), now = 10)
        store.updatePosition(saved.id, 1, now = 20)
        val again = ShelfStore(root)

        assertEquals(saved.id, again.lastId())
        val listed = again.list().single()
        assertEquals("River", listed.title)
        assertEquals(1, listed.chunkIndex)
        assertEquals(2, listed.chunkCount)
        assertEquals(listOf("page one", "page two"), again.loadChunks(saved.id))
        root.deleteRecursively()
    }

    @Test
    fun emptyShelfHasNoLastBook() {
        val root = Files.createTempDirectory("shelf-empty").toFile()
        assertNull(ShelfStore(root).lastId())
        root.deleteRecursively()
    }

    @Test
    fun saveKeepsTitlesBesideChunks() {
        val root = Files.createTempDirectory("shelf-titles").toFile()
        val store = ShelfStore(root)
        val saved = store.save(
            "Issue",
            "epub",
            listOf("leaders body", "lab body"),
            titles = listOf("Leaders", ""),
            now = 10,
        )
        val again = ShelfStore(root)
        assertEquals(listOf("leaders body", "lab body"), again.loadChunks(saved.id))
        assertEquals(listOf("Leaders", ""), again.loadTitles(saved.id))
        root.deleteRecursively()
    }

    @Test
    fun oldChunkArrayLoadsWithBlankTitles() {
        val root = Files.createTempDirectory("shelf-old").toFile()
        File(root, "old.json").writeText("""["alpha","beta"]""")
        val store = ShelfStore(root)
        assertEquals(listOf("alpha", "beta"), store.loadChunks("old"))
        assertEquals(listOf("", ""), store.loadTitles("old"))
        root.deleteRecursively()
    }

    @Test
    fun titleCountMismatchPadsAndDrops() {
        val root = Files.createTempDirectory("shelf-mismatch").toFile()
        File(root, "short.json").writeText("""{"chunks":["a","b","c"],"titles":["Only"]}""")
        File(root, "long.json").writeText("""{"chunks":["a"],"titles":["One","Extra"]}""")
        val store = ShelfStore(root)
        assertEquals(listOf("Only", "", ""), store.loadTitles("short"))
        assertEquals(listOf("One"), store.loadTitles("long"))
        root.deleteRecursively()
    }

    @Test
    fun deleteRemovesBookFileAndLastOpened() {
        val root = Files.createTempDirectory("shelf-delete").toFile()
        val store = ShelfStore(root)
        val saved = store.save("River", "txt", listOf("page"), now = 10)
        store.updatePosition(saved.id, 0, now = 20)
        store.delete(saved.id)
        val again = ShelfStore(root)
        assertNull(again.lastId())
        assertTrue(again.list().isEmpty())
        assertFalse(File(root, "${saved.id}.json").exists())
        root.deleteRecursively()
    }

    @Test
    fun deleteDropsIndexWhenFileIsAlreadyGone() {
        val root = Files.createTempDirectory("shelf-missing").toFile()
        val store = ShelfStore(root)
        val saved = store.save("River", "txt", listOf("page"), now = 10)
        assertTrue(File(root, "${saved.id}.json").delete())
        store.delete(saved.id)
        assertTrue(ShelfStore(root).list().isEmpty())
        root.deleteRecursively()
    }

    @Test
    fun missingFileStaysListedUntilDelete() {
        val root = Files.createTempDirectory("shelf-listed").toFile()
        val store = ShelfStore(root)
        val saved = store.save("River", "txt", listOf("page"), now = 10)
        assertTrue(File(root, "${saved.id}.json").delete())
        val again = ShelfStore(root)
        assertEquals(listOf(saved.id), again.list().map { it.id })
        assertEquals(emptyList<String>(), again.loadChunks(saved.id))
        root.deleteRecursively()
    }
}
