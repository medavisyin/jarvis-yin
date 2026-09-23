package com.jarvis.ir.books

import kotlin.coroutines.cancellation.CancellationException

data class LocalImportProbe(
    val name: String?,
    val kind: String?,
    val error: String?,
)

object LocalImport {
    fun probe(name: () -> String?, mime: () -> String?): LocalImportProbe {
        try {
            val found = name()
            val kind = FileKind.detect(found, mime())
            if (kind == null) return LocalImportProbe(found, null, LocalImportMessages.UNKNOWN)
            return LocalImportProbe(found, kind, null)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return LocalImportProbe(null, null, EconomistMessages.IMPORT)
        }
    }
}
