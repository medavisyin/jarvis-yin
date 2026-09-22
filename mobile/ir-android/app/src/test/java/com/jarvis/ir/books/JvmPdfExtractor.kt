package com.jarvis.ir.books

import org.apache.pdfbox.pdmodel.PDDocument
import org.apache.pdfbox.text.PDFTextStripper
import java.io.InputStream

object JvmPdfExtractor {
    fun extract(input: InputStream): String {
        PDDocument.load(input).use { doc ->
            return PDFTextStripper().getText(doc)
        }
    }
}
