package com.jarvis.ir.dict

object StarDictSql {
    const val LOOKUP =
        "SELECT word, pos, translation FROM stardict WHERE word = ? COLLATE NOCASE LIMIT 1"
}
