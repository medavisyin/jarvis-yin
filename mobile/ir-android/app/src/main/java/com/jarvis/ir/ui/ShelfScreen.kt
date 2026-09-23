package com.jarvis.ir.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.ir.books.ShelfEntry

@Composable
fun ShelfScreen(
    books: List<ShelfEntry>,
    onOpen: (ShelfEntry) -> Unit,
    onDelete: (ShelfEntry) -> Unit,
    onSample: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    var pendingDelete by remember { mutableStateOf<ShelfEntry?>(null) }
    if (books.isEmpty()) {
        Column(modifier.fillMaxSize().padding(28.dp)) {
            Text("还没有书。打开设置，导入本地文件。", color = readingInk, fontSize = 18.sp)
            if (onSample != null) {
                Text(
                    "阅读样例",
                    color = readingInk,
                    fontSize = 18.sp,
                    modifier = Modifier.padding(top = 24.dp).clickable(onClick = onSample),
                )
            }
        }
        return
    }
    LazyColumn(modifier.fillMaxSize()) {
        items(books, key = { it.id }) { book ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(
                    Modifier
                        .weight(1f)
                        .clickable { onOpen(book) }
                        .padding(vertical = 8.dp, horizontal = 8.dp),
                ) {
                    Text(
                        book.title,
                        color = readingInk,
                        fontSize = 20.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    val page = book.chunkIndex + 1
                    Text(
                        "上次读到 $page/${book.chunkCount}",
                        color = readingInk.copy(alpha = 0.7f),
                        fontSize = 14.sp,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                TextButton(onClick = { pendingDelete = book }) { Text("删除") }
            }
        }
    }
    val pending = pendingDelete
    if (pending != null) {
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("删除这本书？") },
            confirmButton = {
                TextButton(onClick = {
                    pendingDelete = null
                    onDelete(pending)
                }) { Text("删除") }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text("取消") }
            },
        )
    }
}
