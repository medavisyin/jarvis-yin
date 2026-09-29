package com.jarvis.ir.glm

import android.util.Log
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets

class GlmHttpException(message: String) : IllegalStateException(message)

class HttpGlmTransport : GlmTransport {
    @Volatile
    var cancelled: Boolean = false

    private var connection: HttpURLConnection? = null

    fun cancel() {
        cancelled = true
        connection?.disconnect()
    }

    override fun post(apiKey: String, jsonBody: String, emit: (String) -> Unit) {
        val url = URL(GlmProtocol.ENDPOINT)
        val conn = (url.openConnection() as HttpURLConnection).also { connection = it }
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 30_000
            conn.readTimeout = 120_000
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "text/event-stream")
            conn.outputStream.use { out ->
                out.write(jsonBody.toByteArray(StandardCharsets.UTF_8))
            }
            val status = conn.responseCode
            if (status !in 200..299) {
                throw GlmHttpException(GlmErrors.forStatus(status))
            }
            val collected = StringBuilder()
            BufferedReader(InputStreamReader(conn.inputStream, StandardCharsets.UTF_8)).use { reader ->
                while (!cancelled) {
                    val line = reader.readLine() ?: break
                    val pieces = GlmProtocol.deltas(listOf(line))
                    for (piece in pieces) {
                        collected.append(piece)
                        emit(piece)
                    }
                }
            }
            if (!cancelled && collected.isEmpty()) throw GlmHttpException(GlmErrors.EMPTY)
        } catch (e: GlmHttpException) {
            throw e
        } catch (e: Exception) {
            if (cancelled) return
            Log.w("Glm", "request failed: ${e.javaClass.simpleName}")
            throw GlmHttpException(GlmErrors.FAILED)
        } finally {
            conn.disconnect()
            connection = null
        }
    }
}
