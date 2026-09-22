package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
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
}
