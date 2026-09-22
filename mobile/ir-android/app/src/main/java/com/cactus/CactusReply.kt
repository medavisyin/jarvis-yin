package com.cactus

import org.json.JSONObject

object CactusReply {
    fun text(raw: String): String {
        val json = JSONObject(raw)
        if (!json.isNull("error")) {
            val err = json.optString("error", "").trim()
            if (err.isNotEmpty()) throw CactusException(err)
        }
        if (json.isNull("response")) return ""
        return json.optString("response", "")
    }
}
