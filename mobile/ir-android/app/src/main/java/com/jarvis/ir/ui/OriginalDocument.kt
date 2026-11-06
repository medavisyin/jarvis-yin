package com.jarvis.ir.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Point
import android.graphics.pdf.PdfRenderer
import android.graphics.pdf.models.selection.SelectionBoundary
import android.os.Build
import android.os.ParcelFileDescriptor
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.View
import androidx.annotation.RequiresApi
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.widthIn
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.webkit.WebViewAssetLoader
import com.jarvis.ir.books.ChapterLocator
import com.jarvis.ir.books.ChapterSwipe
import com.jarvis.ir.books.EpubPages
import com.jarvis.ir.books.PdfImporter
import com.jarvis.ir.books.ReadingPosition
import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.explain.ExplainPipeline
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private data class PdfPagePicture(
    val image: androidx.compose.ui.graphics.ImageBitmap,
    val pageWidth: Int,
    val pageHeight: Int,
)

@Composable
fun OriginalDocument(
    file: File,
    kind: String,
    pipeline: ExplainPipeline,
    onNote: (String, String) -> Unit,
    chapterTitle: String = "",
    chapterExcerpt: String = "",
    chapterIndex: Int = 0,
    onChapterSwipe: (Int) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    if (kind == "pdf") {
        PdfOriginal(file, pipeline, onNote, chapterTitle, chapterExcerpt, chapterIndex, onChapterSwipe, modifier)
    } else {
        EpubOriginal(file, pipeline, onNote, chapterTitle, chapterExcerpt, chapterIndex, onChapterSwipe, modifier)
    }
}

