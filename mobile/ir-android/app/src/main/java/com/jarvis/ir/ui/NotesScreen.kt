package com.jarvis.ir.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.jarvis.ir.notes.Note
import com.jarvis.ir.notes.NoteGroups

@Composable
fun NotesScreen(
    notes: List<Note>,
    onDelete: (String) -> Unit,
    onShare: (Note) -> Unit,
    modifier: Modifier = Modifier,
) {
    var openBook by remember { mutableStateOf<String?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }
    val books = NoteGroups.byBook(notes)
    LaunchedEffect(notes, openBook, openId) {
        if (openBook != null && books.none { it.title == openBook }) {
            openBook = null
            openId = null
        } else if (openId != null && notes.none { it.id == openId }) {
            openId = null
        }
    }
    if (notes.isEmpty()) {
        Text(
            "还没有笔记",
            color = readingInk.copy(alpha = 0.7f),
            fontFamily = FontFamily.Serif,
            fontSize = 18.sp,
            modifier = modifier.padding(28.dp),
        )
        return
    }
    LazyColumn(
        modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(books, key = { it.title }) { book ->
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .clickable {
                        openId = null
                        openBook = book.title
                    },
                shape = RoundedCornerShape(18.dp),
                color = readingPaper,
                shadowElevation = 2.dp,
            ) {
                Row(
                    Modifier.height(IntrinsicSize.Min).padding(end = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        Modifier
                            .width(4.dp)
                            .fillMaxHeight()
                            .background(readingInk.copy(alpha = 0.55f)),
                    )
                    Text(
                        book.title.ifBlank { "未命名" },
                        color = readingInk,
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Medium,
                        fontSize = 20.sp,
                        lineHeight = 28.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier
                            .weight(1f)
                            .padding(horizontal = 14.dp, vertical = 16.dp),
                    )
                    Text(
                        "${book.notes.size}",
                        color = readingInk,
                        fontSize = 13.sp,
                        modifier = Modifier
                            .clip(RoundedCornerShape(999.dp))
                            .background(readingInk.copy(alpha = 0.08f))
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                }
            }
        }
    }
    val shown = books.firstOrNull { it.title == openBook }
    if (shown != null) {
        Dialog(
            onDismissRequest = {
                openBook = null
                openId = null
            },
            properties = DialogProperties(usePlatformDefaultWidth = false),
        ) {
            Surface(
                modifier = Modifier
                    .padding(horizontal = 20.dp)
                    .fillMaxWidth(),
                shape = RoundedCornerShape(22.dp),
                color = readingPaper,
                shadowElevation = 8.dp,
            ) {
                Column(Modifier.padding(horizontal = 18.dp, vertical = 18.dp)) {
                    Text(
                        shown.title.ifBlank { "未命名" },
                        color = readingInk,
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Medium,
                        fontSize = 22.sp,
                        lineHeight = 30.sp,
                    )
                    Text(
                        "${shown.notes.size} 条",
                        color = readingInk.copy(alpha = 0.55f),
                        fontSize = 13.sp,
                        modifier = Modifier.padding(top = 4.dp, bottom = 14.dp),
                    )
                    LazyColumn(Modifier.heightIn(max = 520.dp)) {
                        items(shown.notes, key = { it.id }) { note ->
                            val open = openId == note.id
                            Column(
                                Modifier
                                    .padding(bottom = 8.dp)
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(16.dp))
                                    .background(
                                        if (open) readingInk.copy(alpha = 0.07f) else readingInk.copy(alpha = 0.04f),
                                    )
                                    .clickable { openId = if (open) null else note.id }
                                    .padding(horizontal = 14.dp, vertical = 12.dp),
                            ) {
                                Text(
                                    note.content,
                                    color = readingInk,
                                    fontFamily = FontFamily.Serif,
                                    fontSize = 17.sp,
                                    lineHeight = 26.sp,
                                    maxLines = if (open) Int.MAX_VALUE else 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                if (open && note.explanation.isNotBlank()) {
                                    Text(
                                        "解释",
                                        color = readingInk.copy(alpha = 0.45f),
                                        fontSize = 12.sp,
                                        modifier = Modifier.padding(top = 12.dp),
                                    )
                                    Text(
                                        note.explanation,
                                        color = readingInk.copy(alpha = 0.9f),
                                        fontSize = 15.sp,
                                        lineHeight = 24.sp,
                                        modifier = Modifier
                                            .padding(top = 6.dp)
                                            .fillMaxWidth()
                                            .clip(RoundedCornerShape(12.dp))
                                            .background(readingPaper)
                                            .padding(12.dp),
                                    )
                                }
                                if (open) {
                                    Row(
                                        Modifier.fillMaxWidth().padding(top = 4.dp),
                                        horizontalArrangement = Arrangement.End,
                                    ) {
                                        TextButton(onClick = { onShare(note) }) {
                                            Text("分享", color = readingInk)
                                        }
                                        TextButton(onClick = { onDelete(note.id) }) {
                                            Text("删除", color = readingInk.copy(alpha = 0.45f))
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
