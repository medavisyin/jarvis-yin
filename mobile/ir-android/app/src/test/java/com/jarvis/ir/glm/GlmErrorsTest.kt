package com.jarvis.ir.glm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class GlmErrorsTest {
    @Test
    fun statusMapsWithoutTheBody() {
        assertEquals("GLM 请求过于频繁，请稍后再试", GlmErrors.forStatus(429))
        assertEquals("GLM 请求失败", GlmErrors.forStatus(500))
        assertEquals("没有返回内容", GlmErrors.EMPTY)
        assertFalse(GlmErrors.forStatus(401).contains("sk-"))
    }
}
