package com.jarvis.ir.glm

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class GlmProtocolTest {
    @Test
    fun bodyDisablesThinkingAndOmitsTheKey() {
        val json = JSONObject(GlmProtocol.body("system text", "user text"))
        assertEquals("glm-4.7-flash", json.getString("model"))
        assertEquals(true, json.getBoolean("stream"))
        assertEquals(4096, json.getInt("max_tokens"))
        assertEquals("disabled", json.getJSONObject("thinking").getString("type"))
        assertEquals("system text", json.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertFalse(json.toString().contains("sk-"))
    }

    @Test
    fun sseJoinsContentDeltasAndStops() {
        val lines = listOf(
            """data: {"choices":[{"delta":{"content":"好"}}]}""",
            """data: {"choices":[{"delta":{"content":"词"}}]}""",
            "data: [DONE]",
            """data: {"choices":[{"delta":{"content":"忽略"}}]}""",
        )
        assertEquals(listOf("好", "词"), GlmProtocol.deltas(lines))
    }
}
