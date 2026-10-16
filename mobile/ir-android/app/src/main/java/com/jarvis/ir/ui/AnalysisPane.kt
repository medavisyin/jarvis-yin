package com.jarvis.ir.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.ir.analysis.AnalysisShare
import com.jarvis.ir.analysis.AnalysisView

@Composable
fun AnalysisPane(
    text: String,
    error: String,
    running: Boolean,
    bookTitle: String,
    selectedKind: String,
    onSelect: (String) -> Unit,
    onGenerate: () -> Unit,
    onCancel: () -> Unit,
    onShare: (String) -> Unit,
    onNote: (String) -> Unit,
    onRewrite: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .background(readingPaper)
            .padding(12.dp),
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            KindToggle(selectedKind = selectedKind, onSelect = onSelect)
            if (!running) {
                val saved = onRewrite != null
                Button(onClick = { if (saved) onRewrite?.invoke() else onGenerate() }) {
                    Text(AnalysisView.action(saved))
                }
            }
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
            if (text.isBlank()) {
                Text(
                    if (running) "分析中…" else emptyHint(selectedKind),
                    color = readingInk,
                    fontSize = 15.sp,
                )
            } else {
                val shareable = AnalysisShare.paragraphs(text, includeTail = !running)
                val tail = if (running) AnalysisShare.openTail(text) else ""
                shareable.forEach { paragraph ->
                    Text(paragraph, color = readingInk, fontSize = 15.sp)
                    Row {
                        TextButton(onClick = { onShare(AnalysisShare.body(bookTitle, paragraph)) }) {
                            Text("分享")
                        }
                        TextButton(onClick = { onNote(paragraph) }) {
                            Text("笔记")
                        }
                    }
                }
                if (tail.isNotEmpty()) {
                    Text(tail, color = readingInk, fontSize = 15.sp)
                }
            }
        }
    }
}

@Composable
private fun KindToggle(selectedKind: String, onSelect: (String) -> Unit) {
    val shape = RoundedCornerShape(10.dp)
    Row(Modifier.clip(shape).border(1.dp, readingInk.copy(alpha = 0.2f), shape)) {
        listOf(
            AnalysisView.VOCAB to "好词好句",
            AnalysisView.CULTURE to "社会文化",
        ).forEach { (kind, label) ->
            val on = AnalysisView.bright(kind, selectedKind)
            Text(
                label,
                color = if (on) readingPaper else readingInk.copy(alpha = 0.4f),
                fontSize = 14.sp,
                modifier = Modifier
                    .background(if (on) readingInk else readingPaper)
                    .clickable { onSelect(kind) }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            )
        }
    }
}

private fun emptyHint(kind: String): String =
    if (kind == AnalysisView.CULTURE) "这一页还没有社会文化" else "这一页还没有好词好句"
