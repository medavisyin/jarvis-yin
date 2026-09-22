package com.jarvis.ir.explain

import org.junit.Assert.assertEquals
import org.junit.Test

class GlossModelStoreTest {
    @Test
    fun keepsAKnownModelAndFallsBackToSmall() {
        assertEquals("qwen3-1.7", GlossModelStore.normalize("qwen3-1.7"))
        assertEquals("qwen3-0.6", GlossModelStore.normalize(null))
        assertEquals("qwen3-0.6", GlossModelStore.normalize("qwen3-4b"))
    }
}
