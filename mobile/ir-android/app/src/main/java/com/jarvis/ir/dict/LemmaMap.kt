package com.jarvis.ir.dict

class LemmaMap(private val inflectedToStem: Map<String, String>) {
    fun stem(word: String): String {
        val key = word.lowercase()
        return inflectedToStem[key] ?: key
    }

    companion object {
        fun load(text: String): LemmaMap {
            val map = HashMap<String, String>()
            text.lineSequence().forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isEmpty() || trimmed.startsWith(";")) return@forEach
                val parts = trimmed.split("->", limit = 2)
                if (parts.size != 2) return@forEach
                val stem = parts[0].substringBefore("/").trim().lowercase()
                if (stem.isEmpty()) return@forEach
                map[stem] = stem
                parts[1].split(',').map { it.trim().lowercase() }.filter { it.isNotEmpty() }
                    .forEach { form -> map[form] = stem }
            }
            return LemmaMap(map)
        }
    }
}
