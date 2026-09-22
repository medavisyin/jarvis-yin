package com.jarvis.ir.dict

import java.io.File
import java.sql.Connection
import java.sql.DriverManager

class JdbcStarDict(file: File) : AutoCloseable {
    private val conn: Connection = DriverManager.getConnection("jdbc:sqlite:${file.absolutePath}")

    fun lookupExact(word: String): DictRow? {
        conn.prepareStatement(StarDictSql.LOOKUP).use { stmt ->
            stmt.setString(1, word)
            stmt.executeQuery().use { rs ->
                if (!rs.next()) return null
                return DictRow(
                    word = rs.getString("word"),
                    pos = rs.getString("pos"),
                    translation = rs.getString("translation") ?: "",
                )
            }
        }
    }

    override fun close() {
        conn.close()
    }
}
