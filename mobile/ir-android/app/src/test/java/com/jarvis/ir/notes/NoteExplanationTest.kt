package com.jarvis.ir.notes

import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.explain.ExplainStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class NoteExplanationTest {
    @Test
    fun keepsDictionaryAndFinishedGloss() {
        val card = ExplainCard(
            status = ExplainStatus.OK,
            word = "bank",
            translation = "n. 银行\nn. 河岸",
        )
        val text = NoteExplanation.text(card, "这里是河岸", "词")
        assertEquals("n. 银行\nn. 河岸\n\n词：这里是河岸", text)
    }

    @Test
    fun skipsGlossThatIsStillLoading() {
        val card = ExplainCard(
            status = ExplainStatus.OK,
            word = "bank",
            translation = "n. 河岸",
        )
        assertEquals("n. 河岸", NoteExplanation.text(card, "正在写这个词…", "词"))
        assertEquals("", NoteExplanation.text(null, "正在翻译这句…", "句"))
    }
}
