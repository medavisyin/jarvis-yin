package com.jarvis.ir.mimo

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MimoAnalysisTest {
    @Test
    fun missingKeyDoesNotCallTransport() {
        var called = false
        val analysis = MimoAnalysis(key = { "" }) { _, _, _ -> called = true }
        try {
            analysis.run("vocab", "Emma", 0, "Hello.") {}
            throw AssertionError("expected missing key")
        } catch (e: MimoConfigException) {
            assertEquals(MimoKey.MISSING, e.message)
        }
        assertEquals(false, called)
    }

    @Test
    fun sendsSlicedPassageAndForwardsDeltas() {
        var seenKey = ""
        var seenBody = ""
        val analysis = MimoAnalysis(key = { "sk-1234567890abcd" }) { key, body, emit ->
            seenKey = key
            seenBody = body
            emit("句")
        }
        val parts = mutableListOf<String>()
        analysis.run("culture", "Emma", 1, "She walked.", parts::add)
        assertEquals("sk-1234567890abcd", seenKey)
        val json = JSONObject(seenBody)
        assertEquals("mimo-v2.6-flash", json.getString("model"))
        assertEquals(true, json.getBoolean("stream"))
        assertEquals(4096, json.getInt("max_completion_tokens"))
        assertFalse(json.has("thinking"))
        val user = json.getJSONArray("messages").getJSONObject(1).getString("content")
        assertTrue(user.contains("She walked."))
        assertEquals(listOf("句"), parts)
    }
}
