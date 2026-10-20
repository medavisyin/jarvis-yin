package com.jarvis.ir.ui

import android.content.Context
import android.content.SharedPreferences
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import java.util.Locale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.ParagraphStyle
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextIndent
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.jarvis.ir.books.ReadingDisplay
import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.mimo.MimoKey
import com.jarvis.ir.mimo.MimoTtsClient
import com.jarvis.ir.mimo.MimoTtsException
import com.jarvis.ir.speak.PassageSpeak
import com.jarvis.ir.notes.NoteExplanation
import com.jarvis.ir.explain.ExplainPipeline
import com.jarvis.ir.explain.GlossPrompt
import com.jarvis.ir.explain.GlossSession
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.roundToInt

@Composable
fun ReaderScreen(
    passage: String,
    pipeline: ExplainPipeline,
    gloss: GlossSession,
    glossModel: String,
    glossReady: Boolean,
    onModelRejected: () -> Unit = {},
    onNote: (String, String) -> Unit = { _, _ -> },
    onQuote: (String, String) -> Unit = { _, _ -> },
    heading: String? = null,
    onTurn: ((Int) -> Unit)? = null,
    mimoKey: String = "",
    modifier: Modifier = Modifier,
) {
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    var selection by remember(passage) { mutableStateOf<WordHit?>(null) }
    var anchor by remember(passage) { mutableIntStateOf(-1) }
    var card by remember(passage) { mutableStateOf<ExplainCard?>(null) }
    var glossLine by remember(passage) { mutableStateOf<String?>(null) }
    var glossLabel by remember(passage) { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var speaker by remember { mutableStateOf<TextToSpeech?>(null) }
    var speakReady by remember { mutableStateOf(false) }
    DisposableEffect(context) {
        var engine: TextToSpeech? = null
        engine = TextToSpeech(context) { status ->
            val created = engine ?: return@TextToSpeech
            val language = if (status == TextToSpeech.SUCCESS) {
                created.setLanguage(Locale.US)
            } else {
                TextToSpeech.LANG_NOT_SUPPORTED
            }
            val ready = status == TextToSpeech.SUCCESS &&
                language != TextToSpeech.LANG_MISSING_DATA &&
                language != TextToSpeech.LANG_NOT_SUPPORTED
            Handler(Looper.getMainLooper()).post {
                speaker = if (ready) created else null
                speakReady = ready
            }
        }
        onDispose {
            engine?.stop()
            engine?.shutdown()
            speaker = null
            speakReady = false
        }
    }
    var readBusy by remember(passage) { mutableStateOf(false) }
    var readError by remember(passage) { mutableStateOf("") }
    var resumeOffset by remember(passage) { mutableIntStateOf(0) }
    var readJob by remember(passage) { mutableStateOf<Job?>(null) }
    val readPlace = remember(passage) { mutableIntStateOf(0) }
    fun stopRead(keepPlace: Boolean) {
        readJob?.cancel()
        readJob = null
        speaker?.stop()
        readBusy = false
        if (keepPlace && readPlace.intValue > 0) resumeOffset = readPlace.intValue else if (!keepPlace) resumeOffset = 0
    }
    DisposableEffect(passage) {
        val prefs = context.getSharedPreferences(MimoKey.PREFS, Context.MODE_PRIVATE)
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (
                key == PassageSpeak.PREF_ENGINE ||
                key == PassageSpeak.PREF_VOICE_EN ||
                key == PassageSpeak.PREF_VOICE_ZH ||
                key == PassageSpeak.PREF_STYLE
            ) {
                stopRead(true)
            }
        }
        prefs.registerOnSharedPreferenceChangeListener(listener)
        onDispose {
            prefs.unregisterOnSharedPreferenceChangeListener(listener)
            stopRead(false)
        }
    }
    var glossJob by remember { mutableStateOf<Job?>(null) }
    val scroll = rememberScrollState()
    var viewportHeight by remember { mutableIntStateOf(0) }
    val highlighted = buildAnnotatedString {
        append(passage)
        val indent = ParagraphStyle(
            textIndent = TextIndent(firstLine = 28.sp),
            lineHeight = 34.sp,
        )
        paragraphRanges(passage).forEach { range ->
            addStyle(indent, range.first, range.last + 1)
        }
        val hit = selection
        if (hit != null && hit.end > hit.start) {
            addStyle(
                SpanStyle(background = MaterialTheme.colorScheme.secondaryContainer),
                hit.start,
                hit.end.coerceAtMost(passage.length),
            )
        }
    }

    fun startRead() {
        if (readBusy) {
            stopRead(true)
            return
        }
        val text = passage.trim()
        if (text.isEmpty()) return
        val prefs = context.getSharedPreferences(MimoKey.PREFS, Context.MODE_PRIVATE)
        val selected = PassageSpeak.choice(
            prefs.getString(PassageSpeak.PREF_ENGINE, null),
            prefs.getString(PassageSpeak.PREF_VOICE_EN, null),
            prefs.getString(PassageSpeak.PREF_VOICE_ZH, null),
            prefs.getString(PassageSpeak.PREF_STYLE, null),
        )
        val pageLang = PassageSpeak.lang(text)
        val gender = if (pageLang == "zh") selected.voiceZh else selected.voiceEn
        val max = if (selected.engine == "mimo") PassageSpeak.PASSAGE_CHUNK else PassageSpeak.BROWSER_CHUNK
        val pieces = PassageSpeak.chunks(text, max)
        if (pieces.isEmpty()) return
        val found = PassageSpeak.starts(text, pieces)
        val startAt = PassageSpeak.indexAt(found, resumeOffset)
        readError = ""
        readBusy = true
        readJob = scope.launch {
            try {
                if (selected.engine == "mimo") {
                    val key = try {
                        MimoKey.require(mimoKey)
                    } catch (e: Exception) {
                        readError = e.message ?: MimoKey.MISSING
                        return@launch
                    }
                    PassageSpeak.playPrefetched(
                        from = startAt,
                        until = pieces.size,
                        fetch = { index ->
                            val spoken = PassageSpeak.withStyle(pieces[index], selected.style)
                            MimoTtsClient.wav(key, PassageSpeak.ttsBody(spoken, pageLang, gender))
                        },
                        onChunk = { index -> readPlace.intValue = found[index] },
                        play = { wav -> playWav(context.cacheDir, wav) },
                    )
                } else {
                    val synth = speaker
                    if (synth == null) {
                        readError = "手机不能朗读"
                        return@launch
                    }
                    applySystemVoice(synth, pageLang, gender)
                    for (index in startAt until pieces.size) {
                        if (!isActive) return@launch
                        readPlace.intValue = found[index]
                        speakUtterance(synth, pieces[index])
                    }
                }
                if (isActive) {
                    readPlace.intValue = 0
                    resumeOffset = 0
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: MimoTtsException) {
                if (isActive) {
                    readError = e.message ?: MimoTtsClient.FAILED
                    if (readPlace.intValue > 0) resumeOffset = readPlace.intValue
                }
            } catch (_: Exception) {
                if (isActive) {
                    readError = "朗读失败"
                    if (readPlace.intValue > 0) resumeOffset = readPlace.intValue
                }
            } finally {
                readBusy = false
                readJob = null
            }
        }
    }
    Box(modifier.fillMaxSize()) {
    Column(
        Modifier
            .fillMaxSize()
            .background(readingPaper),
    ) {
    PassageSpeakBar(
        speaking = readBusy,
        canResume = resumeOffset > 0,
        error = readError,
        onToggle = { startRead() },
    )
    Column(
        Modifier
            .weight(1f)
            .padding(horizontal = 28.dp, vertical = 12.dp)
            .onSizeChanged { viewportHeight = it.height }
            .verticalScroll(scroll),
    ) {
        if (!heading.isNullOrBlank()) {
            Text(
                heading,
                color = readingInk,
                fontFamily = FontFamily.Serif,
                fontSize = 28.sp,
                lineHeight = 36.sp,
                modifier = Modifier.padding(bottom = 18.dp),
            )
        }
        Box {
            Text(
                text = highlighted,
                style = MaterialTheme.typography.bodyLarge.copy(
                    fontFamily = FontFamily.Serif,
                    fontSize = 20.sp,
                    lineHeight = 34.sp,
                    letterSpacing = 0.2.sp,
                    color = readingInk,
                ),
                onTextLayout = { layout = it },
                modifier = Modifier.pointerInput(passage, onTurn) {
                    detectTapGestures(
                        onLongPress = { offset ->
                            val index = indexAt(layout, passage, offset) ?: return@detectTapGestures
                            val hit = WordSelector.span(passage, index, index) ?: return@detectTapGestures
                            anchor = index
                            card = null
                            glossJob?.cancel()
                            glossLine = null
                            glossLabel = null
                            selection = hit
                        },
                        onTap = { offset ->
                            val turn = onTurn
                            if (turn != null) {
                                val delta = ReadingDisplay.edgeDelta(
                                    offset.x,
                                    size.width.toFloat(),
                                    56.dp.toPx(),
                                )
                                if (delta != null) {
                                    turn(delta)
                                    return@detectTapGestures
                                }
                            }
                            val start = anchor
                            if (start < 0 || selection == null) return@detectTapGestures
                            val index = indexAt(layout, passage, offset) ?: return@detectTapGestures
                            val hit = WordSelector.span(passage, start, index) ?: return@detectTapGestures
                            card = null
                            glossJob?.cancel()
                            glossLine = null
                            glossLabel = null
                            selection = hit
                        },
                        onDoubleTap = {
                            anchor = -1
                            selection = null
                            card = null
                            glossJob?.cancel()
                            glossLine = null
                            glossLabel = null
                        },
                    )
                },
            )
            val hit = selection
            val textLayout = layout
            if (hit != null && textLayout != null && hit.end > hit.start) {
                val spot = selectionBounds(textLayout, hit.start, hit.end)
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    modifier = Modifier.offset {
                        val buttonHeight = 40.dp.toPx()
                        val gap = 4.dp.toPx()
                        val top = explainButtonTop(
                            selectionTop = spot.top,
                            selectionBottom = spot.bottom,
                            viewportTop = scroll.value.toFloat(),
                            viewportBottom = scroll.value + viewportHeight.toFloat(),
                            buttonHeight = buttonHeight,
                            gap = gap,
                        )
                        val count = if (speakReady) 3 else 2
                        val rowWidth = 40.dp.toPx() * count + 56.dp.toPx() * 2 + gap * (count + 1)
                        val maxX = (textLayout.size.width - rowWidth).coerceAtLeast(0f)
                        IntOffset(spot.left.coerceIn(0f, maxX).roundToInt(), top.roundToInt())
                    },
                ) {
                    SelectionAction("词") {
                        val next = pipeline.dictionaryCard(hit.word, hit.sentence) ?: return@SelectionAction
                        card = next
                        glossJob?.cancel()
                        glossLabel = "词"
                        glossLine = null
                        if (glossReady) {
                            glossLine = if (GlossPrompt.isPhrase(hit.word)) {
                                "正在解释这个词组…"
                            } else {
                                "正在写这个词…"
                            }
                            glossJob = scope.launch {
                                val line = gloss.explainIfReady(glossModel, hit.word, hit.sentence)
                                glossLine = line
                                if (line != null && !gloss.downloaded(glossModel)) onModelRejected()
                            }
                        }
                    }
                    SelectionAction("句") {
                        val next = pipeline.dictionaryCard(hit.word, hit.sentence) ?: return@SelectionAction
                        card = next
                        glossJob?.cancel()
                        glossLabel = "句"
                        glossLine = null
                        if (glossReady) {
                            glossLine = "正在翻译这句…"
                            glossJob = scope.launch {
                                val line = gloss.translateIfReady(glossModel, hit.sentence)
                                glossLine = line
                                if (line != null && !gloss.downloaded(glossModel)) onModelRejected()
                            }
                        }
                    }
                    if (speakReady) {
                        SelectionAction("读") {
                            speaker?.speak(hit.word, TextToSpeech.QUEUE_FLUSH, null, "ir-word")
                        }
                    }
                    SelectionAction("笔记", width = 56.dp) {
                        val explanation = NoteExplanation.text(
                            card ?: pipeline.dictionaryCard(hit.word, hit.sentence),
                            glossLine,
                            glossLabel,
                        )
                        onNote(hit.word, explanation)
                    }
                    SelectionAction("摘句", width = 56.dp) {
                        val explanation = NoteExplanation.text(
                            card ?: pipeline.dictionaryCard(hit.word, hit.sentence),
                            glossLine,
                            glossLabel,
                        )
                        onQuote(hit.sentence, explanation)
                    }
                }
            }
        }
    }
    }
    }
    val shown = card
    if (shown != null) {
        Dialog(onDismissRequest = {
            glossJob?.cancel()
            card = null
            glossLine = null
            glossLabel = null
        }) {
            ExplainCardView(
                shown,
                glossLine = glossLine,
                glossLabel = glossLabel,
                onNote = selection?.let { hit ->
                    {
                        val saved = if (glossLabel == "句" && hit.sentence.isNotBlank()) hit.sentence else hit.word
                        onNote(saved, NoteExplanation.text(shown, glossLine, glossLabel))
                    }
                },
            )
        }
    }
}

