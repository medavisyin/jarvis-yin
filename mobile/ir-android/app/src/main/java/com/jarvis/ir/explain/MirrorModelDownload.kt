package com.jarvis.ir.explain

import java.io.BufferedInputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

object MirrorModelDownload {
    fun fetch(slug: String, url: String, onStatus: (String) -> Unit = {}) {
        val models = File(ModelFiles.filesDir ?: error("应用目录还没准备好"), "models")
        val folder = File(models, slug)
        if (folder.isDirectory && folder.listFiles()?.isNotEmpty() == true) return
        folder.deleteRecursively()
        models.mkdirs()
        val zip = File(models, "$slug.zip")
        try {
            val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 30_000
                readTimeout = 120_000
                setRequestProperty("User-Agent", "Y")
            }
            connection.connect()
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                throw IllegalStateException("镜像下载失败 ${connection.responseCode}")
            }
            val total = connection.contentLengthLong
            var done = 0L
            var lastLabel = ""
            connection.inputStream.use { input ->
                zip.outputStream().use { output ->
                    val buffer = ByteArray(256 * 1024)
                    while (true) {
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
            onStatus("正在解压…")
            folder.mkdirs()
            ZipInputStream(BufferedInputStream(zip.inputStream())).use { zipInput ->
                while (true) {
                    val entry = zipInput.nextEntry ?: break
                    val extracted = File(folder, entry.name)
                    if (!extracted.canonicalPath.startsWith(folder.canonicalPath + File.separator)) {
                        throw SecurityException("Zip path traversal")
                    }
                    if (entry.isDirectory) {
                        extracted.mkdirs()
                    } else {
                        extracted.parentFile?.mkdirs()
                        extracted.outputStream().use { zipInput.copyTo(it) }
                    }
                    zipInput.closeEntry()
                }
            }
            val contents = folder.listFiles()
            if (contents != null && contents.size == 1 && contents[0].isDirectory) {
                val nested = contents[0]
                nested.listFiles()?.forEach { file ->
                    file.renameTo(File(folder, file.name))
                }
                nested.delete()
            }
            if (folder.listFiles().isNullOrEmpty()) {
                throw IllegalStateException("镜像解压后是空的")
            }
        } catch (e: Exception) {
            zip.delete()
            folder.deleteRecursively()
            throw e
        } finally {
            zip.delete()
        }
    }
}
