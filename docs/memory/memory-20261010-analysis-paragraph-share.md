# Memory: Android 分析分段分享

**Generated**: 2026-10-10 10:50
**Last updated**: 2026-10-16 12:05
**Project**: c:\jarvis
**Focus**: 精读分析按空行分段，每段可分享到系统面板（含微信）

---

## Goal & Scope

Android 精读的「好词好句」和「社会文化」里，分析正文按空行分成段，每段下面有「分享」。点了打开系统分享面板，可以选微信。分享正文第一行是书名，后面是这一段。只改 `mobile/ir-android`。点词释义不改，不接微信专用接口。

---

## Key Decisions

1. **按空行分段，不是按条目卡片**：用户选定空行。模型如果整篇没有空行，结束后整篇只有一个分享。Rejected: 整篇一个按钮；模型按条目输出卡片。
2. **按钮放在该段文字下面**：字大好点。Rejected: 右上角小图标；长按分享。
3. **生成中只分享已经以空行结束的段**：未完成的尾巴只显示文字，没有按钮。生成结束后最后一段也可以分享。
4. **系统分享面板**：`ACTION_SEND` 纯文本。不集成微信 SDK。
5. **直接实现，不另写计划**。用户要求把设计写入本记忆文件。
6. **分段分享评审可以合并**：2026-10-10 评审没有 Critical、Important、Minor。用户要求把结论写入本文件。建议以后再补的回归（`\r\n`、两段已闭合加一段未闭合、读屏时区分多个「分享」按钮）不挡使用，本轮不改。
7. **按编号切分享，不再按空行**（2026-10-16）：1. 2. 3. 和 一、二、三 各自成一块。编号前的总标题并进第一条。一块内部的空行和分隔线不再单独分享。笔记跟分享用同一块。生成未结束时，最后正在写的那一条先不给分享。Rejected: 只认中文编号；总标题单独分享；总标题不给分享。

---

## Confirmed Assumptions

- 分享内容带书名。书名为空时只分享这一段。
- 空段丢掉。一段内部的单个换行不算新段。

---

## Key Discoveries

- 分析面板目前把整段流式文字画成一个 `Text`，没有段边界。
- Android Studio 的 Run 在设备未选中时不会安装。覆盖安装用 `gradlew :app:installDebug`，不删除书籍和已下载的 Qwen。

---

## Current State

- **Working**: 分享和笔记按编号切块。1. 2. 3. 与 一、二、三 各成一块，总标题并进第一条。`AnalysisShareTest` 已通过。
- **Pending**: Minor-2 仍先不改：两条之间的 `---` 该留在上一块，测试没钉死。Minor-1 的补测试复查（agent 4f1d6fc6）没有新问题。模型若整篇没有编号，结束后整篇只有一个分享。
- **Blocked**: 无。

---

## Next Steps

1. [x] 实现 `AnalysisShare` 分段和分享正文。
2. [x] 单测通过，并覆盖安装到手机。
3. [x] 代码评审通过，没有必须修改的问题。

---

## References

- `mobile/ir-android/app/src/main/java/com/jarvis/ir/ui/AnalysisPane.kt` — 分析面板
- `mobile/ir-android/app/src/main/java/com/jarvis/ir/MainActivity.kt` — 书名与分析状态

---

**Confirmed at**: 2026-10-10 10:50
