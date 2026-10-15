package com.jarvis.ir.notes

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

class NoteStoreTest {
    @Test
    fun newestNoteIsListedFirst() {
        val file = Files.createTempDirectory("notes").toFile().resolve("notes.json")
        val store = NoteStore(file)
        store.add("Emma", "第一段", now = 10)
        store.add("Emma", "selected phrase", now = 20)
        val again = NoteStore(file)
        val listed = again.list()
        assertEquals(listOf("selected phrase", "第一段"), listed.map { it.content })
        assertEquals(listOf("Emma", "Emma"), listed.map { it.title })
        assertEquals(listOf(20L, 10L), listed.map { it.createdAt })
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun explanationIsSavedAndOldNotesStayBlank() {
        val file = Files.createTempDirectory("notes-explain").toFile().resolve("notes.json")
        val store = NoteStore(file)
        store.add("Emma", "bank", "n. 河岸", now = 10)
        assertEquals("n. 河岸", NoteStore(file).list().single().explanation)
        file.writeText("""[{"id":"1","title":"Emma","content":"old","createdAt":1}]""")
        assertEquals("", NoteStore(file).list().single().explanation)
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun blankContentIsNotSaved() {
        val file = Files.createTempDirectory("notes-blank").toFile().resolve("notes.json")
        val store = NoteStore(file)
        assertNull(store.add("Emma", "   ", now = 10))
        assertEquals(emptyList<Note>(), store.list())
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun corruptFileIsLeftUntouched() {
        val file = Files.createTempDirectory("notes-corrupt").toFile().resolve("notes.json")
        file.writeText("{not json")
        val before = file.readBytes()
        assertNull(NoteStore(file).add("Emma", "新笔记", now = 10))
        assertTrue(before.contentEquals(file.readBytes()))
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun deleteRemovesOnlyThatNote() {
        val file = Files.createTempDirectory("notes-delete").toFile().resolve("notes.json")
        val store = NoteStore(file)
        val first = store.add("Emma", "第一段", now = 10)
        val second = store.add("Emma", "第二段", now = 20)
        assertTrue(store.delete(first!!.id))
        val listed = NoteStore(file).list()
        assertEquals(listOf(second!!.id), listed.map { it.id })
        assertEquals(listOf("第二段"), listed.map { it.content })
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun deleteMissingIdLeavesFile() {
        val file = Files.createTempDirectory("notes-missing").toFile().resolve("notes.json")
        val store = NoteStore(file)
        val note = store.add("Emma", "留下", now = 10)
        val before = file.readBytes()
        assertFalse(store.delete("missing"))
        assertTrue(before.contentEquals(file.readBytes()))
        assertEquals(listOf(note!!.id), store.list().map { it.id })
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun deleteOnCorruptFileIsLeftUntouched() {
        val file = Files.createTempDirectory("notes-delete-corrupt").toFile().resolve("notes.json")
        file.writeText("{not json")
        val before = file.readBytes()
        assertFalse(NoteStore(file).delete("any"))
        assertTrue(before.contentEquals(file.readBytes()))
        file.parentFile?.deleteRecursively()
    }
}