@Composable
private fun PdfOriginal(
    file: File,
    pipeline: ExplainPipeline,
    onNote: (String, String) -> Unit,
    chapterTitle: String,
    chapterExcerpt: String,
    chapterIndex: Int,
    onChapterSwipe: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    var pageCount by remember(file) { mutableIntStateOf(0) }
    var pageIndex by rememberSaveable(file.absolutePath) { mutableIntStateOf(0) }
    var locatedTitle by rememberSaveable(file.absolutePath) { mutableStateOf("") }
    var picture by remember(file) { mutableStateOf<PdfPagePicture?>(null) }
    var pageTexts by remember(file) { mutableStateOf<List<String>?>(null) }
    var located by remember(file) { mutableStateOf(false) }
    var selected by remember(file) { mutableStateOf("") }
    var card by remember(file) { mutableStateOf<ExplainCard?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(file) {
        pageCount = withContext(Dispatchers.IO) { pdfPageCount(file) }
    }
    val chapterToken = ReadingPosition.token(chapterIndex, chapterTitle)
    LaunchedEffect(file, chapterToken, chapterExcerpt) {
        val title = chapterTitle.trim()
        val excerpt = chapterExcerpt.trim()
        if (ReadingPosition.keep(pageIndex, chapterToken, locatedTitle)) {
            located = true
            return@LaunchedEffect
        }
        if (title.isEmpty() && excerpt.isEmpty()) {
            located = true
            return@LaunchedEffect
        }
        val texts = pageTexts ?: withContext(Dispatchers.IO) {
            file.inputStream().use { PdfImporter.extractPages(it) }
        }
        pageTexts = texts
        val found = ChapterLocator.pageForChapter(texts, title, excerpt)
        if (found != null) pageIndex = found
        locatedTitle = chapterToken
        located = true
    }
    LaunchedEffect(file, pageIndex, located) {
        if (!located) return@LaunchedEffect
        picture = withContext(Dispatchers.IO) { renderPdfPage(file, pageIndex, 1200) }
    }
    Column(
        modifier
            .fillMaxSize()
            .chapterSwipe(onChapterSwipe),
    ) {
        SelectionActions(selected, card, pipeline, onNote) { card = it }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            TextButton(onClick = { if (pageIndex > 0) pageIndex -= 1 }, enabled = pageIndex > 0) { Text("上一页") }
            Text(if (pageCount == 0) "" else "${pageIndex + 1}/$pageCount")
            TextButton(
                onClick = { if (pageIndex < pageCount - 1) pageIndex += 1 },
                enabled = pageCount > 0 && pageIndex < pageCount - 1,
            ) { Text("下一页") }
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
            val page = picture ?: return@Box
            Image(
                bitmap = page.image,
                contentDescription = "第 ${pageIndex + 1} 页",
                contentScale = ContentScale.FillWidth,
                modifier = Modifier
                    .widthIn(max = 840.dp)
                    .fillMaxWidth()
                    .pointerInput(file, pageIndex, page.pageWidth, page.pageHeight) {
                        detectTapGestures { offset ->
                            if (Build.VERSION.SDK_INT < 35 || size.width <= 0 || size.height <= 0) return@detectTapGestures
                            val x = (offset.x / size.width * page.pageWidth).toInt()
                            val y = (offset.y / size.height * page.pageHeight).toInt()
                            scope.launch(Dispatchers.IO) {
                                val text = selectPdfWord(file, pageIndex, x, y)
                                withContext(Dispatchers.Main) {
                                    selected = text
                                    card = null
                                }
                            }
                        }
                    },
            )
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun EpubOriginal(
    file: File,
    pipeline: ExplainPipeline,
    onNote: (String, String) -> Unit,
    chapterTitle: String,
    chapterExcerpt: String,
    chapterIndex: Int,
    onChapterSwipe: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var pages by remember(file) { mutableStateOf<List<String>>(emptyList()) }
    var index by rememberSaveable(file.absolutePath) { mutableIntStateOf(0) }
    var locatedTitle by rememberSaveable(file.absolutePath) { mutableStateOf("") }
    var webView by remember { mutableStateOf<WebView?>(null) }
    val dest = remember(file) { File(context.cacheDir, "epub-${file.nameWithoutExtension}") }
    LaunchedEffect(file) {
        pages = withContext(Dispatchers.IO) { EpubPages.prepare(file.readBytes(), dest) }
    }
    val excerptNow = remember { ExcerptHolder() }
    excerptNow.text = chapterExcerpt
    val swipeNow = remember { SwipeHolder() }
    swipeNow.onSwipe = onChapterSwipe
    val chapterToken = ReadingPosition.token(chapterIndex, chapterTitle)
    LaunchedEffect(pages, chapterToken, chapterExcerpt) {
        if (pages.isEmpty()) return@LaunchedEffect
        val title = chapterTitle.trim()
        val excerpt = chapterExcerpt.trim()
        if (ReadingPosition.keep(index, chapterToken, locatedTitle)) return@LaunchedEffect
        if (title.isNotEmpty() || excerpt.isNotEmpty()) {
            val found = withContext(Dispatchers.IO) {
                EpubPages.chapterFile(pages, { href ->
                    val html = File(dest, href)
                    if (!html.isFile) "" else html.readText()
                }, title, excerpt)
            }
            if (found != null && found >= 0) index = found
        }
        locatedTitle = chapterToken
        webView?.let { scrollToExcerpt(it, excerpt) }
    }
    Box(modifier.fillMaxSize()) {
            if (pages.isNotEmpty()) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx ->
                        val loader = WebViewAssetLoader.Builder()
                            .addPathHandler("/book/", WebViewAssetLoader.InternalStoragePathHandler(ctx, dest))
                            .build()
                        WebView(ctx).apply {
                            settings.javaScriptEnabled = true
                            settings.allowFileAccess = false
                            settings.textZoom = 100
                            settings.defaultFontSize = 19
                            setBackgroundColor(readingPaper.toArgb())
                            setOnTouchListener(ChapterSwipeTouch(ctx) { delta -> swipeNow.onSwipe(delta) })
                            webViewClient = object : WebViewClient() {
                                override fun onPageFinished(view: WebView, url: String) {
                                    scrollToExcerpt(view, excerptNow.text)
                                }
                                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                                    val response = loader.shouldInterceptRequest(request.url) ?: return null
                                    val mime = EpubPages.documentMime(request.url.path.orEmpty(), response.mimeType)
                                    if (mime == null || mime == response.mimeType) return response
                                    return WebResourceResponse(
                                        mime,
                                        "utf-8",
                                        EpubPages.documentStatus(response.statusCode),
                                        "OK",
                                        response.responseHeaders ?: emptyMap(),
                                        response.data,
                                    )
                                }
                            }
                            webView = this
                        }
                    },
                    update = { view ->
                        val href = pages.getOrNull(index) ?: return@AndroidView
                        val target = "https://appassets.androidplatform.net/book/$href"
                        if (view.url != target) view.loadUrl(target)
                    },
                )
            }
    }
}

@Composable
private fun SelectionActions(
    selected: String,
    card: ExplainCard?,
    pipeline: ExplainPipeline,
    onNote: (String, String) -> Unit,
    setCard: (ExplainCard?) -> Unit,
) {
    Column {
        if (selected.isNotEmpty()) {
            Row {
                TextButton(onClick = { setCard(pipeline.dictionaryCard(selected, selected)) }) { Text("解释") }
                TextButton(onClick = {
                    val shown = card ?: pipeline.dictionaryCard(selected, selected)
                    if (shown != null) onNote(shown.word.ifBlank { selected }, noteText(shown))
                }) { Text("笔记") }
            }
        }
        card?.let { shown ->
            ExplainCardView(card = shown, onNote = { onNote(shown.word, noteText(shown)) })
        }
    }
}

