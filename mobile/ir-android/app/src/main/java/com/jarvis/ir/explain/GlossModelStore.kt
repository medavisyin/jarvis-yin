package com.jarvis.ir.explain

object GlossModelStore {
    const val PREFS = "ir"
    const val KEY = "gloss_model"

    fun normalize(saved: String?): String =
        if (saved != null && saved in GlossSession.choices) saved else GlossSession.MODEL_06
}
