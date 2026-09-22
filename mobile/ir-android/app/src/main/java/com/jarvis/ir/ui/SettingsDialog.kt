package com.jarvis.ir.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingsDialog(
    onDismiss: () -> Unit,
    onOpenTxt: () -> Unit,
    onOpenEpub: () -> Unit,
    onOpenPdf: () -> Unit,
    glossSelected: String,
    glossStatus: String,
    glossBusy: Boolean,
    onSelectModel: (String) -> Unit,
    onDownload: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
        title = { Text("设置") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(onClick = onOpenTxt) { Text("打开 TXT") }
                    Button(onClick = onOpenEpub) { Text("打开 EPUB") }
                    Button(onClick = onOpenPdf) { Text("打开 PDF") }
                }
                GlossDownloadBar(
                    selected = glossSelected,
                    status = glossStatus,
                    busy = glossBusy,
                    onSelect = onSelectModel,
                    onDownload = onDownload,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
    )
}
