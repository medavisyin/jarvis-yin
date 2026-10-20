package com.jarvis.ir.speak

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.supervisorScope
import org.json.JSONArray
import org.json.JSONObject
import java.util.Base64

object PassageSpeak {
    const val PASSAGE_CHUNK = 500
    const val BROWSER_CHUNK = 120
    const val DEFAULT_STYLE = "平静"
    const val PREF_ENGINE = "speak_engine"
    const val PREF_VOICE_EN = "speak_voice_en"
    const val PREF_VOICE_ZH = "speak_voice_zh"
    const val PREF_STYLE = "speak_style"

    fun engine(raw: String?): String = if (raw == "mimo") "mimo" else "browser"

    fun gender(raw: String?): String = if (raw == "male") "male" else "female"

    fun style(raw: String?): String = if (raw != null && raw in STYLES) raw else DEFAULT_STYLE

    data class Choice(
        val engine: String,
        val voiceEn: String,
        val voiceZh: String,
        val style: String,
    )

    fun choice(engine: String?, voiceEn: String?, voiceZh: String?, style: String?): Choice = Choice(
        engine(engine),
        gender(voiceEn),
        gender(voiceZh),
        style(style),
    )

    val STYLES = listOf(
        "开心", "悲伤", "愤怒", "恐惧", "惊讶", "兴奋", "委屈", "平静", "冷漠",
        "怅然", "欣慰", "无奈", "愧疚", "释然", "嫉妒", "厌倦", "忐忑", "动情",
        "温柔", "高冷", "活泼", "严肃", "慵懒", "俏皮", "深沉", "干练", "凌厉",
        "磁性", "醇厚", "清亮", "空灵", "稚嫩", "苍老", "甜美", "沙哑", "醇雅",
        "夹子音", "御姐音", "正太音", "大叔音", "台湾腔",
        "东北话", "四川话", "河南话", "粤语",
        "孙悟空", "林黛玉",
        "唱歌",
    )

    private val sentenceMark = setOf('.', '!', '?', '。', '！', '？')

    fun lang(text: String): String {
        var han = 0
        var latin = 0
        for (ch in text) {
            if (ch in '\u3400'..'\u9fff') han += 1
            else if (ch in 'A'..'Z' || ch in 'a'..'z') latin += 1
        }
        return if (han > latin) "zh" else "en"
    }

    fun chunks(text: String, max: Int = PASSAGE_CHUNK): List<String> {
        val out = mutableListOf<String>()
        for (para in text.split(Regex("\\n\\n+"))) {
            val body = para.trim()
            if (body.isEmpty()) continue
            if (body.length <= max) {
                out.add(body)
                continue
            }
            var buf = ""
            for (sentence in splitSentences(body)) {
                val part = sentence.trim()
                if (part.isEmpty()) continue
                if (part.length > max) {
                    if (buf.isNotEmpty()) {
                        out.add(buf)
                        buf = ""
                    }
                    pushHard(out, part, max)
                    continue
                }
                val joined = joinSentences(buf, part)
                if (buf.isEmpty()) {
                    buf = part
                } else if (joined.length <= max) {
                    buf = joined
                } else {
                    out.add(buf)
                    buf = part
                }
            }
            if (buf.isNotEmpty()) out.add(buf)
        }
        return out
    }

    fun starts(text: String, pieces: List<String>): List<Int> {
        val found = mutableListOf<Int>()
        var cursor = 0
        for (part in pieces) {
            val at = text.indexOf(part, cursor)
            val start = if (at >= 0) at else cursor
            found.add(start)
            cursor = start + part.length
        }
        return found
    }

    fun indexAt(found: List<Int>, offset: Int): Int {
        var index = 0
        for (i in found.indices) {
            if (found[i] <= offset) index = i else break
        }
        return index
    }

    fun withStyle(text: String, style: String): String {
        val body = text.trim()
        if (body.isEmpty() || body[0] == '(' || body[0] == '（' || body[0] == '[') return body
        return "($style)$body"
    }

    fun mimoVoice(lang: String, gender: String): String {
        val english = lang.lowercase().startsWith("en")
        return if (gender == "male") {
            if (english) "Dean" else "白桦"
        } else {
            if (english) "Mia" else "mimo_default"
        }
    }

    fun ttsBody(text: String, lang: String, gender: String): String {
        val root = JSONObject()
        root.put("model", "mimo-v2.5-tts")
        val messages = JSONArray()
        messages.put(JSONObject().put("role", "assistant").put("content", text))
        root.put("messages", messages)
        val audio = JSONObject()
            .put("format", "wav")
            .put("voice", mimoVoice(lang, gender))
        root.put("audio", audio)
        return root.toString()
    }

    fun wavBytes(raw: String): ByteArray {
        val message = JSONObject(raw)
            .getJSONArray("choices")
            .getJSONObject(0)
            .getJSONObject("message")
        val audio = message.optJSONObject("audio")
        val data = audio?.optString("data").orEmpty()
        if (data.isEmpty()) throw IllegalStateException("MiMo 没有返回音频")
        return Base64.getDecoder().decode(data)
    }

    suspend fun playPrefetched(
        from: Int,
        until: Int,
        fetch: (Int) -> ByteArray,
        onChunk: (Int) -> Unit,
        play: suspend (ByteArray) -> Unit,
    ) {
        if (from >= until) return
        supervisorScope {
            var upcoming = async(Dispatchers.IO) { fetch(from) }
            for (index in from until until) {
                ensureActive()
                onChunk(index)
                val wav = upcoming.await()
                ensureActive()
                val next = if (index + 1 < until) async(Dispatchers.IO) { fetch(index + 1) } else null
                play(wav)
                ensureActive()
                if (next == null) return@supervisorScope
                upcoming = next
            }
        }
    }

    private fun splitSentences(body: String): List<String> {
        val sentences = mutableListOf<String>()
        val buf = StringBuilder()
        for (ch in body) {
            buf.append(ch)
            if (ch in sentenceMark) {
                val trimmed = buf.toString().trim()
                if (trimmed.isNotEmpty()) sentences.add(trimmed)
                buf.setLength(0)
            }
        }
        val rest = buf.toString().trim()
        if (rest.isNotEmpty()) sentences.add(rest)
        return sentences
    }

    private fun pushHard(out: MutableList<String>, text: String, max: Int) {
        var i = 0
        while (i < text.length) {
            val end = (i + max).coerceAtMost(text.length)
            val piece = text.substring(i, end).trim()
            if (piece.isNotEmpty()) out.add(piece)
            i += max
        }
    }

    private fun joinSentences(left: String, right: String): String {
        if (left.isEmpty()) return right
        if (left.last().isWhitespace() || right.first().isWhitespace()) return left + right.trimStart()
        val cjk = left.last() in '\u3400'..'\u9fff' || left.last() in "。！？" ||
            right.first() in '\u3400'..'\u9fff'
        return if (cjk) left + right else "$left $right"
    }
}
