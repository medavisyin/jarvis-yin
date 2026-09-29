package com.jarvis.ir.glm

fun interface GlmTransport {
    fun post(apiKey: String, jsonBody: String, emit: (String) -> Unit)
}

object StreamGate {
    fun isCurrent(active: Any?, source: Any?): Boolean = active === source
}

class GlmAnalysis(
    private val key: () -> String,
    private val transport: GlmTransport,
) {
    fun run(kind: String, title: String, chunkIndex: Int, passage: String, emit: (String) -> Unit) {
        val apiKey = GlmKey.require(key())
        val slice = PassageWindow.slice(passage)
        val body = GlmProtocol.body(
            AnalysisPrompts.system(kind),
            AnalysisPrompts.user(kind, title, chunkIndex, slice.text, slice.hasMore),
        )
        transport.post(apiKey, body, emit)
    }
}
