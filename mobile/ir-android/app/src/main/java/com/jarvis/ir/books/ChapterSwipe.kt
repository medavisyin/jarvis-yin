package com.jarvis.ir.books

import kotlin.math.abs

object ChapterSwipe {
    fun delta(dx: Float, dy: Float, minDistance: Float): Int? {
        if (minDistance <= 0f) return null
        if (abs(dx) < minDistance) return null
        if (abs(dx) < abs(dy) * 1.2f) return null
        return if (dx < 0f) 1 else -1
    }
}
