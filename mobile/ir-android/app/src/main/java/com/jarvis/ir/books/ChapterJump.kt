package com.jarvis.ir.books

class ChapterJump {
    var target: Int? = null
        private set

    fun request(index: Int) {
        target = index
    }

    suspend fun consume(scroll: suspend (Int) -> Unit) {
        val page = target ?: return
        try {
            scroll(page)
        } finally {
            if (target == page) target = null
        }
    }

    fun reset() {
        target = null
    }
}
