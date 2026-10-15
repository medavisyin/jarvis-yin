package com.jarvis.ir.analysis

import com.jarvis.ir.books.writeReplacing
import org.json.JSONObject
import java.io.File

class PageAnalysisStore(private val root: File) {
    fun load(bookId: String, page: Int, kind: String): String {
        if (page < 0 || kind !in kinds) return ""
        val doc = read(bookId) ?: return ""
        return doc.optJSONObject(page.toString())?.optString(kind).orEmpty()
    }

    fun save(bookId: String, page: Int, kind: String, text: String): Boolean {
        if (bookId.isBlank() || page < 0 || kind !in kinds || text.isBlank()) return false
        val doc = read(bookId) ?: return false
        val pageObject = doc.optJSONObject(page.toString()) ?: JSONObject()
        pageObject.put(kind, text)
        doc.put(page.toString(), pageObject)
        return try {
            writeReplacing(file(bookId), doc.toString())
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun read(bookId: String): JSONObject? {
        val stored = file(bookId)
        if (!stored.exists()) return JSONObject()
        return try {
            JSONObject(stored.readText())
        } catch (_: Exception) {
            null
        }
    }

    private fun file(bookId: String) = File(root, "$bookId.analyses.json")

    companion object {
        val kinds = setOf("vocab", "culture")
    }
}
