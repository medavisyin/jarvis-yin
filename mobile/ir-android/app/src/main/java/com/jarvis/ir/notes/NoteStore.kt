package com.jarvis.ir.notes

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

data class Note(
    val id: String,
    val title: String,
    val content: String,
    val createdAt: Long,
    val explanation: String = "",
)

class NoteStore(private val file: File) {
    fun list(): List<Note> = (read() ?: emptyList()).sortedByDescending { it.createdAt }

    fun add(
        title: String,
        content: String,
        explanation: String = "",
        now: Long = System.currentTimeMillis(),
    ): Note? {
        val body = content.trim()
        if (body.isEmpty()) return null
        val existing = read() ?: return null
        val note = Note(
            id = UUID.randomUUID().toString(),
            title = title.trim(),
            content = body,
            createdAt = now,
            explanation = explanation.trim(),
        )
        write(existing + note)
        return note
    }

    fun delete(id: String): Boolean {
        val existing = read() ?: return false
        if (existing.none { it.id == id }) return false
        write(existing.filter { it.id != id })
        return true
    }

    private fun read(): List<Note>? {
        if (!file.isFile) return emptyList()
        return try {
            val array = JSONArray(file.readText())
            buildList {
                for (index in 0 until array.length()) {
                    val obj = array.getJSONObject(index)
                    add(
                        Note(
                            id = obj.getString("id"),
                            title = obj.optString("title"),
                            content = obj.getString("content"),
                            createdAt = obj.getLong("createdAt"),
                            explanation = obj.optString("explanation"),
                        ),
                    )
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun write(notes: List<Note>) {
        val dir = file.parentFile ?: return
        dir.mkdirs()
        val array = JSONArray()
        notes.forEach { note ->
            array.put(
                JSONObject()
                    .put("id", note.id)
                    .put("title", note.title)
                    .put("content", note.content)
                    .put("createdAt", note.createdAt)
                    .put("explanation", note.explanation),
            )
        }
        val temp = File(dir, "${file.name}.tmp")
        temp.writeText(array.toString())
        val target = file.toPath()
        val source = temp.toPath()
        try {
            java.nio.file.Files.move(
                source,
                target,
                java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                java.nio.file.StandardCopyOption.ATOMIC_MOVE,
            )
        } catch (_: Exception) {
            temp.copyTo(file, overwrite = true)
            temp.delete()
        }
    }
}
