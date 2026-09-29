package com.jarvis.ir.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun AnalysisPane(
    text: String,
    error: String,
    running: Boolean,
    onRun: (String) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .background(readingPaper)
            .padding(12.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onRun("vocab") }) { Text("好词好句") }
            Button(onClick = { onRun("culture") }) { Text("社会文化") }
        }
        if (running) {
            TextButton(onClick = onCancel) { Text("取消") }
        }
        if (error.isNotEmpty()) {
            Text(error, color = readingInk, fontSize = 14.sp, modifier = Modifier.padding(top = 8.dp))
        }
        Column(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(top = 8.dp),
        ) {
            Text(
                text.ifBlank { if (running) "分析中…" else "选一个分析" },
                color = readingInk,
                fontSize = 15.sp,
            )
        }
    }
}
