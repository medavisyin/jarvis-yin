package com.jarvis.ir.ui

import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
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
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.explain.ExplainPipeline
import com.jarvis.ir.explain.GlossPrompt
import com.jarvis.ir.explain.GlossSession
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
fun ReaderScreen(
    passage: String,
    pipeline: ExplainPipeline,
    gloss: GlossSession,
    glossModel: String,
    glossReady: Boolean,
    onModelRejected: () -> Unit = {},
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
            engine?.shutdown()
            speaker = null
            speakReady = false
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

    Column(
        modifier
            .fillMaxSize()
            .background(readingPaper)
            .padding(horizontal = 28.dp, vertical = 20.dp)
            .onSizeChanged { viewportHeight = it.height }
            .verticalScroll(scroll),
    ) {
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
                modifier = Modifier.pointerInput(passage) {
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
                        val rowWidth = 40.dp.toPx() * count + gap * (count - 1)
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
            ExplainCardView(shown, glossLine = glossLine, glossLabel = glossLabel)
        }
    }
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
private fun SelectionAction(label: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.size(40.dp),
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
