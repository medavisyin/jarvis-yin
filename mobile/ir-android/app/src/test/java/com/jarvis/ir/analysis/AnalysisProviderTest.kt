package com.jarvis.ir.analysis

import org.junit.Assert.assertEquals
import org.junit.Test

class AnalysisProviderTest {
    @Test
    fun unknownOrMissingBecomesGlm() {
        assertEquals(AnalysisProvider.GLM, AnalysisProvider.normalize(null))
        assertEquals(AnalysisProvider.GLM, AnalysisProvider.normalize(""))
        assertEquals(AnalysisProvider.GLM, AnalysisProvider.normalize("qwen"))
        assertEquals("analysis_provider", AnalysisProvider.PREF_KEY)
    }

    @Test
    fun mimoStaysMimo() {
        assertEquals(AnalysisProvider.MIMO, AnalysisProvider.normalize("mimo"))
    }
}
