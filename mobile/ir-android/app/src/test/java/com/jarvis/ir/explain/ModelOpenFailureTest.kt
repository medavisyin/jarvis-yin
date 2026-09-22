package com.jarvis.ir.explain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ModelOpenFailureTest {
    @Test
    fun keepsFilesAndShowsNativeError() {
        val text = ModelOpenFailure.message(
            nativeError = "Cannot open weight file: /data/models/qwen3-0.6/config.txt",
            engineMessage = "Failed to initialize model context",
        )
        assertFalse(text.contains("请再点一次下载"))
        assertEquals(
            "模型打不开。文件还在，不用重新下载。\nCannot open weight file: /data/models/qwen3-0.6/config.txt",
            text,
        )
    }

    @Test
    fun fallsBackToEngineMessageWhenNativeErrorIsBlank() {
        val text = ModelOpenFailure.message(nativeError = "  ", engineMessage = "init failed")
        assertEquals("模型打不开。文件还在，不用重新下载。\ninit failed", text)
    }
}
