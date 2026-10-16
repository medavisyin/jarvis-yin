package com.jarvis.ir.analysis

object AnalysisRestore {
    fun screen(
        startedBook: String?,
        startedPage: Int,
        startedKind: String,
        currentBook: String?,
        currentPage: Int,
        currentKind: String?,
        saved: String,
    ): AnalysisView.State? {
        if (startedBook == null || startedBook != currentBook) return null
        if (startedPage != currentPage || startedKind != currentKind) return null
        return AnalysisView.show(startedKind, saved)
    }
}
