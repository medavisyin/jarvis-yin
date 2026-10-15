package com.jarvis.ir.analysis

object AnalysisSave {
    fun shouldPersist(completed: Boolean, error: String, text: String): Boolean =
        completed && error.isEmpty() && text.isNotBlank()
}
