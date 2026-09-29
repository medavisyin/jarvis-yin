package com.jarvis.ir.glm

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GlmAnalysisTest {
    @Test
    fun missingKeyDoesNotCallTransport() {
        var called = false
        val analysis = GlmAnalysis(key = { "" }) { _, _, _ -> called = true }
        try {
            analysis.run("vocab", "Emma", 0, "Hello.") {}
            throw AssertionError("expected missing key")
        } catch (e: GlmConfigException) {
            assertEquals(GlmKey.MISSING, e.message)
        }
        assertEquals(false, called)
    }

    @Test
    fun sendsSlicedPassageAndForwardsDeltas() {
        var seenKey = ""
        var seenBody = ""
        val analysis = GlmAnalysis(key = { "sk-1234567890abcd" }) { key, body, emit ->
            seenKey = key
            seenBody = body
            emit("句")
        }
        val parts = mutableListOf<String>()
        analysis.run("vocab", "Emma", 1, "She walked.", parts::add)
        assertEquals("sk-1234567890abcd", seenKey)
        val user = JSONObject(seenBody).getJSONArray("messages").getJSONObject(1).getString("content")
        assertTrue(user.contains("She walked."))
        assertEquals(listOf("句"), parts)
    }

    @Test
    fun lateDeltaFromAnOldRequestIsDropped() {
        val current = Any()
        val previous = Any()
        assertEquals(true, StreamGate.isCurrent(current, current))
        assertEquals(false, StreamGate.isCurrent(current, previous))
        assertEquals(false, StreamGate.isCurrent(null, previous))
    }
}
