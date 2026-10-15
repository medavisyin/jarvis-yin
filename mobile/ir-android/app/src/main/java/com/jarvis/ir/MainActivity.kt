package com.jarvis.ir

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.jarvis.ir.analysis.AnalysisSave
import com.jarvis.ir.analysis.AnalysisShare
import com.jarvis.ir.analysis.PageAnalysisStore
import com.jarvis.ir.books.BookChapters
import com.jarvis.ir.books.BookOpen
import com.jarvis.ir.books.ChapterJump
import com.jarvis.ir.books.ReadingDisplay
import com.jarvis.ir.books.ReadingGroups
import com.jarvis.ir.books.EconomistMessages
import com.jarvis.ir.books.EpubImporter
import com.jarvis.ir.books.LocalImport
import com.jarvis.ir.books.LocalImportMessages
import com.jarvis.ir.books.PdfImporter
import com.jarvis.ir.books.ShelfEntry
import com.jarvis.ir.books.ShelfStore
import com.jarvis.ir.analysis.AnalysisProvider
import com.jarvis.ir.books.TxtImporter
import com.jarvis.ir.notes.Note
import com.jarvis.ir.notes.NoteStore
import com.jarvis.ir.explain.ModelFiles
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.jarvis.ir.dict.DictionaryRepository
import com.jarvis.ir.dict.LemmaMap
import com.jarvis.ir.dict.SqliteDict
import com.jarvis.ir.explain.CactusGlossEngine
import com.jarvis.ir.explain.ExplainPipeline
import com.jarvis.ir.explain.GlossModelStore
import com.jarvis.ir.explain.GlossSession
import com.jarvis.ir.glm.GlmAnalysis
import com.jarvis.ir.glm.GlmConfigException
import com.jarvis.ir.glm.GlmErrors
import com.jarvis.ir.glm.GlmHttpException
import com.jarvis.ir.glm.GlmKey
import com.jarvis.ir.mimo.HttpMimoTransport
import com.jarvis.ir.mimo.MimoAnalysis
import com.jarvis.ir.mimo.MimoConfigException
import com.jarvis.ir.mimo.MimoHttpException
import com.jarvis.ir.mimo.MimoKey
import com.jarvis.ir.mimo.MimoProtocol
import com.jarvis.ir.glm.GlmProtocol
import com.jarvis.ir.glm.HttpGlmTransport
import com.jarvis.ir.glm.StreamGate
import com.jarvis.ir.ui.AnalysisPane
import com.jarvis.ir.ui.EconomistPicker
import com.jarvis.ir.ui.NotesScreen
import com.jarvis.ir.ui.showPageControls
import com.jarvis.ir.ui.ReaderScreen
import com.jarvis.ir.ui.SettingsDialog
import com.jarvis.ir.ui.ShelfScreen
import com.jarvis.ir.ui.analysisBesidePassage
import com.jarvis.ir.ui.readingInk
import com.jarvis.ir.ui.readingPaper
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private var sqlite: SqliteDict? = null
    private var chunks by mutableStateOf(listOf<String>())
    private var chunkTitles by mutableStateOf(listOf<String>())
    private var chunkIndex by mutableIntStateOf(0)
    private val chapterJump = ChapterJump()
    private var chapterJumpTick by mutableIntStateOf(0)
    private var showChapters by mutableStateOf(false)
    private var importError by mutableStateOf<String?>(null)
    private var showSettings by mutableStateOf(false)
    private var showEconomist by mutableStateOf(false)
    private var showShelf by mutableStateOf(true)
    private var showNotes by mutableStateOf(false)
    private var notes by mutableStateOf(listOf<Note>())
    private lateinit var noteStore: NoteStore
    private var bookTitle by mutableStateOf("样例")
    private var bookId by mutableStateOf<String?>(null)
    private var readKeys by mutableStateOf(setOf<String>())
    private var shelfBooks by mutableStateOf(listOf<ShelfEntry>())
    private lateinit var shelfStore: ShelfStore
    private lateinit var pageAnalysis: PageAnalysisStore
    private var shelfReady = false
    private val gloss = GlossSession(CactusGlossEngine())
    private var glossModel by mutableStateOf(GlossSession.MODEL_06)
    private var glossStatus by mutableStateOf(GlossSession.NOT_DOWNLOADED)
    private var glossBusy by mutableStateOf(false)
    private var glossReady by mutableStateOf(false)
    private var analysisProvider by mutableStateOf(AnalysisProvider.GLM)
    private var glmKey by mutableStateOf("")
    private var glmStatus by mutableStateOf("")
    private var glmBusy by mutableStateOf(false)
    private var mimoKey by mutableStateOf("")
    private var mimoStatus by mutableStateOf("")
    private var mimoBusy by mutableStateOf(false)
    private var analysisText by mutableStateOf("")
    private var analysisError by mutableStateOf("")
    private var analysisRunning by mutableStateOf(false)
    private var analysisKind by mutableStateOf<String?>(null)
    private var analysisSaved by mutableStateOf(false)
    private var showAnalysis by mutableStateOf(false)
    private var analysisJob: Job? = null
    private var analysisTransport: Any? = null

    private val openLocal = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        importLocal(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PDFBoxResourceLoader.init(applicationContext)
        ModelFiles.filesDir = filesDir
        val modelPrefs = getSharedPreferences(GlossModelStore.PREFS, Context.MODE_PRIVATE)
        glossModel = GlossModelStore.normalize(modelPrefs.getString(GlossModelStore.KEY, null))
        analysisProvider = AnalysisProvider.normalize(
            modelPrefs.getString(AnalysisProvider.PREF_KEY, null),
        )
        glmKey = modelPrefs.getString(GlmKey.PREF_KEY, "").orEmpty()
        mimoKey = modelPrefs.getString(MimoKey.PREF_KEY, "").orEmpty()
        shelfStore = ShelfStore(File(filesDir, "shelf"))
        pageAnalysis = PageAnalysisStore(File(filesDir, "shelf"))
        noteStore = NoteStore(File(filesDir, "notes/notes.json"))
        notes = noteStore.list()
        shelfReady = true
        shelfBooks = shelfStore.list()
        restoreLastBook()
        glossReady = gloss.downloaded(glossModel)
        glossStatus = GlossSession.statusFor(glossReady)
        val dictFile = copyAsset("ecdict.db")
        sqlite = SqliteDict(dictFile)
        val lemma = LemmaMap.load(assets.open("lemma.en.txt").bufferedReader().use { it.readText() })
        val pipeline = ExplainPipeline(
            dict = DictionaryRepository(lemma, sqlite!!::lookupExact),
        )
        setContent {
            MaterialTheme {
                val scope = rememberCoroutineScope()
                val readingPages = ReadingGroups.pages(chunkTitles, chunks)
                val shelfCaptions = remember(shelfBooks, showShelf) {
                    if (!showShelf) {
                        emptyMap()
                    } else {
                        shelfBooks.associate { book -> book.id to shelfCaption(book) }
                    }
                }
                Column(Modifier.fillMaxSize().background(readingPaper)) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (showNotes) {
                            TextButton(onClick = { showNotes = false }) { Text("返回") }
                        } else {
                            if (!showShelf) {
                                TextButton(onClick = {
                                    chapterJump.reset()
                                    resetAnalysis()
                                    showShelf = true
                                }) { Text("书架") }
                            }
                            TextButton(onClick = {
                                notes = noteStore.list()
                                showNotes = true
                            }) { Text("笔记") }
                        }
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (showNotes) "笔记" else if (showShelf) "书架" else bookTitle,
                                color = readingInk,
                                fontSize = 18.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                            val here = readingPages.getOrNull(chunkIndex)
                            val chrome = if (
                                showPageControls(showNotes, showShelf, chunks.isNotEmpty()) &&
                                here != null
                            ) {
                                ReadingDisplay.chrome(here, chunkIndex)
                            } else {
                                null
                            }
                            if (chrome?.section != null) {
                                Text(
                                    chrome.section,
                                    color = readingInk.copy(alpha = 0.7f),
                                    fontSize = 12.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                            if (chrome?.article != null) {
                                Text(
                                    chrome.article,
                                    color = readingInk,
                                    fontSize = 14.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        }
                        if (showPageControls(showNotes, showShelf, chunks.isNotEmpty())) {
                            Text(
                                "${chunkIndex + 1}/${chunks.size}",
                                color = readingInk,
                                fontSize = 14.sp,
                                modifier = Modifier.padding(end = 4.dp),
                            )
                            val here = readingPages.getOrNull(chunkIndex)
                            val nextArticle = if (here != null) {
                                ReadingGroups.nextStart(readingPages, chunkIndex)
                            } else {
                                null
                            }
                            if (nextArticle != null) {
                                TextButton(
                                    onClick = {
                                        chapterJump.request(nextArticle)
                                        chapterJumpTick += 1
                                    },
                                    modifier = Modifier.width(72.dp),
                                ) { Text("下一篇") }
                            }
                            TextButton(onClick = { showChapters = true }) { Text("章节") }
                        }
                        TextButton(onClick = { showSettings = true }) { Text("设置") }
                    }
                    if (showNotes) {
                        NotesScreen(
                            notes = notes,
                            onDelete = { id -> deleteNote(id) },
                            onShare = { note ->
                                val base = AnalysisShare.body(note.title, note.content)
                                val explanation = note.explanation.trim()
                                shareAnalysis(if (explanation.isEmpty()) base else "$base\n\n$explanation")
                            },
                            modifier = Modifier.weight(1f),
                        )
                    } else if (showShelf) {
                        ShelfScreen(
                            books = shelfBooks,
                            onOpen = { openEntry(it) },
                            onDelete = { deleteBook(it) },
                            onRetitle = { retitleBook(it) },
                            onSample = if (shelfBooks.isEmpty()) {
                                { openSample() }
                            } else {
                                null
                            },
                            caption = { book ->
                                shelfCaptions[book.id]
                                    ?: "上次读到 ${book.chunkIndex + 1}/${book.chunkCount}"
                            },
                            modifier = Modifier.weight(1f),
                        )
                    } else if (chunks.isNotEmpty()) {
                        BoxWithConstraints(Modifier.weight(1f)) {
                            val wide = analysisBesidePassage(maxWidth.value.toInt())
                            val passage: @Composable (Modifier) -> Unit = { passageModifier ->
                                Box(passageModifier) {
                                    key(bookId ?: "sample") {
                                        val pagerState = rememberPagerState(
                                            initialPage = chunkIndex.coerceIn(0, chunks.lastIndex),
                                            pageCount = { chunks.size },
                                        )
                                        LaunchedEffect(pagerState.settledPage) {
                                            moveChunk(pagerState.settledPage)
                                        }
                                        LaunchedEffect(chapterJumpTick) {
                                            chapterJump.consume { page ->
                                                pagerState.scrollToPage(page.coerceIn(0, chunks.lastIndex))
                                            }
                                        }
                                        HorizontalPager(
                                            state = pagerState,
                                            modifier = Modifier.fillMaxSize(),
                                            userScrollEnabled = chunks.size > 1,
                                        ) { page ->
                                            val info = readingPages.getOrNull(page)
                                            val stored = chunks.getOrElse(page) { "" }
                                            val shown = if (info != null) {
                                                ReadingDisplay.show(info, stored)
                                            } else {
                                                ReadingDisplay.Passage(null, stored)
                                            }
                                            ReaderScreen(
                                                passage = shown.body,
                                                pipeline = pipeline,
                                                gloss = gloss,
                                                glossModel = glossModel,
                                                glossReady = glossReady,
                                                onNote = { selected, explanation ->
                                                    saveNote(bookTitle, selected, explanation)
                                                },
                                                onQuote = { sentence, explanation ->
                                                    saveNote(bookTitle, sentence, explanation)
                                                },
                                                onModelRejected = {
                                                    glossReady = false
                                                    glossStatus = GlossSession.NOT_DOWNLOADED
                                                },
                                                heading = shown.heading,
                                                onTurn = if (
                                                    info != null &&
                                                    ReadingDisplay.allowsEdge(info.magazine) &&
                                                    chunks.size > 1
                                                ) {
                                                    { delta ->
                                                        val target = ReadingDisplay.turnedIndex(
                                                            pagerState.settledPage,
                                                            delta,
                                                            chunks.size,
                                                        )
                                                        if (target != null) {
                                                            chapterJump.request(target)
                                                            chapterJumpTick += 1
                                                        }
                                                    }
                                                } else {
                                                    null
                                                },
                                                modifier = Modifier.fillMaxSize(),
                                            )
                                        }
                                    }
                                }
                            }
                            val pane = @Composable { paneModifier: Modifier ->
                                AnalysisPane(
                                    text = analysisText,
                                    error = analysisError,
                                    running = analysisRunning,
                                    bookTitle = bookTitle,
                                    onRun = { kind -> openAnalysis(kind, scope) },
                                    onCancel = { cancelAnalysis() },
                                    onShare = { body -> shareAnalysis(body) },
                                    onNote = { paragraph -> saveNote(bookTitle, paragraph) },
                                    onRewrite = if (analysisSaved && analysisKind != null) {
                                        { analysisKind?.let { startAnalysis(it, scope) } }
                                    } else {
                                        null
                                    },
                                    modifier = paneModifier,
                                )
                            }
                            if (wide) {
                                Row(Modifier.fillMaxSize()) {
                                    passage(Modifier.weight(1f).fillMaxHeight())
                                    pane(Modifier.width(360.dp).fillMaxHeight())
                                }
                            } else {
                                Box(Modifier.fillMaxSize()) {
                                    passage(Modifier.fillMaxSize())
                                    TextButton(
                                        onClick = { showAnalysis = true },
                                        modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp),
                                    ) { Text("分析") }
                                }
                                if (showAnalysis) {
                                    Dialog(onDismissRequest = { showAnalysis = false }) {
                                        pane(
                                            Modifier
                                                .fillMaxWidth()
                                                .heightIn(min = 320.dp, max = 640.dp)
                                                .background(readingPaper),
                                        )
                                    }
                                }
                            }
                        }
                    }
                    if (showSettings) {
                        SettingsDialog(
                            onDismiss = {
                                saveGlossModel(glossModel)
                                showSettings = false
                            },
                            onOpenLocal = {
                                openLocal.launch(
                                    arrayOf(
                                        "text/plain",
                                        "application/epub+zip",
                                        "application/pdf",
                                        "application/octet-stream",
                                    ),
                                )
                            },
                            onOpenEconomist = { showEconomist = true },
                            glossSelected = glossModel,
                            glossStatus = glossStatus,
                            glossBusy = glossBusy,
                            onSelectModel = { slug ->
                                glossModel = slug
                                saveGlossModel(slug)
                                glossReady = gloss.downloaded(slug)
                                glossStatus = GlossSession.statusFor(glossReady)
                            },
                            analysisProvider = analysisProvider,
                            onSelectAnalysisProvider = { id ->
                                val selected = AnalysisProvider.normalize(id)
                                analysisProvider = selected
                                getSharedPreferences(GlossModelStore.PREFS, Context.MODE_PRIVATE)
                                    .edit()
                                    .putString(AnalysisProvider.PREF_KEY, selected)
                                    .apply()
                            },
                            onDownload = {
                                val slug = glossModel
                                glossBusy = true
                                glossStatus = "正在下载 0%"
                                scope.launch {
                                    glossStatus = gloss.download(slug) { status ->
                                        runOnUiThread { glossStatus = status }
                                    }
                                    glossReady = gloss.downloaded(slug)
                                    glossBusy = false
                                }
                            },
                            glmMasked = GlmKey.mask(glmKey),
                            glmStatus = glmStatus,
                            glmBusy = glmBusy,
                            onSaveGlm = { raw ->
                                val trimmed = raw.trim()
                                getSharedPreferences(GlmKey.PREFS, Context.MODE_PRIVATE)
                                    .edit()
                                    .putString(GlmKey.PREF_KEY, trimmed)
                                    .apply()
                                glmKey = trimmed
                                glmStatus = "已保存"
                            },
                            onTestGlm = { draft ->
                                glmBusy = true
                                glmStatus = "测试中…"
                                scope.launch {
                                    val message = withContext(Dispatchers.IO) {
                                        probeGlm(if (draft.isNotBlank()) draft else glmKey)
                                    }
                                    glmStatus = message
                                    glmBusy = false
                                }
                            },
                            mimoMasked = MimoKey.mask(mimoKey),
                            mimoStatus = mimoStatus,
                            mimoBusy = mimoBusy,
                            onSaveMimo = { raw ->
                                val trimmed = raw.trim()
                                getSharedPreferences(MimoKey.PREFS, Context.MODE_PRIVATE)
                                    .edit()
                                    .putString(MimoKey.PREF_KEY, trimmed)
                                    .apply()
                                mimoKey = trimmed
                                mimoStatus = "已保存"
                            },
                            onTestMimo = { draft ->
                                mimoBusy = true
                                mimoStatus = "测试中…"
                                scope.launch {
                                    val message = withContext(Dispatchers.IO) {
                                        probeMimo(if (draft.isNotBlank()) draft else mimoKey)
                                    }
                                    mimoStatus = message
                                    mimoBusy = false
                                }
                            },
                        )
                    }
                    if (showEconomist) {
                        EconomistPicker(
                            cacheDir = cacheDir,
                            onDismiss = { showEconomist = false },
                            onImported = { title, kind, imported, titles ->
                                openSaved(shelfStore.save(title, kind, imported, titles = titles))
                                showSettings = false
                                showEconomist = false
                            },
                        )
                    }
                    if (showChapters) {
                        Dialog(onDismissRequest = { showChapters = false }) {
                            Column(
                                Modifier
                                    .fillMaxWidth()
                                    .background(readingPaper)
                                    .padding(16.dp),
                            ) {
                                Text("章节", color = readingInk, fontSize = 18.sp)
                                LazyColumn(Modifier.heightIn(max = 480.dp)) {
                                    itemsIndexed(ReadingGroups.menu(readingPages, readKeys)) { _, row ->
                                        val item = row as? ReadingGroups.MenuRow.Item
                                        Text(
                                            row.text,
                                            color = readingInk.copy(alpha = if (item == null) 0.7f else 1f),
                                            fontSize = if (item == null) 14.sp else 16.sp,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .then(
                                                    if (item == null) {
                                                        Modifier
                                                    } else {
                                                        Modifier.clickable {
                                                            showChapters = false
                                                            chapterJump.request(item.index)
                                                            chapterJumpTick += 1
                                                        }
                                                    },
                                                )
                                                .padding(vertical = if (item == null) 8.dp else 12.dp),
                                        )
                                    }
                                }
                            }
                        }
                    }
                    importError?.let { message ->
                        AlertDialog(
                            onDismissRequest = { importError = null },
                            text = { Text(message) },
                            confirmButton = {
                                TextButton(onClick = { importError = null }) { Text("关闭") }
                            },
                        )
                    }
                }
            }
        }
    }

    override fun onPause() {
        if (shelfReady) {
            bookId?.let { shelfStore.updatePosition(it, chunkIndex) }
        }
        super.onPause()
    }

    override fun onDestroy() {
        sqlite?.close()
        super.onDestroy()
    }

    private fun shelfCaption(book: ShelfEntry): String {
        val pages = ReadingGroups.pages(shelfStore.loadTitles(book.id), shelfStore.loadChunks(book.id))
        val line = ReadingDisplay.shelfLine(pages, book.chunkIndex, shelfStore.loadRead(book.id))
        return line ?: "上次读到 ${book.chunkIndex + 1}/${book.chunkCount}"
    }

    private fun restoreLastBook() {
        chapterJump.reset()
        val last = shelfStore.lastId()?.let { shelfStore.find(it) } ?: return
        val loaded = shelfStore.loadChunks(last.id)
        if (loaded.isEmpty()) return
        chunks = loaded
        chunkTitles = shelfStore.loadTitles(last.id)
        chunkIndex = last.chunkIndex.coerceIn(0, loaded.lastIndex)
        bookId = last.id
        bookTitle = last.title
        readKeys = shelfStore.loadRead(last.id)
        showShelf = false
        noteArticleProgress()
    }

    private fun openEntry(entry: ShelfEntry) {
        chapterJump.reset()
        val loaded = shelfStore.loadChunks(entry.id)
        val error = BookOpen.errorIfEmpty(loaded)
        if (error != null) {
            importError = error
            return
        }
        resetAnalysis()
        chunks = loaded
        chunkTitles = shelfStore.loadTitles(entry.id)
        chunkIndex = entry.chunkIndex.coerceIn(0, loaded.lastIndex)
        bookId = entry.id
        bookTitle = entry.title
        readKeys = shelfStore.loadRead(entry.id)
        shelfStore.updatePosition(entry.id, chunkIndex)
        noteArticleProgress()
        shelfBooks = shelfStore.list()
        showShelf = false
    }

    private fun openSample() {
        chapterJump.reset()
        resetAnalysis()
        val sample = assets.open("sample.txt").bufferedReader().use { it.readText() }
        chunks = listOf(sample)
        chunkTitles = emptyList()
        chunkIndex = 0
        bookId = null
        bookTitle = "样例"
        readKeys = emptySet()
        showShelf = false
    }

    private fun moveChunk(index: Int) {
        val next = index.coerceIn(0, chunks.lastIndex.coerceAtLeast(0))
        val changed = next != chunkIndex
        if (changed) {
            cancelAnalysis()
            analysisError = ""
            analysisText = ""
            analysisSaved = false
        }
        chunkIndex = next
        bookId?.let {
            shelfStore.updatePosition(it, chunkIndex)
            shelfBooks = shelfStore.list()
        }
        if (changed) restoreAnalysis()
        noteArticleProgress()
    }

    private fun noteArticleProgress() {
        val page = ReadingGroups.pages(chunkTitles, chunks).getOrNull(chunkIndex) ?: return
        if (!page.isLastPart) return
        val id = bookId ?: return
        if (page.readKey in readKeys) return
        if (!shelfStore.markRead(id, page.readKey)) return
        readKeys = readKeys + page.readKey
    }

    private fun saveNote(title: String, content: String, explanation: String = "") {
        noteStore.add(title, content, explanation)
        notes = noteStore.list()
    }

    private fun deleteNote(id: String) {
        if (noteStore.delete(id)) notes = noteStore.list()
    }

    private fun shareAnalysis(body: String) {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, body)
        }
        startActivity(Intent.createChooser(send, "分享"))
    }

    private fun cancelAnalysis() {
        analysisJob?.cancel()
        when (val transport = analysisTransport) {
            is HttpGlmTransport -> transport.cancel()
            is HttpMimoTransport -> transport.cancel()
        }
        analysisTransport = null
        analysisRunning = false
    }

    private fun resetAnalysis() {
        cancelAnalysis()
        analysisText = ""
        analysisError = ""
        analysisSaved = false
        analysisKind = null
        showAnalysis = false
    }

    private fun openAnalysis(kind: String, scope: CoroutineScope) {
        val saved = savedAnalysis(kind)
        analysisKind = kind
        if (saved.isNotBlank()) {
            cancelAnalysis()
            analysisText = saved
            analysisError = ""
            analysisSaved = true
            return
        }
        startAnalysis(kind, scope)
    }

    private fun restoreAnalysis() {
        val kind = analysisKind ?: return
        val saved = savedAnalysis(kind)
        analysisText = saved
        analysisSaved = saved.isNotBlank()
    }

    private fun savedAnalysis(kind: String): String {
        val id = bookId ?: return ""
        return pageAnalysis.load(id, chunkIndex, kind)
    }

    private fun startAnalysis(kind: String, scope: CoroutineScope) {
        cancelAnalysis()
        analysisKind = kind
        analysisText = ""
        analysisError = ""
        analysisSaved = false
        analysisRunning = true
        val title = bookTitle
        val index = chunkIndex
        val passage = chunks.getOrElse(index) { "" }
        val useMimo = analysisProvider == AnalysisProvider.MIMO
        val transport = if (useMimo) HttpMimoTransport() else HttpGlmTransport()
        analysisTransport = transport
        var completed = false
        analysisJob = scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    val emit: (String) -> Unit = { delta ->
                        runOnUiThread {
                            if (StreamGate.isCurrent(analysisTransport, transport)) {
                                analysisText += delta
                            }
                        }
                    }
                    if (transport is HttpMimoTransport) {
                        MimoAnalysis(key = { mimoKey }, transport = transport).run(kind, title, index, passage, emit)
                    } else {
                        GlmAnalysis(key = { glmKey }, transport = transport as HttpGlmTransport)
                            .run(kind, title, index, passage, emit)
                    }
                }
                completed = true
            } catch (_: CancellationException) {
                // Keep text already received.
            } catch (e: GlmConfigException) {
                if (StreamGate.isCurrent(analysisTransport, transport)) {
                    analysisError = e.message ?: GlmKey.MISSING
                }
            } catch (e: MimoConfigException) {
                if (StreamGate.isCurrent(analysisTransport, transport)) {
                    analysisError = e.message ?: MimoKey.MISSING
                }
            } catch (e: GlmHttpException) {
                if (StreamGate.isCurrent(analysisTransport, transport)) {
                    analysisError = e.message ?: GlmErrors.FAILED
                }
            } catch (e: MimoHttpException) {
                if (StreamGate.isCurrent(analysisTransport, transport)) {
                    analysisError = e.message ?: MimoProtocol.FAILED
                }
            } catch (e: Exception) {
                Log.w(if (useMimo) "MiMo" else "Glm", "request failed: ${e.javaClass.simpleName}")
                if (StreamGate.isCurrent(analysisTransport, transport)) {
                    analysisError = if (useMimo) MimoProtocol.FAILED else GlmErrors.FAILED
                }
            } finally {
                if (analysisTransport === transport) {
                    if (AnalysisSave.shouldPersist(completed, analysisError, analysisText)) {
                        val id = bookId
                        if (id != null && pageAnalysis.save(id, index, kind, analysisText.trim())) {
                            analysisSaved = true
                        }
                    }
                    analysisRunning = false
                }
            }
        }
    }

    private fun importLocal(uri: Uri?) {
        if (uri == null) return
        val probe = LocalImport.probe(
            name = { displayName(uri) },
            mime = { contentResolver.getType(uri) },
        )
        val kind = probe.kind
        if (probe.error != null || kind == null) {
            importError = probe.error ?: LocalImportMessages.UNKNOWN
            return
        }
        try {
            val imported = contentResolver.openInputStream(uri)?.use { input ->
                when (kind) {
                    "epub" -> EpubImporter.importLocal(input)
                    "pdf" -> PdfImporter.importLocal(input)
                    else -> TxtImporter.importLocal(input.readBytes())
                }
            }
            if (imported.isNullOrEmpty()) {
                importError = EconomistMessages.IMPORT
                return
            }
            val title = probe.name ?: kind.uppercase()
            openSaved(
                shelfStore.save(
                    title,
                    kind,
                    imported.map { it.text },
                    titles = imported.map { it.title },
                ),
            )
            showSettings = false
        } catch (e: Exception) {
            Log.e("Y", "import failed", e)
            importError = EconomistMessages.IMPORT
        }
    }

    private fun openSaved(entry: ShelfEntry) {
        chapterJump.reset()
        resetAnalysis()
        chunks = shelfStore.loadChunks(entry.id)
        chunkTitles = shelfStore.loadTitles(entry.id)
        chunkIndex = 0
        bookId = entry.id
        bookTitle = entry.title
        readKeys = shelfStore.loadRead(entry.id)
        shelfBooks = shelfStore.list()
        showShelf = false
        noteArticleProgress()
    }

    private fun retitleBook(entry: ShelfEntry) {
        val joined = shelfStore.loadChunks(entry.id).joinToString("\n\n")
        val pages = BookChapters.retitle(joined)
        if (pages == null) {
            importError = "没有找到章节"
            return
        }
        shelfStore.replace(entry.id, pages.map { it.text }, pages.map { it.title }) ?: return
        shelfBooks = shelfStore.list()
        if (bookId == entry.id) {
            chunks = pages.map { it.text }
            chunkTitles = pages.map { it.title }
            chunkIndex = 0
            noteArticleProgress()
        }
    }

    private fun deleteBook(entry: ShelfEntry) {
        chapterJump.reset()
        shelfStore.delete(entry.id)
        if (bookId == entry.id) {
            bookId = null
            chunks = emptyList()
            chunkTitles = emptyList()
            chunkIndex = 0
            readKeys = emptySet()
            showShelf = true
            resetAnalysis()
        }
        shelfBooks = shelfStore.list()
    }

    private fun saveGlossModel(slug: String) {
        getSharedPreferences(GlossModelStore.PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(GlossModelStore.KEY, slug)
            .apply()
    }

    private fun displayName(uri: Uri): String? {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return null
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index < 0) return null
            return cursor.getString(index)
        }
        return null
    }

    private fun copyAsset(name: String): File {
        val out = File(filesDir, name)
        val assetLen = assets.openFd(name).use { it.length }
        if (out.exists() && out.length() == assetLen && assetLen > 0L) return out
        assets.open(name).use { input ->
            out.outputStream().use { input.copyTo(it) }
        }
        return out
    }

    private fun probeGlm(rawKey: String): String {
        return try {
            val apiKey = GlmKey.require(rawKey)
            val parts = StringBuilder()
            HttpGlmTransport().post(
                apiKey,
                GlmProtocol.body("You are a helpful assistant.", "Say hello in one sentence."),
            ) { parts.append(it) }
            parts.toString().ifBlank { GlmErrors.EMPTY }
        } catch (e: GlmConfigException) {
            e.message ?: GlmKey.MISSING
        } catch (e: GlmHttpException) {
            e.message ?: GlmErrors.FAILED
        } catch (e: Exception) {
            Log.w("Glm", "request failed: ${e.javaClass.simpleName}")
            GlmErrors.FAILED
        }
    }

    private fun probeMimo(rawKey: String): String {
        return try {
            val apiKey = MimoKey.require(rawKey)
            val conn = java.net.URL(MimoProtocol.ENDPOINT).openConnection() as java.net.HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 20000
            conn.readTimeout = 20000
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(MimoProtocol.body().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val raw = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) MimoProtocol.FAILED else MimoProtocol.replyText(raw)
        } catch (e: MimoConfigException) {
            e.message ?: MimoKey.MISSING
        } catch (e: Exception) {
            Log.w("MiMo", "request failed: ${e.javaClass.simpleName}")
            MimoProtocol.FAILED
        }
    }
}
