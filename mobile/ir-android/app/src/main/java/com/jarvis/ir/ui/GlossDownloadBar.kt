package com.jarvis.ir.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.ir.explain.GlossSession

@Composable
fun GlossDownloadBar(
    selected: String,
    status: String,
    busy: Boolean,
    onSelect: (String) -> Unit,
    onDownload: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
        GlossSession.choices.forEach { slug ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(
                    selected = selected == slug,
                    onClick = { onSelect(slug) },
                    enabled = !busy,
                )
                Text(
                    when (slug) {
                        GlossSession.MODEL_06 -> "qwen3-0.6 · 575MB"
                        GlossSession.MODEL_17 -> "qwen3-1.7 · 810MB"
                        else -> slug
                    },
                )
            }
        }
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(
                onClick = onDownload,
                enabled = !busy && status != GlossSession.DOWNLOADED,
            ) { Text(if (busy) "下载中" else "下载") }
            Text(status, Modifier.padding(start = 8.dp).weight(1f))
        }
    }
}
