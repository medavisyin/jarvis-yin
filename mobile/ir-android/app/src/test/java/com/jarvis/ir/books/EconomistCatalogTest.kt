package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EconomistCatalogTest {
    @Test
    fun latestIssuesKeepsThreeNewestTeDirectories() {
        val json = """
            [
              {"name":"2025","path":"01_economist/2025","type":"dir"},
              {"name":"fonts","path":"01_economist/fonts","type":"dir"},
              {"name":"README.md","path":"01_economist/README.md","type":"file"},
              {"name":"te_notes","path":"01_economist/te_notes","type":"file"},
              {"name":"te_2026.08.01","path":"01_economist/te_2026.08.01","type":"dir"},
              {"name":"te_2026.09.05","path":"01_economist/te_2026.09.05","type":"dir"},
              {"name":"te_2026.09.19","path":"01_economist/te_2026.09.19","type":"dir"},
              {"name":"te_2025.12.27","path":"01_economist/te_2025.12.27","type":"dir"}
            ]
        """.trimIndent()
        val issues = EconomistCatalog.latestIssues(json)
        assertEquals(
            listOf("te_2026.09.19", "te_2026.09.05", "te_2026.08.01"),
            issues.map { it.name },
        )
        assertEquals("01_economist/te_2026.09.19", issues[0].path)
    }

    @Test
    fun latestIssuesReturnsAllWhenFewerThanThree() {
        val json = """
            [
              {"name":"te_2026.09.19","path":"01_economist/te_2026.09.19","type":"dir"},
              {"name":"te_2026.09.05","path":"01_economist/te_2026.09.05","type":"dir"}
            ]
        """.trimIndent()
        assertEquals(
            listOf("te_2026.09.19", "te_2026.09.05"),
            EconomistCatalog.latestIssues(json).map { it.name },
        )
    }

    @Test
    fun booksKeepsEpubAndPdfOnly() {
        val json = """
            [
              {"name":"README.md","download_url":"https://example/README.md","type":"file"},
              {"name":"TheEconomist.2026.09.19.mobi","download_url":"https://example/a.mobi","type":"file"},
              {"name":"TheEconomist.2026.09.19.epub","download_url":"https://example/a.epub","type":"file"},
              {"name":"TheEconomist.2026.09.19.PDF","download_url":"https://example/a.pdf","type":"file"},
              {"name":"missing.epub","download_url":null,"type":"file"}
            ]
        """.trimIndent()
        val books = EconomistCatalog.books(json)
        assertEquals(listOf("epub", "pdf"), books.map { it.kind })
        assertEquals("https://example/a.epub", books[0].downloadUrl)
        assertTrue(books.none { it.name.endsWith(".mobi") })
    }

    @Test
    fun badJsonReportsParseFailure() {
        val error = runCatching { EconomistCatalog.latestIssues("{") }.exceptionOrNull()
        assertEquals("期次列表无法解析", error?.message)
    }

    @Test
    fun emptyIssueListUsesTheApprovedLine() {
        val error = runCatching { EconomistCatalog.requireIssues("[]") }.exceptionOrNull()
        assertEquals(EconomistMessages.EMPTY_ISSUES, error?.message)
    }

    @Test
    fun emptyBookListUsesTheApprovedLine() {
        val error = runCatching { EconomistCatalog.requireBooks("[]") }.exceptionOrNull()
        assertEquals(EconomistMessages.EMPTY_FILES, error?.message)
    }
}
