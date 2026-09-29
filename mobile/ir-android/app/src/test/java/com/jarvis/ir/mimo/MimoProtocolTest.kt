package com.jarvis.ir.mimo

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class MimoProtocolTest {
    @Test
    fun bodyUsesFlashWithoutThinking() {
        val json = JSONObject(MimoProtocol.body())
        assertEquals("https://api.xiaomimimo.com/v1/chat/completions", MimoProtocol.ENDPOINT)
        assertEquals("mimo-v2.6-flash", json.getString("model"))
        assertEquals(false, json.getBoolean("stream"))
        assertEquals(64, json.getInt("max_completion_tokens"))
        assertFalse(json.has("thinking"))
        assertEquals(
            "Say hello in one sentence.",
            json.getJSONArray("messages").getJSONObject(0).getString("content"),
        )
        assertFalse(json.toString().contains("sk-"))
    }

    @Test
    fun replyTextReadsAssistantContent() {
        val raw = """{"choices":[{"message":{"content":"Hello there."}}]}"""
        assertEquals("Hello there.", MimoProtocol.replyText(raw))
        assertEquals("MiMo 请求失败", MimoProtocol.replyText("{}"))
    }
}
