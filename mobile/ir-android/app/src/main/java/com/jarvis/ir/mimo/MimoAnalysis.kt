package com.jarvis.ir.mimo

import com.jarvis.ir.glm.AnalysisPrompts
import com.jarvis.ir.glm.GlmTransport
import com.jarvis.ir.glm.PassageWindow

class MimoAnalysis(
    private val key: () -> String,
    private val transport: GlmTransport,
) {
    fun run(kind: String, title: String, chunkIndex: Int, passage: String, emit: (String) -> Unit) {
        val apiKey = MimoKey.require(key())
        val slice = PassageWindow.slice(passage)
        val body = MimoProtocol.analysisBody(
            AnalysisPrompts.system(kind),
            AnalysisPrompts.user(kind, title, chunkIndex, slice.text, slice.hasMore),
        )
        transport.post(apiKey, body, emit)
    }
}
