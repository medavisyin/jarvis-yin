package com.jarvis.ir.explain

import org.junit.Assert.assertEquals
import org.junit.Test

class GlossTextTest {
    @Test
    fun keepsPlainSentence() {
        assertEquals("河岸", GlossText.sentence("  河岸  "))
    }

    @Test
    fun dropsClosedThinkBlock() {
        assertEquals("河岸", GlossText.sentence("<think>\nbank\n</think>\n河岸"))
    }

    @Test
    fun dropsUnclosedThink() {
        assertEquals("", GlossText.sentence("<think>\n先分析 river"))
    }

    @Test
    fun dropsChineseCuePrefix() {
        assertEquals("河岸", GlossText.sentence("中文：河岸"))
    }

    @Test
    fun chineseDropsALeadingEnglishParaphrase() {
        assertEquals(
            "年轻的猫睁开了眼睛。",
            GlossText.chinese("the young cat's eyes widened. 年轻的猫睁开了眼睛。"),
        )
        assertEquals("", GlossText.chinese("the young cat's eyes widened as he scanned the thick underbrush."))
    }
}
