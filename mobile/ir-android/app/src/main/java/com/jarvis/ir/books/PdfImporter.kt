package com.jarvis.ir.books

import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.io.InputStream

object PdfImporter {
    fun extractText(input: InputStream): String {
        PDDocument.load(input).use { doc ->
            return PDFTextStripper().getText(doc).trim()
        }
    }

    fun extractPages(input: InputStream): List<String> {
        PDDocument.load(input).use { doc ->
            val stripper = PDFTextStripper()
            return (1..doc.numberOfPages).map { page ->
                stripper.startPage = page
                stripper.endPage = page
                stripper.getText(doc).trim()
            }
        }
    }

    fun importPdf(input: InputStream, maxWords: Int = 400): List<String> =
        Chunker.chunk(extractText(input), maxWords)
}
