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
    fun analysisBodyStreamsFlashWithoutThinking() {
        val json = JSONObject(MimoProtocol.analysisBody("system text", "user text"))
        assertEquals("mimo-v2.6-flash", json.getString("model"))
        assertEquals(true, json.getBoolean("stream"))
        assertEquals(4096, json.getInt("max_completion_tokens"))
        assertFalse(json.has("thinking"))
        assertEquals("system text", json.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertEquals("user text", json.getJSONArray("messages").getJSONObject(1).getString("content"))
        assertFalse(json.toString().contains("sk-"))
    }

    @Test
    fun jsonNullContentIsSkipped() {
        assertEquals("", MimoProtocol.contentText(JSONObject.NULL))
        assertEquals("null", MimoProtocol.contentText("null"))
        val lines = listOf(
            """data: {"choices":[{"delta":{"role":"assistant","content":null}}]}""",
            """data: {"choices":[{"delta":{"content":null}}]}""",
            """data: {"choices":[{"delta":{"content":"阶层"}}]}""",
        )
        assertEquals(listOf("阶层"), MimoProtocol.deltas(lines))
    }

    @Test
    fun sseJoinsContentDeltasAndStops() {
        val lines = listOf(
            """data: {"choices":[{"delta":{"content":"好"}}]}""",
            """data: {"choices":[{"delta":{"content":"词"}}]}""",
            "data: [DONE]",
            """data: {"choices":[{"delta":{"content":"忽略"}}]}""",
        )
        assertEquals(listOf("好", "词"), MimoProtocol.deltas(lines))
    }

    @Test
    fun replyTextReadsAssistantContent() {
        val raw = """{"choices":[{"message":{"content":"Hello there."}}]}"""
        assertEquals("Hello there.", MimoProtocol.replyText(raw))
        assertEquals("MiMo 请求失败", MimoProtocol.replyText("{}"))
    }
}
