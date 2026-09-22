package com.jarvis.ir.explain

import org.junit.Assert.assertEquals
import org.junit.Test

class DownloadProgressTest {
    @Test
    fun showsPercentAndMegabytesWhenSizeIsKnown() {
        val text = DownloadProgress.label(done = 180L * 1024 * 1024, total = 360L * 1024 * 1024)
        assertEquals("正在下载 50% · 180/360MB", text)
    }

    @Test
    fun showsMegabytesOnlyWhenSizeIsUnknown() {
        val text = DownloadProgress.label(done = 12L * 1024 * 1024, total = -1)
        assertEquals("正在下载 12MB", text)
    }
}