private suspend fun speakUtterance(tts: TextToSpeech, text: String) {
    suspendCancellableCoroutine { cont ->
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) = Unit
            override fun onDone(utteranceId: String?) {
                if (cont.isActive) cont.resume(Unit)
            }
            override fun onError(utteranceId: String?) {
                if (cont.isActive) cont.resumeWithException(IllegalStateException("朗读失败"))
            }
        })
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), "ir-page")
        cont.invokeOnCancellation { tts.stop() }
    }
}

private suspend fun playWav(cacheDir: File, wav: ByteArray) {
    val file = File.createTempFile("ir-speak", ".wav", cacheDir)
    file.writeBytes(wav)
    suspendCancellableCoroutine { cont ->
        val player = MediaPlayer()
        fun finish(error: Throwable?) {
            player.release()
            file.delete()
            if (!cont.isActive) return
            if (error == null) cont.resume(Unit) else cont.resumeWithException(error)
        }
        player.setOnCompletionListener { finish(null) }
        player.setOnErrorListener { _, _, _ ->
            finish(IllegalStateException("朗读失败"))
            true
        }
        cont.invokeOnCancellation {
            player.release()
            file.delete()
        }
        try {
            player.setDataSource(file.absolutePath)
            player.prepare()
            player.start()
        } catch (e: Exception) {
            finish(e)
        }
    }
}

