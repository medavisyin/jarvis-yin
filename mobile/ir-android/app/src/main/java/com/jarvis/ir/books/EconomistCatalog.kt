package com.jarvis.ir.books

import org.json.JSONArray
import org.json.JSONException

data class EconomistIssue(val name: String, val path: String)

data class EconomistFile(val name: String, val downloadUrl: String, val kind: String)

object EconomistCatalog {
    fun latestIssues(json: String, limit: Int = 3): List<EconomistIssue> {
        val array = parseArray(json)
        val issues = buildList {
            for (i in 0 until array.length()) {
                val obj = array.optJSONObject(i) ?: continue
                val name = obj.optString("name")
                if (obj.optString("type") == "dir" && name.startsWith("te_")) {
                    add(EconomistIssue(name, obj.optString("path")))
                }
            }
        }
        return issues.sortedByDescending { it.name }.take(limit)
    }

    fun requireIssues(json: String): List<EconomistIssue> {
        val issues = latestIssues(json)
        if (issues.isEmpty()) throw IllegalStateException(EconomistMessages.EMPTY_ISSUES)
        return issues
    }

    fun requireBooks(json: String): List<EconomistFile> {
        val books = books(json)
        if (books.isEmpty()) throw IllegalStateException(EconomistMessages.EMPTY_FILES)
        return books
    }

    fun books(json: String): List<EconomistFile> {
        val array = parseArray(json)
        return buildList {
            for (i in 0 until array.length()) {
                val obj = array.optJSONObject(i) ?: continue
                if (obj.optString("type") != "file") continue
                val name = obj.optString("name")
                val kind = when {
                    name.endsWith(".epub", ignoreCase = true) -> "epub"
                    name.endsWith(".pdf", ignoreCase = true) -> "pdf"
                    else -> continue
                }
                val url = obj.optString("download_url")
                if (url.isBlank()) continue
                add(EconomistFile(name, url, kind))
            }
        }
    }

    private fun parseArray(json: String): JSONArray {
        try {
            val trimmed = json.trim()
            if (!trimmed.startsWith("[")) {
                throw IllegalArgumentException(EconomistMessages.PARSE)
            }
            return JSONArray(trimmed)
        } catch (e: IllegalArgumentException) {
            throw e
        } catch (e: JSONException) {
            throw IllegalArgumentException(EconomistMessages.PARSE)
        }
    }
}
