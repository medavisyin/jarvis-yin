package com.jarvis.ir.ui

fun showPageControls(showNotes: Boolean, showShelf: Boolean, hasChunks: Boolean): Boolean =
    !showNotes && !showShelf && hasChunks