private fun applySystemVoice(tts: TextToSpeech, lang: String, gender: String) {
    val locale = if (lang == "zh") Locale.SIMPLIFIED_CHINESE else Locale.US
    val prefix = if (lang == "zh") "zh" else "en"
    val same = tts.voices.orEmpty().filter { it.locale.language.lowercase().startsWith(prefix) }
    val match = same.firstOrNull { voiceMatches(it, gender) } ?: same.firstOrNull()
    if (match != null) tts.voice = match else tts.language = locale
    tts.setSpeechRate(0.68f)
}

private fun voiceMatches(voice: Voice, gender: String): Boolean {
    val name = voice.name
    val female = Regex("female|\\bwoman\\b|\\bgirl\\b|女|zira|xiaoxiao", RegexOption.IGNORE_CASE).containsMatchIn(name)
    if (gender == "female") return female
    if (female) return false
    return Regex("\\bmale\\b|\\bman\\b|\\bboy\\b|男|david|yunjian", RegexOption.IGNORE_CASE).containsMatchIn(name)
}

private fun indexAt(layout: TextLayoutResult?, passage: String, offset: Offset): Int? {
    val layoutResult = layout ?: return null
    if (passage.isEmpty()) return null
    return layoutResult.getOffsetForPosition(offset).coerceIn(0, passage.lastIndex)
}

