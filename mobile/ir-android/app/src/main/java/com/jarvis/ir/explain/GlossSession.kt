package com.jarvis.ir.explain

interface GlossEngine {
    fun isDownloaded(slug: String): Boolean

    suspend fun download(slug: String, onStatus: (String) -> Unit = {})

    suspend fun complete(slug: String, word: String, sentence: String): String

    suspend fun translateSentence(slug: String, sentence: String): String
}

class GlossSession(private val engine: GlossEngine) {
    fun downloaded(slug: String): Boolean {
        return try {
            engine.isDownloaded(slug)
        } catch (_: Exception) {
            false
        }
    }

    suspend fun download(slug: String, onStatus: (String) -> Unit = {}): String {
        return try {
            if (!engine.isDownloaded(slug)) {
                engine.download(slug, onStatus)
            }
            DOWNLOADED
        } catch (e: Exception) {
            e.message?.takeIf { it.isNotBlank() } ?: "下载失败"
        }
    }

    suspend fun explainIfReady(slug: String, word: String, sentence: String): String? {
        if (!downloaded(slug)) return null
        return try {
            engine.complete(slug, word, sentence)
        } catch (e: Exception) {
            e.message?.takeIf { it.isNotBlank() } ?: "讲解失败"
        }
    }

    suspend fun translateIfReady(slug: String, sentence: String): String? {
        if (!downloaded(slug)) return null
        return try {
            engine.translateSentence(slug, sentence)
        } catch (e: Exception) {
            e.message?.takeIf { it.isNotBlank() } ?: "翻译失败"
        }
    }

    companion object {
        const val MODEL_06 = "qwen3-0.6"
        const val MODEL_17 = "qwen3-1.7"
        val choices = listOf(MODEL_06, MODEL_17)
        const val DOWNLOADED = "已下载"
        const val NOT_DOWNLOADED = "未下载"

        fun statusFor(downloaded: Boolean): String =
            if (downloaded) DOWNLOADED else NOT_DOWNLOADED
    }
}
