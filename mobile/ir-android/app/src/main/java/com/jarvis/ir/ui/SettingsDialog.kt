package com.jarvis.ir.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.jarvis.ir.speak.PassageSpeak
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.jarvis.ir.analysis.AnalysisProvider

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SettingsDialog(
    onDismiss: () -> Unit,
    onOpenLocal: () -> Unit,
    onOpenEconomist: () -> Unit,
    glossSelected: String,
    glossStatus: String,
    glossBusy: Boolean,
    onSelectModel: (String) -> Unit,
    onDownload: () -> Unit,
    analysisProvider: String,
    onSelectAnalysisProvider: (String) -> Unit,
    glmMasked: String,
    glmStatus: String,
    glmBusy: Boolean,
    onSaveGlm: (String) -> Unit,
    onTestGlm: (String) -> Unit,
    mimoMasked: String,
    mimoStatus: String,
    mimoBusy: Boolean,
    onSaveMimo: (String) -> Unit,
    onTestMimo: (String) -> Unit,
    speakEngine: String,
    onSpeakEngine: (String) -> Unit,
    voiceEn: String,
    onVoiceEn: (String) -> Unit,
    voiceZh: String,
    onVoiceZh: (String) -> Unit,
    mimoStyle: String,
    onMimoStyle: (String) -> Unit,
) {
    var stylesOpen by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
        title = { Text("设置") },
        text = {
            var glmDraft by remember { mutableStateOf("") }
            var mimoDraft by remember { mutableStateOf("") }
            Column(Modifier.verticalScroll(rememberScrollState())) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(onClick = onOpenLocal) { Text("导入本地文件") }
                    Button(onClick = onOpenEconomist) { Text("经济学人") }
                }
                GlossDownloadBar(
                    selected = glossSelected,
                    status = glossStatus,
                    busy = glossBusy,
                    onSelect = onSelectModel,
                    onDownload = onDownload,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("阅读全文", modifier = Modifier.padding(top = 12.dp))
                listOf("browser" to "浏览器", "mimo" to "MiMo").forEach { (id, label) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = speakEngine == id, onClick = { onSpeakEngine(id) })
                        Text(label)
                    }
                }
                Text("Voice EN", modifier = Modifier.padding(top = 4.dp))
                listOf("female" to "女", "male" to "男").forEach { (id, label) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = voiceEn == id, onClick = { onVoiceEn(id) })
                        Text(label)
                    }
                }
                Text("Voice ZH")
                listOf("female" to "女", "male" to "男").forEach { (id, label) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = voiceZh == id, onClick = { onVoiceZh(id) })
                        Text(label)
                    }
                }
                if (speakEngine == "mimo") {
                    Text("Style", modifier = Modifier.padding(top = 4.dp))
                    TextButton(onClick = { stylesOpen = true }) { Text(mimoStyle) }
                }
                Text("分析模型", modifier = Modifier.padding(top = 12.dp))
                listOf(AnalysisProvider.GLM to "GLM", AnalysisProvider.MIMO to "MiMo").forEach { (id, label) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = analysisProvider == id,
                            onClick = { onSelectAnalysisProvider(id) },
                        )
                        Text(label)
                    }
                }
                Text(
                    if (glmMasked.isEmpty()) "GLM 密钥：未配置" else "GLM 密钥：$glmMasked",
                    modifier = Modifier.padding(top = 12.dp),
                )
                TextField(
                    value = glmDraft,
                    onValueChange = { glmDraft = it },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("GLM API key") },
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = {
                            onSaveGlm(glmDraft)
                            glmDraft = ""
                        },
                        enabled = glmDraft.isNotBlank() && !glmBusy,
                    ) { Text("保存") }
                    Button(
                        onClick = { onTestGlm(glmDraft) },
                        enabled = !glmBusy,
                    ) { Text("测试") }
                }
                if (glmStatus.isNotEmpty()) Text(glmStatus)
                Text(
                    if (mimoMasked.isEmpty()) "MiMo 密钥：未配置" else "MiMo 密钥：$mimoMasked",
                    modifier = Modifier.padding(top = 12.dp),
                )
                TextField(
                    value = mimoDraft,
                    onValueChange = { mimoDraft = it },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("MiMo API key") },
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Button(
                        onClick = {
                            onSaveMimo(mimoDraft)
                            mimoDraft = ""
                        },
                        enabled = mimoDraft.isNotBlank() && !mimoBusy,
                    ) { Text("保存") }
                    Button(
                        onClick = { onTestMimo(mimoDraft) },
                        enabled = !mimoBusy,
                    ) { Text("测试") }
                }
                if (mimoStatus.isNotEmpty()) Text(mimoStatus)
            }
        },
    )
    if (stylesOpen) {
        AlertDialog(
            onDismissRequest = { stylesOpen = false },
            confirmButton = {
                TextButton(onClick = { stylesOpen = false }) { Text("关闭") }
            },
            title = { Text("Style") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    PassageSpeak.STYLES.forEach { item ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(
                                selected = mimoStyle == item,
                                onClick = {
                                    onMimoStyle(item)
                                    stylesOpen = false
                                },
                            )
                            Text(item)
                        }
                    }
                }
            },
        )
    }
}
