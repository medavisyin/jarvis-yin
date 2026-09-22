package com.jarvis.ir.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.jarvis.ir.explain.ExplainCard
import com.jarvis.ir.explain.ExplainStatus

@Composable
fun ExplainCardView(
    card: ExplainCard,
    modifier: Modifier = Modifier,
    glossLine: String? = null,
    glossLabel: String? = null,
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            when (card.status) {
                ExplainStatus.NOT_IN_DICT -> {
                    Text(card.word, style = MaterialTheme.typography.titleMedium)
                    if (!glossLine.isNullOrBlank()) {
                        Text(labeledGloss(glossLabel, glossLine), modifier = Modifier.padding(top = 12.dp))
                    }
                }
                ExplainStatus.REFUSED -> Text("这次没法确定")
                ExplainStatus.OK -> {
                    Text(card.word, style = MaterialTheme.typography.titleMedium)
                    if (card.uncertain) {
                        Text("不确定", color = MaterialTheme.colorScheme.error)
                    }
                    if (!card.pos.isNullOrBlank()) {
                        Text(card.pos, style = MaterialTheme.typography.labelMedium)
                    }
                    Text(card.translation)
                    Text(card.example, style = MaterialTheme.typography.bodySmall)
                    if (!glossLine.isNullOrBlank()) {
                        Text(labeledGloss(glossLabel, glossLine), modifier = Modifier.padding(top = 12.dp))
                    }
                }
            }
        }
    }
}

private fun labeledGloss(label: String?, line: String): String =
    if (label.isNullOrBlank()) line else "$label：$line"
