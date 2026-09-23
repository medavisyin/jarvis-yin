package com.jarvis.ir

import android.content.Context
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
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.jarvis.ir.books.BookOpen
import com.jarvis.ir.books.ChapterJump
import com.jarvis.ir.books.ChapterLabels
import com.jarvis.ir.books.EconomistMessages
import com.jarvis.ir.books.EpubImporter
import com.jarvis.ir.books.LocalImport
import com.jarvis.ir.books.LocalImportMessages
import com.jarvis.ir.books.PdfImporter
import com.jarvis.ir.books.ShelfEntry
import com.jarvis.ir.books.ShelfStore
import com.jarvis.ir.books.TxtImporter
import com.jarvis.ir.explain.ModelFiles
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.jarvis.ir.dict.DictionaryRepository
import com.jarvis.ir.dict.LemmaMap
import com.jarvis.ir.dict.SqliteDict
import com.jarvis.ir.explain.CactusGlossEngine
import com.jarvis.ir.explain.ExplainPipeline
import com.jarvis.ir.explain.GlossModelStore
import com.jarvis.ir.explain.GlossSession
import com.jarvis.ir.ui.EconomistPicker
import com.jarvis.ir.ui.ReaderScreen
import com.jarvis.ir.ui.SettingsDialog
import com.jarvis.ir.ui.ShelfScreen
import com.jarvis.ir.ui.readingInk
import com.jarvis.ir.ui.readingPaper
import java.io.File
import kotlinx.coroutines.launch

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
    private var bookTitle by mutableStateOf("样例")
    private var bookId by mutableStateOf<String?>(null)
    private var shelfBooks by mutableStateOf(listOf<ShelfEntry>())
    private lateinit var shelfStore: ShelfStore
    private var shelfReady = false
    private val gloss = GlossSession(CactusGlossEngine())
    private var glossModel by mutableStateOf(GlossSession.MODEL_06)
    private var glossStatus by mutableStateOf(GlossSession.NOT_DOWNLOADED)
    private var glossBusy by mutableStateOf(false)
    private var glossReady by mutableStateOf(false)

    private val openLocal = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        importLocal(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PDFBoxResourceLoader.init(applicationContext)
        ModelFiles.filesDir = filesDir
        val modelPrefs = getSharedPreferences(GlossModelStore.PREFS, Context.MODE_PRIVATE)
        glossModel = GlossModelStore.normalize(modelPrefs.getString(GlossModelStore.KEY, null))
        shelfStore = ShelfStore(File(filesDir, "shelf"))
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
                Column(Modifier.fillMaxSize().background(readingPaper)) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (!showShelf) {
                            TextButton(onClick = {
                                chapterJump.reset()
                                showShelf = true
                            }) { Text("书架") }
                        }
                        Text(
                            if (showShelf) "书架" else bookTitle,
                            color = readingInk,
                            fontSize = 18.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                        if (!showShelf && chunks.isNotEmpty()) {
                            Text(
                                "${chunkIndex + 1}/${chunks.size}",
                                color = readingInk,
                                fontSize = 14.sp,
                                modifier = Modifier.padding(end = 4.dp),
                            )
                            TextButton(onClick = { showChapters = true }) { Text("章节") }
                        }
                        TextButton(onClick = { showSettings = true }) { Text("设置") }
                    }
                    if (showShelf) {
                        ShelfScreen(
                            books = shelfBooks,
                            onOpen = { openEntry(it) },
                            onDelete = { deleteBook(it) },
                            onSample = if (shelfBooks.isEmpty()) {
                                { openSample() }
                            } else {
                                null
                            },
                            modifier = Modifier.weight(1f),
                        )
                    } else if (chunks.isNotEmpty()) {
                        Box(Modifier.weight(1f)) {
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
                                ReaderScreen(
                                    passage = chunks.getOrElse(page) { "" },
                                    pipeline = pipeline,
                                    gloss = gloss,
                                    glossModel = glossModel,
                                    glossReady = glossReady,
                                    onModelRejected = {
                                        glossReady = false
                                        glossStatus = GlossSession.NOT_DOWNLOADED
                                    },
                                    modifier = Modifier.fillMaxSize(),
                                )
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
                                    itemsIndexed(chunks) { index, _ ->
                                        Text(
                                            ChapterLabels.label(chunkTitles.getOrElse(index) { "" }, index),
                                            color = readingInk,
                                            fontSize = 16.sp,
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .clickable {
                                                    showChapters = false
                                                    chapterJump.request(index)
                                                    chapterJumpTick += 1
                                                }
                                                .padding(vertical = 12.dp),
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
        showShelf = false
    }

    private fun openEntry(entry: ShelfEntry) {
        chapterJump.reset()
        val loaded = shelfStore.loadChunks(entry.id)
        val error = BookOpen.errorIfEmpty(loaded)
        if (error != null) {
            importError = error
            return
        }
        chunks = loaded
        chunkTitles = shelfStore.loadTitles(entry.id)
        chunkIndex = entry.chunkIndex.coerceIn(0, loaded.lastIndex)
        bookId = entry.id
        bookTitle = entry.title
        shelfStore.updatePosition(entry.id, chunkIndex)
        shelfBooks = shelfStore.list()
        showShelf = false
    }

    private fun openSample() {
        chapterJump.reset()
        val sample = assets.open("sample.txt").bufferedReader().use { it.readText() }
        chunks = listOf(sample)
        chunkTitles = emptyList()
        chunkIndex = 0
        bookId = null
        bookTitle = "样例"
        showShelf = false
    }

    private fun moveChunk(index: Int) {
        chunkIndex = index.coerceIn(0, chunks.lastIndex.coerceAtLeast(0))
        bookId?.let {
            shelfStore.updatePosition(it, chunkIndex)
            shelfBooks = shelfStore.list()
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
                    "epub" -> EpubImporter.importEpub(input)
                    "pdf" -> PdfImporter.importPdf(input)
                    else -> TxtImporter.importUtf8(input.readBytes())
                }
            }
            if (imported.isNullOrEmpty()) {
                importError = EconomistMessages.IMPORT
                return
            }
            val title = probe.name ?: kind.uppercase()
            openSaved(shelfStore.save(title, kind, imported, titles = List(imported.size) { "" }))
            showSettings = false
        } catch (e: Exception) {
            Log.e("Y", "import failed", e)
            importError = EconomistMessages.IMPORT
        }
    }

    private fun openSaved(entry: ShelfEntry) {
        chapterJump.reset()
        chunks = shelfStore.loadChunks(entry.id)
        chunkTitles = shelfStore.loadTitles(entry.id)
        chunkIndex = 0
        bookId = entry.id
        bookTitle = entry.title
        shelfBooks = shelfStore.list()
        showShelf = false
    }

    private fun deleteBook(entry: ShelfEntry) {
        chapterJump.reset()
        shelfStore.delete(entry.id)
        if (bookId == entry.id) {
            bookId = null
            chunks = emptyList()
            chunkTitles = emptyList()
            chunkIndex = 0
            showShelf = true
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
}
