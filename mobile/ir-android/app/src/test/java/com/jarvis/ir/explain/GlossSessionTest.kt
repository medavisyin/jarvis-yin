package com.jarvis.ir.explain

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GlossSessionTest {
    @Test
    fun choicesAreTheTwoQwenSlugs() {
        assertEquals(listOf("qwen3-0.6", "qwen3-1.7"), GlossSession.choices)
    }

    @Test
    fun explainDoesNotTouchTheModelUntilItIsDownloaded() = runBlocking {
        val engine = FakeEngine(downloaded = false)
        val session = GlossSession(engine)

        val line = session.explainIfReady("qwen3-0.6", "bank", "They sat on the river bank.")

        assertNull(line)
        assertFalse(engine.calls.any { it.startsWith("download:") || it.startsWith("complete:") })
    }

    @Test
    fun downloadFailureIsAMessageNotACrash() = runBlocking {
        val engine = FakeEngine(downloaded = false, downloadError = Exception("Failed to get model qwen3-0.6"))
        val session = GlossSession(engine)

        val status = session.download("qwen3-0.6")

        assertEquals("Failed to get model qwen3-0.6", status)
        assertFalse(session.downloaded("qwen3-0.6"))
    }

    @Test
    fun explainUsesTheSelectedModelAndDoesNotDownloadAgain() = runBlocking {
        val engine = FakeEngine(downloaded = true)
        val session = GlossSession(engine)

        val line = session.explainIfReady("qwen3-1.7", "bank", "They sat on the river bank.")

        assertEquals("岸", line)
        assertTrue(engine.calls.contains("complete:qwen3-1.7"))
        assertFalse(engine.calls.any { it.startsWith("download:") })
    }

    private class FakeEngine(
        private var downloaded: Boolean,
        private val downloadError: Exception? = null,
    ) : GlossEngine {
        val calls = mutableListOf<String>()

        override fun isDownloaded(slug: String): Boolean {
            calls += "is:$slug"
            return downloaded
        }

        override suspend fun download(slug: String, onStatus: (String) -> Unit) {
            calls += "download:$slug"
            downloadError?.let { throw it }
            downloaded = true
        }

        override suspend fun complete(slug: String, word: String, sentence: String): String {
            calls += "complete:$slug"
            return "岸"
        }

        override suspend fun translateSentence(slug: String, sentence: String): String {
            calls += "translate:$slug"
            return "他们坐在河岸上。"
        }
    }
}