private fun noteText(card: ExplainCard): String =
    listOf(card.translation, card.example).filter { it.isNotBlank() }.joinToString("\n")

private class ExcerptHolder {
    var text: String = ""
}

private class SwipeHolder {
    var onSwipe: (Int) -> Unit = {}
}

private fun Modifier.chapterSwipe(onSwipe: (Int) -> Unit): Modifier = pointerInput(onSwipe) {
    var totalX = 0f
    var totalY = 0f
    detectDragGestures(
        onDragStart = {
            totalX = 0f
            totalY = 0f
        },
        onDrag = { change, drag ->
            totalX += drag.x
            totalY += drag.y
            if (ChapterSwipe.delta(totalX, totalY, 72.dp.toPx()) != null) change.consume()
        },
        onDragEnd = {
            val decision = ChapterSwipe.delta(totalX, totalY, 72.dp.toPx())
            if (decision != null) onSwipe(decision)
        },
    )
}

private class ChapterSwipeTouch(
    context: android.content.Context,
    private val onSwipe: (Int) -> Unit,
) : View.OnTouchListener {
    private val minDistance = 72f * context.resources.displayMetrics.density
    private var downX = 0f
    private var downY = 0f
    private var fired = false
    private val detector = GestureDetector(
        context,
        object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent): Boolean = true

            override fun onFling(e1: MotionEvent?, e2: MotionEvent, velocityX: Float, velocityY: Float): Boolean {
                if (e1 == null || fired) return false
                val decision = ChapterSwipe.delta(e2.x - e1.x, e2.y - e1.y, minDistance) ?: return false
                fired = true
                onSwipe(decision)
                return true
            }
        },
    )

    override fun onTouch(v: View, event: MotionEvent): Boolean {
        detector.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                fired = false
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (!fired) {
                    val decision = ChapterSwipe.delta(event.x - downX, event.y - downY, minDistance)
                    if (decision != null) {
                        fired = true
                        onSwipe(decision)
                    }
                }
            }
        }
        return false
    }
}

private fun scrollToExcerpt(view: WebView, excerpt: String) {
    val needle = excerpt.trim().replace(Regex("""\s+"""), " ").take(40)
    if (needle.length < 12) return
    val quoted = buildString {
        append('"')
        needle.forEach { char ->
            when (char) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                else -> append(char)
            }
        }
        append('"')
    }
    view.evaluateJavascript(
        "(function(){var needle=$quoted.toLowerCase();var walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);var node;while((node=walker.nextNode())){var value=node.textContent.replace(/\\s+/g,' ').toLowerCase();if(value.indexOf(needle)>=0){var el=node.parentElement;if(el){el.scrollIntoView({block:'start'});}return;}}})();",
        null,
    )
}

private fun unescapeJsString(raw: String?): String {
    val text = raw?.trim().orEmpty()
    if (text == "null") return ""
    return text.trim('"').replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\")
}

private fun pdfPageCount(file: File): Int {
    return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
        PdfRenderer(descriptor).use { it.pageCount }
    }
}

private fun renderPdfPage(file: File, index: Int, widthPx: Int): PdfPagePicture? {
    ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
        PdfRenderer(descriptor).use { renderer ->
            if (index !in 0 until renderer.pageCount) return null
            renderer.openPage(index).use { page ->
                val width = widthPx.coerceAtLeast(1)
                val height = (page.height.toFloat() / page.width.coerceAtLeast(1) * width).toInt().coerceAtLeast(1)
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                bitmap.eraseColor(Color.WHITE)
                page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                return PdfPagePicture(bitmap.asImageBitmap(), page.width, page.height)
            }
        }
    }
}

@RequiresApi(35)
private fun selectPdfWord(file: File, pageIndex: Int, x: Int, y: Int): String {
    return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
        PdfRenderer(descriptor).use { renderer ->
            renderer.openPage(pageIndex).use { page ->
                val point = Point(x.coerceIn(0, page.width), y.coerceIn(0, page.height))
                val boundary = SelectionBoundary(point)
                page.selectContent(boundary, boundary)?.selectedTextContents?.joinToString(" ") { it.text }.orEmpty()
            }
        }
    }
}
