package com.cactus

import org.json.JSONArray
import org.json.JSONObject
import java.io.Closeable

class Cactus private constructor(private var handle: Long) : Closeable {
    companion object {
        init {
            System.loadLibrary("cactus")
        }

        fun create(modelPath: String): Cactus {
            val handle = nativeInit(modelPath, null)
            if (handle == 0L) {
                throw CactusException(nativeGetLastError().ifEmpty { "Failed to initialize model" })
            }
            return Cactus(handle)
        }

        @JvmStatic
        private external fun nativeInit(modelPath: String, corpusDir: String?): Long

        @JvmStatic
        private external fun nativeGetLastError(): String
    }

    fun complete(messages: List<Message>, options: CompletionOptions): CompletionResult {
        val messagesJson = JSONArray(messages.map { it.toJson() }).toString()
        val responseJson = nativeComplete(handle, messagesJson, options.toJson(), null, null)
        return CompletionResult(text = CactusReply.text(responseJson))
    }

    override fun close() {
        if (handle != 0L) {
            nativeDestroy(handle)
            handle = 0L
        }
    }

    private external fun nativeDestroy(handle: Long)

    private external fun nativeComplete(
        handle: Long,
        messagesJson: String,
        optionsJson: String?,
        toolsJson: String?,
        callback: Any?,
    ): String
}

data class Message(val role: String, val content: String) {
    companion object {
        fun system(content: String) = Message("system", content)
        fun user(content: String) = Message("user", content)
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put("role", role)
        put("content", content)
    }
}

data class CompletionOptions(
    val temperature: Float = 0.7f,
    val topP: Float = 0.9f,
    val topK: Int = 40,
    val maxTokens: Int = 512,
) {
    fun toJson(): String = JSONObject().apply {
        put("temperature", temperature)
        put("top_p", topP)
        put("top_k", topK)
        put("max_tokens", maxTokens)
        put("stop", JSONArray())
        put("confidence_threshold", 0.0)
    }.toString()
}

data class CompletionResult(val text: String)

class CactusException(message: String) : Exception(message)
