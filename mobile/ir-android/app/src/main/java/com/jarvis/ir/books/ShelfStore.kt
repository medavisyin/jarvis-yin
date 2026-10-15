package com.jarvis.ir.books

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption

data class ShelfEntry(
    val id: String,
    val title: String,
    val kind: String,
    val chunkIndex: Int,
    val chunkCount: Int,
    val updatedAt: Long,
)

internal fun writeReplacing(file: File, text: String) {
    file.parentFile?.mkdirs()
    val temp = File(file.parentFile, "${file.name}.tmp")
    temp.writeText(text)
    val source = temp.toPath()
    val target = file.toPath()
    try {
        Files.move(source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    } catch (_: AtomicMoveNotSupportedException) {
        try {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING)
        } catch (error: Exception) {
            temp.delete()
            throw error
        }
    } catch (error: Exception) {
        temp.delete()
        throw error
    }
}

class ShelfStore(private val root: File) {
    fun list(): List<ShelfEntry> = readIndex().books.sortedByDescending { it.updatedAt }

    fun lastId(): String? = readIndex().lastId

    fun find(id: String): ShelfEntry? = readIndex().books.firstOrNull { it.id == id }

    fun loadChunks(id: String): List<String> = readBook(id).chunks

    fun loadTitles(id: String): List<String> = readBook(id).titles

    fun save(
        title: String,
        kind: String,
        chunks: List<String>,
        titles: List<String> = emptyList(),
        now: Long = System.currentTimeMillis(),
    ): ShelfEntry {
        root.mkdirs()
        val id = uniqueId(now)
        val aligned = List(chunks.size) { index -> titles.getOrElse(index) { "" } }
        val chunkArray = JSONArray()
        chunks.forEach { chunkArray.put(it) }
        val titleArray = JSONArray()
        aligned.forEach { titleArray.put(it) }
        val body = JSONObject().put("chunks", chunkArray).put("titles", titleArray)
        File(root, "$id.json").writeText(body.toString())
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

    fun replace(
        id: String,
        chunks: List<String>,
        titles: List<String>,
        now: Long = System.currentTimeMillis(),
    ): ShelfEntry? {
        if (chunks.isEmpty()) return null
        val index = readIndex()
        val current = index.books.firstOrNull { it.id == id } ?: return null
        val aligned = List(chunks.size) { indexInChunk -> titles.getOrElse(indexInChunk) { "" } }
        val chunkArray = JSONArray()
        chunks.forEach { chunkArray.put(it) }
        val titleArray = JSONArray()
        aligned.forEach { titleArray.put(it) }
        val body = JSONObject().put("chunks", chunkArray).put("titles", titleArray)
        readJsonObject(id)?.optJSONArray("read")?.let { body.put("read", it) }
        File(root, "$id.json").writeText(body.toString())
        File(root, "$id.analyses.json").delete()
        val updated = current.copy(chunkIndex = 0, chunkCount = chunks.size, updatedAt = now)
        writeIndex(index.copy(books = index.books.map { if (it.id == id) updated else it }))
        return updated
    }

    fun delete(id: String) {
        val index = readIndex()
        val last = if (index.lastId == id) null else index.lastId
        writeIndex(index.copy(lastId = last, books = index.books.filter { it.id != id }))
        File(root, "$id.json").delete()
        File(root, "$id.analyses.json").delete()
    }

    fun loadRead(id: String): Set<String> {
        val array = readJsonObject(id)?.optJSONArray("read") ?: return emptySet()
        return (0 until array.length()).map { array.optString(it) }.filter { it.isNotEmpty() }.toSet()
    }

    fun markRead(id: String, key: String): Boolean {
        if (key.isBlank()) return false
        val file = File(root, "$id.json")
        if (!file.exists()) return false
        val json = readJsonObject(id) ?: return false
        val array = json.optJSONArray("read") ?: JSONArray()
        val existing = (0 until array.length()).map { array.optString(it) }
        if (key !in existing) {
            array.put(key)
            json.put("read", array)
            writeReplacing(file, json.toString())
        }
        return true
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

    private data class BookFile(val chunks: List<String>, val titles: List<String>)

    private fun readJsonObject(id: String): JSONObject? {
        val file = File(root, "$id.json")
        if (!file.exists()) return null
        val text = file.readText().trim()
        if (text.startsWith("[")) {
            return JSONObject().put("chunks", JSONArray(text)).put("titles", JSONArray())
        }
        return JSONObject(text)
    }

    private fun readBook(id: String): BookFile {
        val file = File(root, "$id.json")
        if (!file.exists()) return BookFile(emptyList(), emptyList())
        val text = file.readText().trim()
        if (text.startsWith("[")) {
            val array = JSONArray(text)
            val chunks = (0 until array.length()).map { array.getString(it) }
            return BookFile(chunks, List(chunks.size) { "" })
        }
        val json = JSONObject(text)
        val chunksJson = json.optJSONArray("chunks") ?: JSONArray()
        val titlesJson = json.optJSONArray("titles") ?: JSONArray()
        val chunks = (0 until chunksJson.length()).map { chunksJson.optString(it) }
        val titles = List(chunks.size) { index ->
            if (index < titlesJson.length()) titlesJson.optString(index) else ""
        }
        return BookFile(chunks, titles)
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
