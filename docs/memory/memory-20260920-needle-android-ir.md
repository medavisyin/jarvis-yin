# Memory: Needle Android Intensive Reading Feasibility

**Generated**: 2026-09-20 ~18:10 UTC+8
**Last updated**: 2026-09-22 ~13:25 UTC+8
**Project**: c:\jarvis
**Focus**: Needle Android 精读 APK：可行性 + 已批准设计 + 实现计划（单 Android 栈）

---

## Goal & Scope (required)

做一个不依赖 Jarvis 后端的原生 ARM64 Android APK；唯一功能是精读：手机本地导入书，选中单词或词组后展示 ECDICT 词性/中文释义 + 原文例句。语境一句中文由已下载的 Qwen 写。Needle 只抽 headword / 选 sense_id，不写长文。Windows 只用 Android Studio 编译，推理在 USB 真机上。桌面显示名是 Y，包名仍是 `com.jarvis.ir`。

---

## Key Decisions (required)

1. **精读范围 = 结构化抽取，不写长文**：选词后只要词性 / 释义 / 例句，不要 Jarvis 式段落分析 Tab / 口语 / TTS / 笔记。
2. **产品形态 = 原生 Android APK**：可脱离 Jarvis，手机本地跑 Needle。Rejected: 微信小程序、WebView/PWA+WASM。
3. **书源 = 手机完全自给**：Android 上导入 PDF/EPUB（或纯文本），本地切段阅读。Rejected: Jarvis 导出 pack；第一版只粘贴一段。
4. **可行性阶段交付 = 结论 + 建议架构**；随后用户 Trigger `brainstorming` 并批准设计，再选 `writing-plans`（standard / 同一会话）。
5. **理解已确认**：释义主要来自本地词典工具；Needle 负责选工具 / 填参 / 抽字段 / 按语境选义项，不当英语老师写长解释。
6. **可行性结论 = 有条件可以**：Needle 适合做选词路由与 grounded 抽取；不适合生成释义。条件是 App 自带词典 + JNI 包一层 C API + 自管 PDF/EPUB。
7. **电脑测试深度曾选 C**（Windows Python 闭环 + Jarvis 书 + JNI 冒烟），随后 **Reversed**。
8. **Reversed: Windows 上用 Python `cactus-needle` 做推理测试**：用户要求一切都是 Android 一套，不需要 Windows 推理；Windows 只装 Android Studio 编译/部署。
9. **词典 = 完整 ECDICT**（电脑与手机同一份）；在单 Android 栈下落地为 APK 内同一 sqlite。
10. **真机可用 USB 装 APK**；Studio 可以现装。Windows x64 模拟器不是 Needle 推理主路径（见 Key Discoveries）。
11. **Brainstorming 设计已批准（2026-09-21）**：Kotlin/Compose + NDK；工程 `c:\jarvis\mobile\ir-android\`；ECDICT sqlite；选词闭环；M1 范文 → M2 EPUB/TXT → M3 PDF；abiFilters 仅 `arm64-v8a`。
12. **实现计划**：`docs/plans/2026-09-21-needle-android-ir.md`（standard 模式）。Fine-tune 明确不在本计划内。
13. **语境一句中文用 Qwen，不替换词典**：保留 ECDICT。点词只出词典。讲解模型用单独「下载」按钮，可选 `qwen3-0.6` 与 `qwen3-1.7`。选中不自动下载。Hy-MT 整句翻译这次不做。
14. **模型名单走不通时改下 Hugging Face 镜像**：Cactus 默认向 `vlqqczxwyaodtcdmdmlw.supabase.co` 要下载地址。本机和华为都连不上（连接被重置），按钮上显示 `Failed to get model`。镜像包不打进 APK。
15. **权重必须对上 Cactus 1.4.3（2026-02-10）**：2026-04 的 `qwen3-0.6b-int4.zip`（v1.14）解压后 `cactus_init` 失败。`qwen3-0.6` 改下 2026-02-06 的 `weights/qwen3-0.6b.zip`（commit `be1f1740`，约 575MB）。`qwen3-1.7` 最早可用包是 2026-02-18 的 `qwen3-1.7b-int4.zip`（commit `fafba006`，约 810MB），尚未在真机验证。打不开时删掉本地模型，按钮回到「未下载」。上次已下载的 v1.14 已从手机删除，必须重下 575MB 包。
16. **选词改为长按再拖**：单词和词组同一套。长按后拖到末尾，正文高亮，松手后正文下面出现 Explain，点了才弹小窗。普通滑动仍翻页。Rejected: 按住立刻拖（正文不能翻页）；系统选中手柄。小窗内容仍是词典卡；整段词组不在词典里时显示选中文字和原句，模型已下载再加一句中文。不再一点单词就在正文下面出卡。整页美化、Hy-MT 仍不做。

---

## Confirmed Assumptions (required)

- 离线推理；不依赖 Jarvis `/api/intensive-reading/*`
- 选词为主；选句可后做
- 例句优先复制原文句子（grounded span），不让模型编教学例句
- 词性可用 enum 分类；中文释义必须来自词典条目，不能从模型凭空生成
- 自用，不是对外产品

---

## Constraints & Non-Goals (include when relevant)

- 不搬 Jarvis Analysis Tab / TTS / 口语 / RAG / Explain 长文
- Fine-tune Needle 不在本计划
- 不提交 `needle3.cact` / `libneedle.a` / 完整 `ecdict.db`
- 不走微信小程序（无法加载 `libneedle`）
- 不把整本书塞进 Needle 上下文（默认 `buffer_size=65536`）

---

## Key Discoveries (required)

- Needle 3 明确 **不做自由文本回复**：`type=respond` 时答案就是 tool results；off-topic 返回空 `function_calls`。官方 README 写明 trade general chat capacity 换 tool-call / extraction。
- Structured extraction 的字段必须是 **passage 中的 span**（或 enum 分类）。没有 span 的 optional 字段会被省略，不会编造。因此「生成中文释义」不在能力内。
- 官方 Android 引擎存在：`android-arm64` / `android-armv7` / `android-riscv64`，每套 `<1MB` engine + `libneedle.a` + `needle.h`；权重 `needle3.cact` 8–29MB（2–20 layers）。见 [supported devices](https://cactuscompute.com/blog/needle-supported-devices)（2026-09-18）。
- C API：`needle_init` / `needle_complete` / `needle_embed`；进程内一份模型。Android 需要自己写 JNI/Kotlin 包装，没有现成 AAR。
- 同一模型可 `embed()` 做句向量，本地搜相似句；精读 v1 非必需。
- 默认遥测开启，APK 需设 `NEEDLE_TELEMETRY=0` 与 `DO_NOT_TRACK=1`。
- 现有 Jarvis IR 依赖本地 Ollama 写全英文/中文讲解（`scripts/rag/intensive_reading/prompts.py`）；与 Needle 的行为契约不兼容。2026-08-21 曾讨论过 Android pack（预生成标注、手机只读），后因翻译质量差删除 overlay/pack；当时明确 **本次不做原生安卓 App**。这次是新方向：手机本地模型 + 词典，而不是桌面预生成。
- **Needle 没有 `android-x86_64` 引擎**，只有 `android-arm64` / `armv7` / `riscv64`。Windows Studio 默认 AVD 是 x86_64，跑不了 `libneedle`；在 Intel/AMD Windows 上开 arm64 系统镜像会走软件翻译，慢到不能当主测试。因此「电脑上用 Studio 测」= Windows 编译 + USB 部署到 ARM64 真机。
- `huggingface.co` 在本机超时；`HF_ENDPOINT=https://hf-mirror.com` 可下到 `needle3.cact` 35.3MB、`libneedle.a` 1.66MB。
- 实机 `needle.h`：`needle_load(cact, n)` 装权重；`needle_init(system_prompt, tools_json, tool_index_path)` 不接收模型路径；`needle_complete(input, max_new_tokens, out, cap)`；`needle_embed`；`needle_reset`；`needle_last_error`。
- 2026-09-22 点词闪退：`CactusLM.downloadModel` 抛 `Failed to get model qwen3-0.6`（主线程未捕获）。根因是 `Supabase.getModel` 连不上 `vlqqczxwyaodtcdmdmlw.supabase.co`。镜像若下到 2026-04 的 `qwen3-0.6b-int4.zip`（权重 v1.14），文件夹里有 `config.txt` 和 `layer_*.weights`，但 Cactus 1.4.3（2026-02-10）的 `cactus_init` 返回空，卡片显示 `Failed to initialize model context`。要对上引擎，改下 2026-02-06 的 `weights/qwen3-0.6b.zip`（commit `be1f1740`，约 575MB）。解压目录是 `files/models/<slug>/`。

---

## Open Risks (include when relevant)

- PDF/EPUB 解析与切段是比 Needle 更大的工程风险（桌面端已踩过 pypdf 行折/段界）
- 未实测 Needle 在「词典多义项 + 原文语境 → 选 sense_id」上的准确率；可能需要少量 fine-tune
- JNI / NDK 打包、16KB page size、arm64-v8a 兼容是集成风险，不是模型能力风险
- 本地词典体积（ECDICT 等）可能比 29MB 模型还大

---

## Current State (required)

- **Working**: 华为 GRL-AL10 上 ECDICT 查词已通。显示名 Y 的新包已安装（2026-09-22）。下载按钮显示百分比。屏幕状态是「未下载」，因为打不开的 v1.14 权重已删除。
- **Pending**: 用户重下 `qwen3-0.6`（575MB，2026-02-06）。长按拖选 + Explain 小窗已选方案，设计确认后才改代码。界面美化、Hy-MT 未做。
- **Blocked**: Cactus 官方模型名单（supabase.co）连不上。2026-04 权重和 1.4.3 引擎对不上，不能复用上次下载。

---

## Next Steps (required)

1. [x] Task 1–11 电脑侧（M1 UI + JNI 编译、M2 TXT/EPUB、M3 PDF）
2. [x] USB ARM64 真机：GRL-AL10 点 `bank` 成功（2026-09-22）
3. [x] 完整 ECDICT 精简库已放入 assets（未提交 git）
4. [ ] 在已安装的 Y 上选 `qwen3-0.6 · 575MB`，点「下载」，下完再点词看一句中文（当前包仍是点一下就出卡）
5. [ ] 设计确认后实现：长按拖选、Explain、小弹窗
6. [ ] 界面改版稍后

---

## Notes for Next Session (include when relevant)

- 不要把 Needle 当成 Ollama 替代品去 port `/api/intensive-reading/explain-selection`
- 推荐闭环：选区 → Needle 抽 headword/span → 本地词典 → 把义项列表喂回 Needle → 抽 `sense_id` + 原文例句 span → UI 展示词典释义
- 官方构建：`needle build --platform android-arm64 [--layers N]`

---

## References (required)

- https://github.com/cactus-compute/needle
- https://cactuscompute.com/blog/structured-extraction-with-needle
- https://cactuscompute.com/blog/needle-supported-devices
- https://cactuscompute.com/blog/needle-python-docs
- https://raw.githubusercontent.com/cactus-compute/needle/main/llms.txt
- `scripts/rag/intensive_reading/prompts.py` — 现有 Jarvis 精读 prompts（长文，与 Needle 不兼容）
- `docs/memory/memory-20260821-intensive-reading-android-cost.md` — 上次 Android/pack 结论（已删除 pack；当时不做原生 App）
- `docs/plans/2026-09-21-needle-android-ir.md` — 已批准设计的实现计划

---

**Confirmed at**: 2026-09-21 ~11:20 UTC+8
