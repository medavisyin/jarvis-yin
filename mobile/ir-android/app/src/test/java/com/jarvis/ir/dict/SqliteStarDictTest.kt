package com.jarvis.ir.dict

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

class SqliteStarDictTest {
    private val dbFile = File(
        javaClass.classLoader!!.getResource("ecdict-fixture.db")!!.toURI(),
    )

    @Test
    fun looksUpBankSenses() {
        JdbcStarDict(dbFile).use { db ->
            val row = db.lookupExact("bank")!!
            assertEquals("bank", row.word)
            val hit = DictionaryRepository(LemmaMap.load(""), db::lookupExact).lookup("bank")!!
            assertEquals(listOf("岸", "银行"), hit.senses.map { it.translation })
        }
    }

    @Test
    fun unknownIsNull() {
        JdbcStarDict(dbFile).use { db ->
            assertNull(db.lookupExact("xyzzy-not-a-word"))
        }
    }
}
