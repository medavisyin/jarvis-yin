package com.jarvis.ir.mimo

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class MimoKeyTest {
    @Test
    fun maskHidesTheMiddle() {
        assertEquals("sk-1****abcd", MimoKey.mask("sk-1234567890abcd"))
        assertEquals("", MimoKey.mask(""))
        assertEquals("****", MimoKey.mask("short"))
    }

    @Test
    fun requireRejectsBlank() {
        val error = assertThrows(MimoConfigException::class.java) {
            MimoKey.require("  ")
        }
        assertEquals("还没有 MiMo 密钥", error.message)
    }
}
