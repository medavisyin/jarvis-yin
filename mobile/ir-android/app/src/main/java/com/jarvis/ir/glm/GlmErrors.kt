package com.jarvis.ir.glm

object GlmErrors {
    const val FAILED = "GLM 请求失败"
    const val BUSY = "GLM 请求过于频繁，请稍后再试"
    const val EMPTY = "没有返回内容"

    fun forStatus(status: Int): String = if (status == 429) BUSY else FAILED
}
