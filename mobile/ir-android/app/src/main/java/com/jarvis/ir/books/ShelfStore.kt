package com.jarvis.ir.books

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

data class ShelfEntry(
    val id: String,
    val title: String,
    val kind: String,
    val chunkIndex: Int,
    val chunkCount: Int,
    val updatedAt: Long,
)

class ShelfStore(private val root: File) {
    fun list(): List<ShelfEntry> = readIndex().books.sortedByDescending { it.updatedAt }

    fun lastId(): String? = readIndex().lastId

    fun find(id: String): ShelfEntry? = readIndex().books.firstOrNull { it.id == id }

    fun loadChunks(id: String): List<String> {
        val file = File(root, "$id.json")
        if (!file.exists()) return emptyList()
        val array = JSONArray(file.readText())
        return (0 until array.length()).map { array.getString(it) }
    }

    fun save(
        title: String,
        kind: String,
        chunks: List<String>,
        now: Long = System.currentTimeMillis(),
    ): ShelfEntry {
        root.mkdirs()
        val id = uniqueId(now)
        val array = JSONArray()
        chunks.forEach { array.put(it) }
        File(root, "$id.json").writeText(array.toString())
        val entry = ShelfEntry(
            id = id,
            title = title.ifBlank { kind },
            kind = kind,
            chunkIndex = 0,
            chunkCount = chunks.size,
            updatedAt = now,
        )
        val index = readIndex()
        writeIndex(index.copy(lastId = id, books = index.books + entry))
        return entry
    }

    fun updatePosition(id: String, chunkIndex: Int, now: Long = System.currentTimeMillis()) {
        val index = readIndex()
        val books = index.books.map { entry ->
            if (entry.id != id) {
                entry
            } else {
                val last = (entry.chunkCount - 1).coerceAtLeast(0)
                entry.copy(chunkIndex = chunkIndex.coerceIn(0, last), updatedAt = now)
            }
        }
        writeIndex(index.copy(lastId = id, books = books))
    }

    private fun uniqueId(now: Long): String {
        var id = now.toString()
        var n = 0
        while (File(root, "$id.json").exists()) {
            n += 1
            id = "$now-$n"
        }
        return id
    }

    private data class Index(val lastId: String?, val books: List<ShelfEntry>)

    private fun readIndex(): Index {
        val indexFile = File(root, "index.json")
        if (!indexFile.exists()) return Index(null, emptyList())
        val json = JSONObject(indexFile.readText())
        val last = if (!json.has("lastId") || json.isNull("lastId")) {
            null
        } else {
            json.optString("lastId").ifBlank { null }
        }
        val booksJson = json.optJSONArray("books") ?: JSONArray()
        val books = (0 until booksJson.length()).map { i ->
            val item = booksJson.getJSONObject(i)
            ShelfEntry(
                id = item.getString("id"),
                title = item.optString("title"),
                kind = item.optString("kind"),
                chunkIndex = item.optInt("chunkIndex"),
                chunkCount = item.optInt("chunkCount"),
                updatedAt = item.optLong("updatedAt"),
            )
        }
        return Index(last, books)
    }

    private fun writeIndex(index: Index) {
        root.mkdirs()
        val books = JSONArray()
        index.books.forEach { entry ->
            books.put(
                JSONObject()
                    .put("id", entry.id)
                    .put("title", entry.title)
                    .put("kind", entry.kind)
                    .put("chunkIndex", entry.chunkIndex)
                    .put("chunkCount", entry.chunkCount)
                    .put("updatedAt", entry.updatedAt),
            )
        }
        val json = JSONObject().put("books", books)
        if (index.lastId == null) json.put("lastId", JSONObject.NULL) else json.put("lastId", index.lastId)
        File(root, "index.json").writeText(json.toString())
    }
}
