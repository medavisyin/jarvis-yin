package com.jarvis.ir.mimo

import com.jarvis.ir.speak.PassageSpeak
import java.net.HttpURLConnection
import java.net.URL

class MimoTtsException(message: String) : IllegalStateException(message)

object MimoTtsClient {
    const val FAILED = "MiMo 朗读失败"

    fun wav(apiKey: String, jsonBody: String): ByteArray {
        val conn = (URL("https://api.xiaomimimo.com/v1/chat/completions").openConnection() as HttpURLConnection)
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 30_000
            conn.readTimeout = 120_000
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $apiKey")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { out ->
                out.write(jsonBody.toByteArray(Charsets.UTF_8))
            }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val raw = stream?.use { it.readBytes() }?.toString(Charsets.UTF_8).orEmpty()
            if (status !in 200..299) throw MimoTtsException(FAILED)
            return PassageSpeak.wavBytes(raw)
        } catch (e: MimoTtsException) {
            throw e
        } catch (_: Exception) {
            throw MimoTtsException(FAILED)
        } finally {
            conn.disconnect()
        }
    }
}
