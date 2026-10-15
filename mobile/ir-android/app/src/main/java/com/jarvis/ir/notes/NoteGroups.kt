package com.jarvis.ir.notes

data class NoteBook(val title: String, val notes: List<Note>)

object NoteGroups {
    fun byBook(notes: List<Note>): List<NoteBook> {
        val order = mutableListOf<String>()
        val grouped = linkedMapOf<String, MutableList<Note>>()
        for (note in notes) {
            val title = note.title
            val bucket = grouped[title]
            if (bucket == null) {
                order.add(title)
                grouped[title] = mutableListOf(note)
            } else {
                bucket.add(note)
            }
        }
        return order.map { title -> NoteBook(title, grouped.getValue(title)) }
    }
}
