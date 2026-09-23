# Memory: Mobile Economist Import

**Generated**: 2026-09-23 ~14:30 UTC+8
**Last updated**: 2026-09-23 ~20:20 UTC+8
**Project**: c:\jarvis
**Focus**: Android IR app — Economist import, plus local-file import, chapter jump, and shelf delete

---

## Goal & Scope (required)

Phone intensive reading (`mobile/ir-android`) imports the latest 3 Economist issues from GitHub and reads them with desktop magazine chunking. Next UI work on the same app: one settings button 「导入本地文件」 that detects txt/epub/pdf after the file is chosen; a chapter list while reading that jumps to a chunk; delete a book from the shelf. 「经济学人」 stays. Desktop reading stays unchanged.

---

## Key Decisions (required)

1. **Loaded unrelated memory then left it**: User first selected `memory-20260920-deeptutor-comparison.md`. That topic stays closed (living book was removed). This task is a new memory file.
2. **In-app download**: New phone entry lists issues, user picks EPUB or PDF, app downloads and imports. Rejected: list-only plus browser download; rejected: local-folder picker with no GitHub.
3. **Latest 3 only**: Show the 3 newest directories whose names start with `te_`. Do not list full history or the `2025` folder.
4. **Official GitHub first**: List via `api.github.com`, download via `raw.githubusercontent.com`. On failure, show an error. Mirror prefix is later, not this round.
5. **Confirmed understanding**: User confirmed the scope above before design.
6. **Trigger `brainstorming`**: User approved moving to design before code.
7. **Write this memory file**: User confirmed a new file, not an update of the DeepTutor memory.
8. **Approach A (two-step catalog)**: Settings button lists the 3 newest `te_*` dirs, then that folder's EPUB/PDF. Rejected: prefetch all three folders' files on open; rejected: guess `TheEconomist.YYYY.MM.DD.epub/pdf` without listing the folder.
9. **Architecture approved**: No new Activity or library. `EconomistCatalog` parses JSON. `EconomistSource` uses `HttpURLConnection` (User-Agent `Y`) to list and download into a cache temp file. `EconomistPicker` dialog drives the two steps, then existing importers and `ShelfStore`. Temp file deleted after import. Failures show in the dialog.
10. **Data flow approved**: List `contents/01_economist`, show 3 names; open one issue with a second contents call; back does not refetch the issue list. Download with `DownloadProgress` to cache, import, `ShelfStore.save` using the GitHub file name, delete temp, close dialogs, open the book. Network and extract run off the main thread.
11. **Error handling approved**: One line in the dialog plus 重试. No stack traces. Temp file deleted on failure or dismiss. Dismiss cancels an in-flight download so a closed dialog cannot still save a book. Messages: 连不上 GitHub; 403 访问次数过多; 404 找不到; other HTTP code; 期次列表无法解析; 没有找到最近的期次; 这一期没有 EPUB 或 PDF; 下载失败; 这本书无法导入 (including empty extract — do not save). Retry repeats only the current step.
12. **Tests approved**: JVM unit tests only, no live GitHub and no UI automation. Cover latest-3 filtering, epub/pdf file filtering, parse and HTTP messages, and magazine splits.
13. **Execute directly**: User chose implementation in this session, not a written plan.
14. **Economist chunks follow desktop magazine logic**: Port the intensive-reading magazine split (section headings, weak/TOC spine titles, page headings, 1200-word oversized split). Do not use the phone's generic ~400-word `Chunker` for these imports.
15. **Reversed: three local open buttons stay**: User asked to merge 「打开 TXT / EPUB / PDF」 into one 「导入本地文件」. Format is known after the file is chosen. 「经济学人」 stays its own button.
16. **Chapter list while reading**: Same idea as desktop Passage TOC. Jump to that chunk. Label is the stored article title when the import has one (magazines); otherwise 「第 N 段」. Rejected: use the first line of the body as the name. Rejected: show only the index when a title exists.
17. **Shelf delete**: Each shelf row can delete that book. Confirm first. If the deleted book is the one open, return to the shelf. Unrecognized local files show one line and are not saved.
18. **Trigger `brainstorming` for the three UI changes**: User approved design before code, and approved updating this memory file.
19. **Store titles apart from passage text**: On save, each book file keeps the chunk strings and a parallel title list. Economist import writes article titles. Local import writes blank titles, and the list shows 「第 N 段」. Books already on the shelf stay readable with blank titles. Rejected: infer the title from the first line of the body. Rejected: chapter list only for Economist books.
20. **Architecture approved**: One 「导入本地文件」 launcher; detect suffix, then MIME. Book file stores chunks plus titles; old chunk-only files still open. Top bar 「章节」 jumps the pager. Shelf row 「删除」 confirms, then removes the index entry and the book file; deleting the open book returns to the shelf.
21. **Data flow approved**: Local import saves chunks with blank titles and opens the book. Economist import writes article titles in the same order as the passages. Opening a book loads both; a chapter tap stores the new position. Delete removes the index entry and the book file, and clears last-opened when that book was last.
22. **Errors approved**: Unknown format shows 无法识别这个文件 and does not save. A recognized file that cannot be read shows 这本书无法导入 and does not save. Canceling the picker does nothing. Delete asks 删除这本书？; cancel keeps the book; a missing file still leaves the shelf. Title count mismatches become blank titles, and reading continues. Blank titles display as 「第 N 段」.
23. **Tests approved**: JVM unit tests only. Cover suffix-then-MIME detection, shelf save/load of titles, old chunk-only files, title-count mismatch, delete including a missing file and last-opened cleanup, Economist titles aligned with passages and TOC excluded, and chapter labels （title or 「第 N 段」, 1-based）.
24. **Execute the UI design directly**: User chose implementation in this session, not a written plan, and approved saving the full design in this memory file.
25. **UI implementation landed**: One 「导入本地文件」 button detects suffix then MIME (`FileKind`). Book files are `{"chunks","titles"}`; old JSON arrays still open with blank titles. Top bar 「章节」 uses `ChapterLabels` (stored title or 「第 N 段」) and jumps the pager. Shelf 「删除」 confirms, then `ShelfStore.delete`. Unknown format shows 无法识别这个文件; unreadable content shows 这本书无法导入. Economist `readEpub` / `readPdf` / `readPages` keep article titles beside passages and skip TOC. User asked for `requesting-code-review` and to record this state.
26. **UI review, no Critical or Important**: Reviewer found Minor-1 (name/MIME lookup outside the import try), Minor-2 (opening a missing book file is silent), Minor-3 (`chapterJump` can survive leaving the reader). User sent them to `receiving-code-review`. Triage: all three ACCEPTED from source. Rejected as defects this round: double `selected()` call (idempotent today), moving local import off the main thread (not a regression; approved local design did not require it).
27. **All three minors fixed**: User said to apply all. `LocalImport.probe` catches name/MIME failures and returns 这本书无法导入. `BookOpen.errorIfEmpty` shows that line and leaves the shelf index. `ChapterJump.consume` clears the pending page in `finally`; shelf, open, delete, and save call `reset()`. User asked for a follow-up `requesting-code-review` of these fixes.
28. **Follow-up review accepted one minor**: No Critical or Important. Minor-1: `ChapterJump.consume` clears `target` even when a newer `request` arrived during `scrollToPage` (`ChapterJump.kt:15-16`, call at `MainActivity.kt:266-267`). User sent it to `receiving-code-review`. Triage: ACCEPTED. `finally` should clear only when `target` is still that page.
29. **Chapter jump no longer drops a newer request**: `finally` clears `target` only when it still equals the page that scroll captured. `ChapterJumpTest.newerRequestSurvivesCancelledScroll` failed first (`target` was null), then passed. User accepted this state after two review-fix rounds and declined another review.

