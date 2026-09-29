package com.jarvis.ir.glm

import org.json.JSONObject

object GlmProtocol {
    const val ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    const val MODEL = "glm-4.7-flash"

    fun body(system: String, user: String): String {
        val root = JSONObject()
        root.put("model", MODEL)
        root.put("stream", true)
        root.put("max_tokens", 4096)
        root.put("thinking", JSONObject().put("type", "disabled"))
        val messages = org.json.JSONArray()
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
                choices.getJSONObject(0).optJSONObject("delta")?.optString("content").orEmpty()
            } catch (_: Exception) {
                continue
            }
            if (content.isNotEmpty()) out.add(content)
        }
        return out
    }
}