private data class SelectionBounds(val left: Float, val top: Float, val bottom: Float)

private fun selectionBounds(layout: TextLayoutResult, start: Int, endExclusive: Int): SelectionBounds {
    val lastIndex = layout.layoutInput.text.lastIndex.coerceAtLeast(0)
    val from = start.coerceIn(0, lastIndex)
    val to = (endExclusive - 1).coerceIn(from, lastIndex)
    val startBox = layout.getBoundingBox(from)
    val endBox = layout.getBoundingBox(to)
    return SelectionBounds(
        left = minOf(startBox.left, endBox.left),
        top = minOf(startBox.top, endBox.top),
        bottom = maxOf(startBox.bottom, endBox.bottom),
    )
}

@Composable
private fun SelectionAction(label: String, width: Dp = 40.dp, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.size(width = width, height = 40.dp),
        contentPadding = PaddingValues(0.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = readingInk,
            contentColor = readingPaper,
        ),
    ) {
        Text(label)
    }
}

internal fun explainButtonTop(
    selectionTop: Float,
    selectionBottom: Float,
    viewportTop: Float,
    viewportBottom: Float,
    buttonHeight: Float,
    gap: Float,
): Float {
    val below = selectionBottom + gap
    val above = selectionTop - gap - buttonHeight
    val fitsBelow = below + buttonHeight <= viewportBottom
    return if (fitsBelow) below else above.coerceAtLeast(viewportTop)
}