---

## Confirmed Assumptions (required)

- Target is `mobile/ir-android`, not the desktop reading page.
- Magazine files are downloaded on the device at runtime and are not committed to git.
- MOBI and README inside an issue folder are not import targets unless the user later asks.
- Local TXT/EPUB/PDF still use the existing ~400-word `Chunker`. Economist imports still use `MagazineChunker`.
- A file whose format cannot be told shows one Chinese line and is not written to the shelf.

---

## Constraints & Non-Goals

- Do not list every historical `te_*` issue.
- Do not add a GitHub mirror in this round.
- Do not change desktop Jarvis or the web intensive-reading UI.
- Do not commit PDF/EPUB/MOBI into the repo.
- Do not use the first line of a passage as the chapter name.

---

## Key Discoveries (required)

- Import today is `SettingsDialog` buttons plus three `ActivityResultContracts.OpenDocument` launchers in `MainActivity.importUri`. Failures are only `Log.e`, no on-screen error.
- `INTERNET` is already in `mobile/ir-android/app/src/main/AndroidManifest.xml`.
- `MirrorModelDownload` already downloads with `HttpURLConnection`, User-Agent `Y`, progress labels, and temp-file cleanup. Shelf stores extracted text chunks (`ShelfStore.save`), not the original file.
- Issue `te_2026.09.19` contains `README.md`, `TheEconomist.2026.09.19.epub` (~6.3MB), `.mobi` (~7.9MB), `.pdf` (~9.0MB). `download_url` is `raw.githubusercontent.com` on `master`.
- Directory names encode the date (`te_YYYY.MM.DD`), so newest-3 is a name sort, not a separate API.
- `ShelfStore` persists `{id}.json` as a JSON array of strings. `ShelfEntry` has no per-chunk titles. `MagazineChunker.passages` returns strings only, so article titles are dropped before `save`.
- `ReaderScreen` shows one passage. The pager and page index live in `MainActivity`. There is no chapter control. `ShelfScreen` opens a book and has no delete.
- `ShelfStore` new saves write `{"chunks","titles"}`. `loadChunks` / `loadTitles` still read an old JSON array of strings and treat titles as blank. Title lists shorter than chunks are padded; longer lists are truncated.
- `MagazineChunker.selected` is the same TOC-and-blank filter `passages` uses, so Economist titles stay aligned with passage text.

