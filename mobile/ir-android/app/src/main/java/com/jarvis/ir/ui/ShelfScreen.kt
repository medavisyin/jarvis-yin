package com.jarvis.ir.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.ir.books.ShelfEntry

@Composable
fun ShelfScreen(
    books: List<ShelfEntry>,
    onOpen: (ShelfEntry) -> Unit,
    onSample: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    if (books.isEmpty()) {
        Column(modifier.fillMaxSize().padding(28.dp)) {
            Text("还没有书。打开设置，导入 TXT、EPUB 或 PDF。", color = readingInk, fontSize = 18.sp)
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
            Column(
                Modifier
                    .fillMaxWidth()
                    .clickable { onOpen(book) }
                    .padding(horizontal = 28.dp, vertical = 16.dp),
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
        }
    }
}
