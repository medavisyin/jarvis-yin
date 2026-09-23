package com.jarvis.ir.books

import java.io.InputStream
import kotlin.coroutines.cancellation.CancellationException

data class ImportedBook(val chunks: List<String>, val titles: List<String>)

object EconomistImport {
    fun readEpub(input: InputStream): ImportedBook = importing {
        readyBook(MagazineChunker.fromSections(EpubImporter.extractSections(input)))
    }

    fun readPdf(input: InputStream): ImportedBook = importing {
        readyBook(MagazineChunker.fromPages(PdfImporter.extractPages(input)))
    }

    fun readPages(pages: List<String>): ImportedBook = importing {
        readyBook(MagazineChunker.fromPages(pages))
    }

    fun chunksFromEpub(input: InputStream): List<String> = readEpub(input).chunks

    fun chunksFromPdf(input: InputStream): List<String> = readPdf(input).chunks

    fun chunksFromPages(pages: List<String>): List<String> = readPages(pages).chunks

    private fun readyBook(chunks: List<MagazineChunk>): ImportedBook {
        val chosen = MagazineChunker.selected(chunks)
        val texts = MagazineChunker.passages(chosen)
        if (texts.isEmpty()) throw IllegalStateException(EconomistMessages.IMPORT)
        return ImportedBook(texts, chosen.map { it.title.trim() })
    }

    internal fun runImport(block: () -> List<String>): List<String> = importing(block)

    private fun <T> importing(block: () -> T): T {
        try {
            return block()
        } catch (e: CancellationException) {
            throw e
        } catch (e: IllegalStateException) {
            if (e.message == EconomistMessages.IMPORT) throw e
            throw IllegalStateException(EconomistMessages.IMPORT, e)
        } catch (e: Exception) {
            throw IllegalStateException(EconomistMessages.IMPORT, e)
        }
    }
}