---

## Current State (required)

- **Working**: Local import, chapter list, and shelf delete are in the app. Two review-fix rounds are done; the user accepted the current state. `ChapterJump.consume` keeps a newer page if one was requested during a cancelled scroll.
- **Pending**: Phone has not tried Economist import or the new buttons.
- **Blocked**: None.

---

## Next Steps (required)

1. [x] Economist import implemented and unit-tested.
2. [x] Chapter titles are stored beside the passage text. Architecture approved.
3. [x] Data flow and errors approved.
4. [x] Tests approved. Execute directly in this session.
5. [x] Implemented. Unit tests passed. Phone not tried.
6. [x] Review completed. Three minor findings accepted; fixes not applied yet.
7. [x] User chose to apply all three minor fixes. Unit tests passed.
8. [x] Follow-up review done. Minor-1 fixed. User accepted the current state and stopped the review loop.
9. [ ] Try on a phone: 设置 → 导入本地文件; 阅读时点章节; 书架删除; 经济学人 still untried against live GitHub.

---

## Notes for Next Session

- User wants only the latest 3 `te_*` batches, then EPUB or PDF, official GitHub, error text on failure.
- Do not resume DeepTutor living book.
- Confirmed UI: one 「导入本地文件」 button; chapter label is the stored title or 「第 N 段」; shelf delete confirms, and deleting the open book returns to the shelf.
- Review loop for this UI stopped after two rounds. Do not start a third unless asked.

---

## References (required)

- https://github.com/hehonghui/awesome-english-ebooks/tree/master/01_economist — issue folders
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/MainActivity.kt` — `importUri`, reader pager
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/SettingsDialog.kt` — import buttons
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/ShelfScreen.kt` — shelf list
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/ReaderScreen.kt` — one passage
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/ShelfStore.kt` — shelf persistence
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/MagazineChunker.kt` — titles exist before `passages`
- `web/src/pages/ReadingPage.tsx` — desktop Articles/Chapters dropdown
- `docs/memory/memory-20260920-deeptutor-comparison.md` — unrelated; do not extend

---

**Confirmed at**: 2026-09-23 ~14:30 UTC+8
