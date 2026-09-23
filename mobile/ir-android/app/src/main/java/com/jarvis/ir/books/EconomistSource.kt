package com.jarvis.ir.books

import com.jarvis.ir.explain.DownloadProgress
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import kotlin.coroutines.cancellation.CancellationException

object EconomistSource {
    private const val API =
        "https://api.github.com/repos/hehonghui/awesome-english-ebooks/contents/"
    private const val ISSUE_ROOT = "01_economist"
    private val allowedHosts = setOf(
        "api.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
    )

    class Attempt {
        private val marker = AtomicReference<Any?>(null)
        private val connection = AtomicReference<HttpURLConnection?>(null)
        private val cancelled = AtomicBoolean(false)

        fun bind(token: Any) {
            marker.set(token)
        }

        fun current(): Any? = marker.get()

        fun isCancelled(): Boolean = cancelled.get()

        fun cancel() {
            cancelled.set(true)
            marker.set(null)
            connection.getAndSet(null)?.disconnect()
        }

        internal fun attach(open: HttpURLConnection) {
            if (cancelled.get()) {
                open.disconnect()
                return
            }
            connection.set(open)
            if (cancelled.get() && connection.compareAndSet(open, null)) {
                open.disconnect()
            }
        }

        internal fun detach(open: HttpURLConnection) {
            connection.compareAndSet(open, null)
        }
    }

    fun requireHost(url: String) {
        val parsed = try {
            URL(url)
        } catch (e: Exception) {
            throw IllegalStateException(EconomistMessages.DOWNLOAD)
        }
        if (!parsed.protocol.equals("https", ignoreCase = true) || parsed.host.lowercase() !in allowedHosts) {
            throw IllegalStateException(EconomistMessages.DOWNLOAD)
        }
    }

    fun listIssues(attempt: Attempt): List<EconomistIssue> =
        EconomistCatalog.requireIssues(getText(API + ISSUE_ROOT, attempt, githubJson = true))

    fun listBooks(attempt: Attempt, path: String): List<EconomistFile> =
        EconomistCatalog.requireBooks(getText(API + path.trim('/'), attempt, githubJson = true))

    fun download(
        attempt: Attempt,
        url: String,
        dest: File,
        onStatus: (String) -> Unit,
        keepGoing: () -> Boolean = { true },
    ) {
        dest.parentFile?.mkdirs()
        val connection = open(url, githubJson = false, attempt)
        try {
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                throw IllegalStateException(EconomistMessages.http(connection.responseCode))
            }
            val total = connection.contentLengthLong
            var done = 0L
            var lastLabel = ""
            connection.inputStream.use { input ->
                dest.outputStream().use { output ->
                    val buffer = ByteArray(256 * 1024)
                    while (keepGoing()) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        output.write(buffer, 0, n)
                        done += n
                        val label = DownloadProgress.label(done, total)
                        if (label != lastLabel) {
                            lastLabel = label
                            onStatus(label)
                        }
                    }
                }
            }
            if (!keepGoing()) throw CancellationException()
        } catch (e: CancellationException) {
            dest.delete()
            throw e
        } catch (e: IllegalStateException) {
            dest.delete()
            throw e
        } catch (e: IOException) {
            dest.delete()
            if (attempt.isCancelled()) throw CancellationException()
            throw IllegalStateException(EconomistMessages.DOWNLOAD)
        } finally {
            attempt.detach(connection)
            connection.disconnect()
        }
    }

    private fun getText(url: String, attempt: Attempt, githubJson: Boolean): String {
        val connection = open(url, githubJson, attempt)
        try {
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                throw IllegalStateException(EconomistMessages.http(connection.responseCode))
            }
            return connection.inputStream.bufferedReader().use { it.readText() }
        } catch (e: IllegalStateException) {
            throw e
        } catch (e: IOException) {
            if (attempt.isCancelled()) throw CancellationException()
            throw IllegalStateException(EconomistMessages.OFFLINE)
        } finally {
            attempt.detach(connection)
            connection.disconnect()
        }
    }

    private fun open(url: String, githubJson: Boolean, attempt: Attempt): HttpURLConnection {
        var current = url
        repeat(5) {
            requireHost(current)
            val connection = (URL(current).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 30_000
                readTimeout = 120_000
                setRequestProperty("User-Agent", "Y")
                if (githubJson) {
                    setRequestProperty("Accept", "application/vnd.github+json")
                }
            }
            attempt.attach(connection)
            try {
                connection.connect()
            } catch (e: IOException) {
                attempt.detach(connection)
                connection.disconnect()
                if (attempt.isCancelled()) throw CancellationException()
                throw IllegalStateException(EconomistMessages.OFFLINE)
            }
            val code = connection.responseCode
            if (code == HttpURLConnection.HTTP_MOVED_PERM ||
                code == HttpURLConnection.HTTP_MOVED_TEMP ||
                code == HttpURLConnection.HTTP_SEE_OTHER ||
                code == 307 ||
                code == 308
            ) {
                val next = connection.getHeaderField("Location")
                attempt.detach(connection)
                connection.disconnect()
                if (next.isNullOrBlank()) throw IllegalStateException(EconomistMessages.DOWNLOAD)
                current = URL(URL(current), next).toString()
                return@repeat
            }
            return connection
        }
        throw IllegalStateException(EconomistMessages.DOWNLOAD)
    }
}
