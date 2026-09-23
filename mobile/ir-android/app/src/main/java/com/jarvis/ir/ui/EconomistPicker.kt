package com.jarvis.ir.ui

import android.os.Handler
import android.os.Looper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.ir.books.EconomistFile
import com.jarvis.ir.books.EconomistImport
import com.jarvis.ir.books.EconomistIssue
import com.jarvis.ir.books.EconomistMessages
import com.jarvis.ir.books.EconomistSource
import java.io.File
import kotlin.coroutines.cancellation.CancellationException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

private sealed class EconomistAction {
    data class LoadIssues(val nonce: Int) : EconomistAction()
    data class LoadFiles(val issue: EconomistIssue, val nonce: Int) : EconomistAction()
    data class Download(val file: EconomistFile, val nonce: Int) : EconomistAction()
    data object Idle : EconomistAction()
}

private sealed class EconomistPhase {
    data class Busy(val label: String) : EconomistPhase()
    data class Issues(val items: List<EconomistIssue>) : EconomistPhase()
    data class Files(val issue: EconomistIssue, val items: List<EconomistIssue>, val files: List<EconomistFile>) : EconomistPhase()
    data class Failed(val message: String, val retry: EconomistAction) : EconomistPhase()
}

@Composable
fun EconomistPicker(
    cacheDir: File,
    onDismiss: () -> Unit,
    onImported: (title: String, kind: String, chunks: List<String>, titles: List<String>) -> Unit,
) {
    var action by remember { mutableStateOf<EconomistAction>(EconomistAction.LoadIssues(0)) }
    var phase by remember { mutableStateOf<EconomistPhase>(EconomistPhase.Busy("正在读取期次")) }
    var savedIssues by remember { mutableStateOf<List<EconomistIssue>>(emptyList()) }
    var nonce by remember { mutableIntStateOf(0) }
    val main = remember { Handler(Looper.getMainLooper()) }

    LaunchedEffect(action) {
        val attempt = EconomistSource.Attempt()
        try {
            when (val current = action) {
                EconomistAction.Idle -> Unit
                is EconomistAction.LoadIssues -> {
                    phase = EconomistPhase.Busy("正在读取期次")
                    val loaded = withContext(Dispatchers.IO) {
                        cancellable(attempt) { EconomistSource.listIssues(attempt) }
                    }
                    if (!isActive) return@LaunchedEffect
                    savedIssues = loaded
                    phase = EconomistPhase.Issues(loaded)
                }
                is EconomistAction.LoadFiles -> {
                    phase = EconomistPhase.Busy("正在读取文件")
                    val files = withContext(Dispatchers.IO) {
                        cancellable(attempt) { EconomistSource.listBooks(attempt, current.issue.path) }
                    }
                    if (!isActive) return@LaunchedEffect
                    phase = EconomistPhase.Files(current.issue, savedIssues, files)
                }
                is EconomistAction.Download -> {
                    phase = EconomistPhase.Busy("正在下载 0%")
                    val tmp = File(cacheDir, "economist-import-${System.nanoTime()}.bin")
                    try {
                        val book = withContext(Dispatchers.IO) {
                            val scope = this
                            cancellable(attempt) {
                                EconomistSource.download(
                                    attempt,
                                    current.file.downloadUrl,
                                    tmp,
                                    onStatus = { label ->
                                        main.post {
                                            if (scope.isActive) phase = EconomistPhase.Busy(label)
                                        }
                                    },
                                    keepGoing = { scope.isActive },
                                )
                                tmp.inputStream().use { input ->
                                    if (current.file.kind == "pdf") {
                                        EconomistImport.readPdf(input)
                                    } else {
                                        EconomistImport.readEpub(input)
                                    }
                                }
                            }
                        }
                        if (!isActive) return@LaunchedEffect
                        onImported(current.file.name, current.file.kind, book.chunks, book.titles)
                    } finally {
                        tmp.delete()
                    }
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (!isActive) return@LaunchedEffect
            phase = EconomistPhase.Failed(economistMessage(e), action)
        } finally {
            attempt.cancel()
        }
    }

    val shown = phase
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
        dismissButton = {
            when (shown) {
                is EconomistPhase.Files -> TextButton(onClick = {
                    action = EconomistAction.Idle
                    phase = EconomistPhase.Issues(shown.items)
                }) { Text("返回") }
                is EconomistPhase.Failed -> TextButton(onClick = {
                    nonce += 1
                    action = retry(shown.retry, nonce)
                }) { Text("重试") }
                else -> Unit
            }
        },
        title = { Text("经济学人") },
        text = {
            Column(
                Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                when (shown) {
                    is EconomistPhase.Busy -> Text(shown.label, color = readingInk)
                    is EconomistPhase.Failed -> Text(shown.message, color = readingInk)
                    is EconomistPhase.Issues -> {
                        shown.items.forEach { issue ->
                            TextButton(
                                onClick = {
                                    nonce += 1
                                    action = EconomistAction.LoadFiles(issue, nonce)
                                },
                                modifier = Modifier.fillMaxWidth(),
                            ) { Text(issue.name) }
                        }
                    }
                    is EconomistPhase.Files -> {
                        Text(shown.issue.name, color = readingInk)
                        shown.files.forEach { file ->
                            TextButton(
                                onClick = {
                                    nonce += 1
                                    action = EconomistAction.Download(file, nonce)
                                },
                                modifier = Modifier.fillMaxWidth(),
                            ) { Text(if (file.kind == "pdf") "PDF" else "EPUB") }
                        }
                    }
                }
            }
        },
    )
}

private suspend fun <T> cancellable(attempt: EconomistSource.Attempt, block: () -> T): T {
    return suspendCancellableCoroutine { cont ->
        cont.invokeOnCancellation { attempt.cancel() }
        try {
            val value = block()
            if (cont.isActive) cont.resume(value)
        } catch (e: Throwable) {
            if (cont.isActive) cont.resumeWithException(e)
        }
    }
}

private fun retry(action: EconomistAction, nonce: Int): EconomistAction = when (action) {
    is EconomistAction.LoadIssues -> EconomistAction.LoadIssues(nonce)
    is EconomistAction.LoadFiles -> EconomistAction.LoadFiles(action.issue, nonce)
    is EconomistAction.Download -> EconomistAction.Download(action.file, nonce)
    EconomistAction.Idle -> EconomistAction.LoadIssues(nonce)
}

private fun economistMessage(error: Throwable): String {
    val known = setOf(
        EconomistMessages.PARSE,
        EconomistMessages.OFFLINE,
        EconomistMessages.EMPTY_ISSUES,
        EconomistMessages.EMPTY_FILES,
        EconomistMessages.DOWNLOAD,
        EconomistMessages.IMPORT,
        EconomistMessages.http(403),
        EconomistMessages.http(404),
    )
    val message = error.message
    if (message != null && (message in known || message.startsWith("GitHub 返回 "))) return message
    return EconomistMessages.IMPORT
}
