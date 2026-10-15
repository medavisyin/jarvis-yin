package com.jarvis.ir.mimo

import org.json.JSONArray
import org.json.JSONObject

object MimoProtocol {
    const val ENDPOINT = "https://api.xiaomimimo.com/v1/chat/completions"
    const val MODEL = "mimo-v2.6-flash"
    const val FAILED = "MiMo 请求失败"
    const val EMPTY = "没有返回内容"

    fun analysisBody(system: String, user: String): String {
        val root = JSONObject()
        root.put("model", MODEL)
        root.put("stream", true)
        root.put("max_completion_tokens", 4096)
        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", system))
        messages.put(JSONObject().put("role", "user").put("content", user))
        root.put("messages", messages)
        return root.toString()
    }

    fun deltas(lines: List<String>): List<String> {
        val out = mutableListOf<String>()
        for (line in lines) {
            val trimmed = line.trim()
            if (!trimmed.startsWith("data:")) continue
            val data = trimmed.removePrefix("data:").trim()
            if (data == "[DONE]") break
            val content = try {
                val choices = JSONObject(data).optJSONArray("choices") ?: continue
                if (choices.length() == 0) continue
                val delta = choices.getJSONObject(0).optJSONObject("delta") ?: continue
                contentText(delta.opt("content"))
            } catch (_: Exception) {
                continue
            }
            if (content.isNotEmpty()) out.add(content)
        }
        return out
    }

    fun contentText(raw: Any?): String {
        if (raw == null || raw == JSONObject.NULL) return ""
        return raw.toString()
    }

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
            val message = JSONObject(raw)
                .getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
            val content = contentText(message.opt("content"))
            content.ifBlank { FAILED }
        } catch (_: Exception) {
            FAILED
        }
    }
}
