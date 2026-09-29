package com.jarvis.ir.glm

class GlmConfigException(message: String) : IllegalStateException(message)

object GlmKey {
    const val PREFS = "ir"
    const val PREF_KEY = "glm_api_key"
    const val MISSING = "还没有 GLM 密钥"

    fun mask(key: String): String {
        if (key.isEmpty()) return ""
        if (key.length > 8) return key.take(4) + "****" + key.takeLast(4)
        return "****"
    }

    fun require(key: String?): String {
        val text = key?.trim().orEmpty()
        if (text.isEmpty()) throw GlmConfigException(MISSING)
        return text
    }
}
