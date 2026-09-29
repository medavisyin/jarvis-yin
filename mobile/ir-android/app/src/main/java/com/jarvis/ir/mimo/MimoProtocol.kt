package com.jarvis.ir.mimo

import org.json.JSONArray
import org.json.JSONObject

object MimoProtocol {
    const val ENDPOINT = "https://api.xiaomimimo.com/v1/chat/completions"
    const val MODEL = "mimo-v2.6-flash"
    const val FAILED = "MiMo 请求失败"

    fun body(): String {
        val root = JSONObject()
        root.put("model", MODEL)
        root.put("stream", false)
        root.put("max_completion_tokens", 64)
        val messages = JSONArray()
        messages.put(JSONObject().put("role", "user").put("content", "Say hello in one sentence."))
        root.put("messages", messages)
        return root.toString()
    }

    fun replyText(raw: String): String {
        return try {
            val content = JSONObject(raw)
                .getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .optString("content")
            content.ifBlank { FAILED }
        } catch (_: Exception) {
            FAILED
        }
    }
}
