package com.jarvis.ir.explain

object ModelOpenFailure {
    fun message(nativeError: String, engineMessage: String?): String {
        val detail = nativeError.trim().ifBlank { engineMessage?.trim().orEmpty() }
        val head = "模型打不开。文件还在，不用重新下载。"
        return if (detail.isBlank()) head else "$head\n$detail"
    }
}
