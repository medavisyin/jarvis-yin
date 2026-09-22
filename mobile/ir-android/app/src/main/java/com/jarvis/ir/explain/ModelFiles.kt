package com.jarvis.ir.explain

import java.io.File

object ModelFiles {
    @Volatile
    var filesDir: File? = null

    fun folder(slug: String): File {
        val root = filesDir ?: error("应用目录还没准备好")
        return File(File(root, "models"), slug)
    }
}
