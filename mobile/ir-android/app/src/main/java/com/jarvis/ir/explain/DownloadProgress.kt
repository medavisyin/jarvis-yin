package com.jarvis.ir.explain

object DownloadProgress {
    fun label(done: Long, total: Long): String {
        val doneMb = done / (1024 * 1024)
        if (total <= 0) return "正在下载 ${doneMb}MB"
        val totalMb = total / (1024 * 1024)
        val pct = ((done * 100) / total).toInt().coerceIn(0, 100)
        return "正在下载 $pct% · $doneMb/${totalMb}MB"
    }
}
