package com.jarvis.ir.books

object EconomistMessages {
    const val PARSE = "期次列表无法解析"
    const val OFFLINE = "连不上 GitHub"
    const val EMPTY_ISSUES = "没有找到最近的期次"
    const val EMPTY_FILES = "这一期没有 EPUB 或 PDF"
    const val DOWNLOAD = "下载失败"
    const val IMPORT = "这本书无法导入"

    fun http(code: Int): String = when (code) {
        403 -> "GitHub 拒绝了请求，可能是访问次数过多"
        404 -> "找不到这一期或这个文件"
        else -> "GitHub 返回 $code"
    }
}
