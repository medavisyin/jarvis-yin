package com.jarvis.ir.dict

import android.database.sqlite.SQLiteDatabase
import java.io.File

class SqliteDict(file: File) : AutoCloseable {
    private val db: SQLiteDatabase =
        SQLiteDatabase.openDatabase(file.absolutePath, null, SQLiteDatabase.OPEN_READONLY)

    fun lookupExact(word: String): DictRow? {
        db.rawQuery(StarDictSql.LOOKUP, arrayOf(word)).use { cursor ->
            if (!cursor.moveToFirst()) return null
            val wordIdx = cursor.getColumnIndexOrThrow("word")
            val posIdx = cursor.getColumnIndexOrThrow("pos")
            val translationIdx = cursor.getColumnIndexOrThrow("translation")
            return DictRow(
                word = cursor.getString(wordIdx),
                pos = cursor.getString(posIdx),
                translation = cursor.getString(translationIdx) ?: "",
            )
        }
    }

    override fun close() {
        db.close()
    }
}
