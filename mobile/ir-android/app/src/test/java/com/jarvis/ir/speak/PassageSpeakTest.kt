package com.jarvis.ir.speak

import org.json.JSONObject
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.Base64
import java.util.Collections

class PassageSpeakTest {
    @Test
    fun settingsFallBackToBrowserFemaleAndCalm() {
        assertEquals("browser", PassageSpeak.engine("edge"))
        assertEquals("mimo", PassageSpeak.engine("mimo"))
        assertEquals("female", PassageSpeak.gender(null))
        assertEquals("male", PassageSpeak.gender("male"))
        assertEquals(PassageSpeak.DEFAULT_STYLE, PassageSpeak.style("nope"))
        assertEquals("磁性", PassageSpeak.style("磁性"))
    }

    @Test
    fun languageFollowsTheMajorityScript() {
        assertEquals("zh", PassageSpeak.lang("这是一段很长的中文 only"))
        assertEquals("en", PassageSpeak.lang("Hello world"))
    }

    @Test
    fun longPageIsSplitAndChineseSentencesStayTogether() {
        val first = "中".repeat(300) + "。"
        val second = "文".repeat(300) + "。"
        assertEquals(listOf(first, second), PassageSpeak.chunks(first + second, 500))
        val packed = PassageSpeak.chunks("句".repeat(200) + "。" + "文".repeat(200) + "。" + "字".repeat(200) + "。", 500)
        assertEquals("句".repeat(200) + "。" + "文".repeat(200) + "。", packed[0])
    }

    @Test
    fun resumeUsesThePieceThatContainsTheOffset() {
        val text = "Alpha.\n\nBeta stays here."
        val pieces = PassageSpeak.chunks(text, 500)
        val found = PassageSpeak.starts(text, pieces)
        assertEquals(listOf(text.indexOf("Alpha."), text.indexOf("Beta")), found)
        assertEquals(1, PassageSpeak.indexAt(found, text.indexOf("Beta")))
        assertEquals(0, PassageSpeak.indexAt(found, 0))
    }

    @Test
    fun savedChoiceReplacesTheVoiceAndStyleFromWhenThePageOpened() {
        val saved = PassageSpeak.choice("mimo", "male", "female", "愤怒")
        assertEquals("mimo", saved.engine)
        assertEquals("male", saved.voiceEn)
        assertEquals("female", saved.voiceZh)
        assertEquals("愤怒", saved.style)
        val spoken = PassageSpeak.withStyle("Hello there.", saved.style)
        val json = JSONObject(PassageSpeak.ttsBody(spoken, "en", saved.voiceEn))
        assertEquals("(愤怒)Hello there.", json.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertFalse(json.has("extra_body"))
        assertEquals("Dean", json.getJSONObject("audio").getString("voice"))
    }

    @Test
    fun readerLoadsTheSavedChoiceWhenAReadStarts() {
        val source = readerSource()
        val start = source.substringAfter("fun startRead()")
        val body = start.substringBefore("\n    Box(")
        assertTrue(body.contains("PassageSpeak.choice("))
        assertTrue(body.contains("PassageSpeak.playPrefetched("))
        assertTrue(body.contains("MimoKey.PREFS"))
        assertFalse(body.contains("voiceZh else voiceEn"))
        assertFalse(body.contains("mimoStyle"))
        assertTrue(source.contains("registerOnSharedPreferenceChangeListener"))
    }

    @Test
    fun mimoRequestUsesTheGenderVoiceAndStylePrefix() {
        val spoken = PassageSpeak.withStyle("Hello there.", "平静")
        val json = JSONObject(PassageSpeak.ttsBody(spoken, "en", "male"))
        assertEquals("mimo-v2.5-tts", json.getString("model"))
        assertEquals("(平静)Hello there.", json.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertFalse(json.has("extra_body"))
        assertEquals("Dean", json.getJSONObject("audio").getString("voice"))
        assertEquals("Mia", PassageSpeak.mimoVoice("en", "female"))
        assertEquals("白桦", PassageSpeak.mimoVoice("zh", "male"))
        assertEquals("mimo_default", PassageSpeak.mimoVoice("zh", "female"))
        assertFalse(json.toString().contains("sk-"))
    }

    @Test
    fun nextChunkIsRequestedWhileTheCurrentChunkPlays() = runBlocking {
        val events = Collections.synchronizedList(mutableListOf<String>())
        PassageSpeak.playPrefetched(
            from = 0,
            until = 2,
            fetch = { index ->
                events.add("fetch-$index")
                byteArrayOf(index.toByte())
            },
            onChunk = {},
            play = { wav ->
                if (wav[0].toInt() == 0) {
                    val deadline = System.currentTimeMillis() + 1000
                    while ("fetch-1" !in events) {
                        if (System.currentTimeMillis() > deadline) error("next chunk was not requested during playback")
                        delay(5)
                    }
                }
                events.add("play-${wav[0]}")
            },
        )
        assertEquals(listOf("fetch-0", "fetch-1", "play-0", "play-1"), events.toList())
    }

    @Test
    fun failedNextChunkSurfacesAfterTheCurrentChunkPlays() = runBlocking {
        var played = false
        try {
            PassageSpeak.playPrefetched(
                from = 0,
                until = 2,
                fetch = { index ->
                    if (index == 1) throw IllegalStateException("next failed")
                    byteArrayOf(1)
                },
                onChunk = {},
                play = { played = true },
            )
            error("expected failure")
        } catch (e: IllegalStateException) {
            assertEquals("next failed", e.message)
            assertTrue(played)
        }
    }

    @Test
    fun wavBytesDecodesTheAudioField() {
        val payload = Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3))
        val raw = """{"choices":[{"message":{"audio":{"data":"$payload"}}}]}"""
        assertTrue(PassageSpeak.wavBytes(raw).contentEquals(byteArrayOf(1, 2, 3)))
    }

    private fun readerSource(): String {
        val candidates = listOf(
            File("src/main/java/com/jarvis/ir/ui/ReaderScreen.kt"),
            File("app/src/main/java/com/jarvis/ir/ui/ReaderScreen.kt"),
        )
        return candidates.firstOrNull { it.isFile }?.readText()
            ?: error("ReaderScreen.kt not found from ${File(".").absolutePath}")
    }
}
