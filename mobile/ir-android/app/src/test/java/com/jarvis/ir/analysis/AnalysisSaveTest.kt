package com.jarvis.ir.analysis

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisSaveTest {
    @Test
    fun onlyAFinishedAnalysisIsSaved() {
        assertTrue(AnalysisSave.shouldPersist(completed = true, error = "", text = "words"))
        assertFalse(AnalysisSave.shouldPersist(completed = false, error = "", text = "partial"))
        assertFalse(AnalysisSave.shouldPersist(completed = true, error = "failed", text = "partial"))
        assertFalse(AnalysisSave.shouldPersist(completed = true, error = "", text = "  "))
    }
}
