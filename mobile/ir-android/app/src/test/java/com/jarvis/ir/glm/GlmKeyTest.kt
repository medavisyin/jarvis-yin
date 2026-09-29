package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Test

class GlmKeyTest {
    @Test
    fun maskHidesTheMiddle() {
        assertEquals("sk-1****abcd", GlmKey.mask("sk-1234567890abcd"))
        assertEquals("", GlmKey.mask(""))
        assertEquals("****", GlmKey.mask("short"))
    }

    @Test
    fun blankKeyThrowsBeforeAnyRequest() {
        try {
            GlmKey.require("  ")
            throw AssertionError("expected GlmConfigException")
        } catch (e: GlmConfigException) {
            assertEquals("还没有 GLM 密钥", e.message)
        }
    }
}
