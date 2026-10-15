package com.jarvis.ir.analysis

object AnalysisProvider {
    const val PREF_KEY = "analysis_provider"
    const val GLM = "glm"
    const val MIMO = "mimo"

    fun normalize(saved: String?): String = if (saved == MIMO) MIMO else GLM
}
