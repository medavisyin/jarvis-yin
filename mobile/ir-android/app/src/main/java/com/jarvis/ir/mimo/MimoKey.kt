package com.jarvis.ir.mimo

class MimoConfigException(message: String) : IllegalStateException(message)

object MimoKey {
    const val PREFS = "ir"
    const val PREF_KEY = "mimo_api_key"
    const val MISSING = "还没有 MiMo 密钥"

    fun mask(key: String): String {
        if (key.isEmpty()) return ""
        if (key.length > 8) return key.take(4) + "****" + key.takeLast(4)
        return "****"
    }

    fun require(key: String?): String {
        val text = key?.trim().orEmpty()
        if (text.isEmpty()) throw MimoConfigException(MISSING)
        return text
    }
}
