package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.HttpURLConnection
import java.net.URL

class EconomistSourceTest {
    @Test
    fun cancellingOneAttemptLeavesTheOtherConnection() {
        val older = EconomistSource.Attempt()
        val newer = EconomistSource.Attempt()
        val olderConn = FakeConn()
        val newerConn = FakeConn()
        older.attach(olderConn)
        newer.attach(newerConn)
        older.cancel()
        assertTrue(olderConn.disconnected)
        assertTrue(!newerConn.disconnected)
        assertNull(older.current())
    }

    @Test
    fun attachAfterCancelDisconnectsImmediately() {
        val attempt = EconomistSource.Attempt()
        attempt.cancel()
        val conn = FakeConn()
        attempt.attach(conn)
        assertTrue(conn.disconnected)
    }

    @Test
    fun foreignDownloadHostIsRejected() {
        val error = runCatching { EconomistSource.requireHost("https://evil.example/book.epub") }.exceptionOrNull()
        assertEquals(EconomistMessages.DOWNLOAD, error?.message)
    }

    @Test
    fun plainHttpIsRejected() {
        val error = runCatching { EconomistSource.requireHost("http://api.github.com/repos/x") }.exceptionOrNull()
        assertEquals(EconomistMessages.DOWNLOAD, error?.message)
    }

    @Test
    fun githubHostsAreAllowed() {
        EconomistSource.requireHost("https://api.github.com/repos/x")
        EconomistSource.requireHost("https://raw.githubusercontent.com/hehonghui/awesome-english-ebooks/master/a.epub")
        EconomistSource.requireHost("https://objects.githubusercontent.com/github-production-repository-file/a")
    }

    private class FakeConn : HttpURLConnection(URL("https://api.github.com/")) {
        var disconnected = false
        override fun disconnect() {
            disconnected = true
        }
        override fun connect() = Unit
        override fun usingProxy() = false
    }
}
