package com.jarvis.ir.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun PassageSpeakBar(
    speaking: Boolean,
    canResume: Boolean,
    error: String,
    onToggle: () -> Unit,
) {
    Column(Modifier.padding(start = 12.dp, top = 4.dp)) {
        TextButton(onClick = onToggle) {
            Text(if (speaking) "停止" else if (canResume) "继续" else "阅读全文")
        }
        if (error.isNotEmpty()) {
            Text(error, color = readingInk, fontSize = 12.sp, modifier = Modifier.padding(start = 12.dp))
        }
    }
}
