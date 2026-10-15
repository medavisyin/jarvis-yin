# Memory: 手机书籍按章切页

**Generated**: 2026-10-10 13:25
**Last updated**: 2026-10-10 15:38
**Project**: c:\jarvis
**Focus**: 新导入的 epub、pdf、txt 按章切开，章内仍按词数分页

---

## Goal & Scope

导入的书按章节切开，章节菜单显示章名。一章太长时，章内仍分成几页，每一页都标这一章的名字。经济学人杂志的新导入不走这条路径。书架上已经导入的书不自动重切；每本书可以手动「重切」。

---

## Key Decisions

1. **章内仍分页**：有目录就按目录分章；没有目录就按单独成行的 Chapter 开头分章。一章太长时沿用现在的词数分页，菜单里每页都显示章名。Rejected: 一章只做一页；菜单只列章、点进去再翻页。
2. **只影响新导入**：epub、pdf、txt。已在书架上的书保持原切分，要新规则就重新导入。经济学人杂志不走这条路径。
3. **章名形式**：Chapter / CHAPTER 加数字或罗马数字，以及「第1章」这种单独成行的开头。用户确认包含罗马数字和第1章。
4. **用户确认的切法**（2026-10-10，直接实现）：epub 目录能对上正文至少两处时，按目录切，菜单用目录标题。pdf 和 txt 若有 Contents / 目录清单，且这些标题在后面正文里再出现至少两次，就按那些位置切。否则只认单独成行、较短的 Chapter / CHAPTER 加数字或罗马数字，以及「第1章」。句子中间的 chapter 不切。章名留在正文里。一章仍按大约 400 词分页，每页菜单名都是章名。找不到两章就保持现在的按词切页，标题为空。目录对上同一文件的两个锚点不算两处。
5. **接受切章复查并已改**（2026-10-10）：目录紧挨正文标题时仍切开。短句「Chapter 1 was...」「Chapter I went...」「第1章讲完了」不切。封面加一个正文文件不算两章，ncx 对不上再试 nav。页码不把「Part 1」削成「Part」。一行一个换行也能认出章名。没有标明目录的 nav 不用。链接里的加号保留，坏的百分号不让整本导入失败。`BookChaptersTest` 已通过，并覆盖安装到 GRL-AL10。
6. **第二次复查再改三条**（2026-10-10）：「Chapter 1 Today was fine.」这种大写开头的句子不切；带冒号的章名仍切。「Part  1」空两格不再和「Part  2」撞成同一个「Part」。中文章名按字数放到 40 个字。用户接受当前切章，不再继续复查。
7. **书架重切**：每本书（含经济学人）在「删除」旁边加「重切」，先确认再切。用已保存的正文，不能再读原 epub 目录。找到两章以上就覆盖这一本的分页和章名，阅读位置回到第一页。找不到就保持原样并提示「没有找到章节」。经济学人在书架上的种类也是 epub 或 pdf，无法和本地书区分，所以「找不到章就保持」对所有书一样。用户要求经济学人找不到章时保持原来的分法。做法已实现。
8. **重切复查的两条先不改**（2026-10-10）：审查没有必须改或应该改的问题。Minor-1：`retitle` 只判断有没有章名，少于两章时清章名靠 `fromPlainText`；单独一个 Chapter 1 还没在 `retitle` 上测试。Minor-2：正在打开的那本书回到第一页没有测试盖住。用户决定两条都先不改。

---

## Confirmed Assumptions

- 现在本地导入用 `Chunker`，epub / pdf / txt 都是大约 400 词一页，标题存成空字符串，菜单显示「第 N 段」。
- 章节菜单读的是每页保存的 title。空标题才显示「第 N 段」。
- 经济学人走 `MagazineChunker`，不经过本地 `importEpub`。

---

## Key Discoveries

- `EpubImporter.extractSections` 只取每个 spine 文件的第一个 h1/h2/h3。一章经常不在单独的文件里。本地导入用的是 `extractText` 再 `Chunker.chunk`，章名被丢掉。
- 书架把 chunks 和 titles 一起写进书的 JSON。新导入只要传入每页标题即可，菜单不用改。

---

## Current State

- **Working**: 新导入的 epub、pdf、txt 会按目录或 Chapter 开头切章。书架每本书可手动重切；找到两章以上覆盖同一本并回到第一页，找不到则不改并提示「没有找到章节」。单元测试已通过，并覆盖安装到 GRL-AL10。
- **Pending**: 用一本带 Chapter 或目录的书试手动重切。审查的 Minor-1、Minor-2 用户决定先不改。
- **Blocked**: 无。

---

## Next Steps

1. [x] 用户确认切章做法。
2. [x] 只改本地 epub、pdf、txt 的新导入。
3. [x] 书架重切已实现并装到手机。
4. [ ] Minor-1、Minor-2 先不改。用户若以后要改再做。

---

## References

- `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/Chunker.kt` — 现有按词数分页
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/EpubImporter.kt` — 本地 epub 导入
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/books/ShelfStore.kt` — 每页标题存在这里
- `docs/memory/memory-20261010-mobile-notes.md` — 同一天的笔记分享，分开记

---

**Confirmed at**: 2026-10-10 13:25
