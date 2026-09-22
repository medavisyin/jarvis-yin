package com.cactus

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class CactusReplyTest {
    @Test
    fun readsResponseWhenErrorFieldIsNull() {
        val raw = """{"success":true,"error":null,"cloud_handoff":false,"response":"河岸"}"""
        assertEquals("河岸", CactusReply.text(raw))
    }

    @Test
    fun throwsWhenErrorIsAMessage() {
        val raw = """{"success":false,"error":"Cannot generate from empty prompt","response":null}"""
        try {
            CactusReply.text(raw)
            fail("expected CactusException")
        } catch (e: CactusException) {
            assertEquals("Cannot generate from empty prompt", e.message)
        }
    }

    @Test
    fun blankWhenResponseIsNull() {
        val raw = """{"success":false,"error":null,"cloud_handoff":true,"response":null}"""
        assertEquals("", CactusReply.text(raw))
    }
}
