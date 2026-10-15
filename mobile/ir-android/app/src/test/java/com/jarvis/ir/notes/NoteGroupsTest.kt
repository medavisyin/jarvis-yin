package com.jarvis.ir.notes

import org.junit.Assert.assertEquals
import org.junit.Test

class NoteGroupsTest {
    @Test
    fun oneRowPerBookWithSelectionsNewestFirst() {
        val notes = listOf(
            Note("2", "Emma", "selected phrase", 20),
            Note("1", "Emma", "第一段", 10),
            Note("3", "River", "bank", 15),
        )
        val groups = NoteGroups.byBook(notes)
        assertEquals(listOf("Emma", "River"), groups.map { it.title })
        assertEquals(listOf("selected phrase", "第一段"), groups[0].notes.map { it.content })
        assertEquals(listOf("bank"), groups[1].notes.map { it.content })
    }
}
