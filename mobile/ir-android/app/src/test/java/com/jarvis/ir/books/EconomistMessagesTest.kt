package com.jarvis.ir.books

import org.junit.Assert.assertEquals
import org.junit.Test

class EconomistMessagesTest {
    @Test
    fun mapsHttpStatusToTheApprovedLines() {
        assertEquals("GitHub 拒绝了请求，可能是访问次数过多", EconomistMessages.http(403))
        assertEquals("找不到这一期或这个文件", EconomistMessages.http(404))
        assertEquals("GitHub 返回 500", EconomistMessages.http(500))
    }
}
