# Jarvis Telegram Bot 实用指南

通过手机上的 **Telegram** 远程向 Jarvis 发命令。技术名词保留英文（括号）说明。

---

## 1. 概述（Overview）

### 功能

**Telegram Bot（Telegram 机器人）** 让你在手机上远程控制 Jarvis：查询服务状态、触发 **Daily Fetch（每日抓取流水线）**、**RAG 检索**、向 **Agent（智能体）** 提问、股票分析与训练、启动 **Scanner（市场扫描）** 等。

### 架构（Architecture）

1. **Bot（机器人）** 通过 **Long Polling（长轮询）** 向 Telegram 拉取 **Updates（更新）**。
2. 收到 **Commands（命令）** 后，使用 **httpx** 调用本机 Jarvis 内部 **HTTP API**：
   - **Search UI（搜索界面）**：默认 `http://127.0.0.1:18888`
   - **Agent（代理服务）**：默认 `http://127.0.0.1:18889`
3. 将 **JSON** 响应交给 **Formatter（格式化函数）** 转成可读文本，再 **Reply（回复）** 到 Telegram 聊天。

---

## 2. 前提条件（Prerequisites）

| 项目 | 说明 |
|------|------|
| **Python 依赖** | `python-telegram-bot`、`httpx[socks]`（若需 SOCKS 代理访问 Telegram） |
| **Telegram 账号** | 用于与机器人对话 |
| **Bot Token（机器人令牌）** | 通过 **@BotFather** 创建机器人后获得 |
| **SOCKS 代理（可选）** | 部分网络无法直连 **Telegram Bot API**，需本地 **SOCKS5** 等 |
| **Jarvis 服务** | **18888**（Search / RAG 相关）与 **18889**（Agent / 工具栏与股票 API）均已启动 |

---

## 3. 安装与配置（Setup）

### 3.1 在 @BotFather 创建机器人（逐步）

1. 在 Telegram 搜索 **@BotFather**，打开对话。
2. 发送 `/newbot`，按提示输入 **Display name（显示名称）** 与 **Username（用户名，需以 bot 结尾）**。
3. 创建成功后，BotFather 会返回一串 **`TELEGRAM_BOT_TOKEN`**，复制保存（勿公开）。

### 3.2 获取自己的 Telegram User ID

常用做法：在 Telegram 搜索 **@userinfobot**（或同类 **ID 查询机器人**），启动后它会回复你的 **User ID（数字）**，对应配置项 **`TELEGRAM_OWNER_ID`**。

### 3.3 编辑 `bot_telegram.env`

文件与脚本同目录：`c:\jarvis\scripts\bot_telegram.env`（也可用系统环境变量覆盖）。

| 变量 | 说明 |
|------|------|
| **`TELEGRAM_BOT_TOKEN`** | 来自 BotFather 的 **Token** |
| **`TELEGRAM_OWNER_ID`** | 你的 **Telegram 数字 ID**；仅该用户可使用命令 |
| **`SOCKS_PROXY`** | 可选。例如 `socks5://127.0.0.1:10808`；留空则直连 |
| **`AGENT_URL`** | Agent 基址，默认 `http://127.0.0.1:18889` |
| **`SEARCH_URL`** | Search UI 基址，默认 `http://127.0.0.1:18888` |

### 3.4 安装依赖

```bash
pip install python-telegram-bot httpx[socks]
```

---

## 4. 可用命令（Commands）

| 命令 | 说明 |
|------|------|
| `/start` | 欢迎与在线提示，并附带命令摘要 |
| `/help` | 列出全部命令说明 |
| `/status` | 检查 Jarvis 服务：**Agent（18889）** 健康检查、**Search UI（18888）** 可达性 |
| `/fetch` | 启动完整 **Daily Fetch** 流水线（耗时约数分钟到数十分钟） |
| `/fetch_step [step]` | 只跑流水线中的某一个 **step**；步骤名须与后端一致（见下方说明） |
| `/search [query]` | 在 **RAG** 知识库中 **Search（检索）**，返回 Top 片段摘要 |
| `/ask [question]` | 向 **Agent** 提问；响应为 **SSE（Server-Sent Events）** 流式拼接后的正文 |
| `/index` | **Index（索引）** 新简报等（调用 Search UI 异步任务） |
| `/knowledge` | **Refresh（刷新）** 知识文档 |
| `/stock [symbol]` | 单标的 **Full stock analysis（完整股票分析）** |
| `/train` | 对关注列表触发 **Daily training（每日训练）**（价格预测等） |
| `/scan` | 启动 **AI market scanner（AI 市场扫描）** |

**`/fetch_step` 步骤名（与 `bot_telegram.py` 提示一致）**：`fetch_sources`、`topic_dedup`、`commit_report`、`jira_daily`、`wiki_fetch`、`ai_audio`、`world_audio`、`china_audio` 等；以后端 **Daily Fetch** 实际注册名为准。

---

## 5. 使用示例（Example Usage）

以下为示意，真实输出随数据与模型变化。

**示例 1：`/status`**

```text
你: /status

Bot:
Agent (18889): running
Ollama: ok
Qdrant: ok
Search UI (18888): running
```

**示例 2：`/search`**

```text
你: /search Jarvis daily fetch

Bot:
Search: "Jarvis daily fetch"

1. 某文档标题 (score: 0.82)
   片段预览文字……
```

**示例 3：`/ask`**

```text
你: /ask 今天简报要点是什么？

Bot:
Thinking...
（随后返回 Agent 流式汇总后的中文回答，过长时可能被截断）
```

---

## 6. 自动启动与手动运行（Auto-Start）

### `jarvis-start.bat`

仓库中 **`c:\jarvis\bin\jarvis-start.bat`** 在拉起 **Search UI（18888）** 与 **Agent（18889）** 后，会再执行一行 **`start`** 最小化窗口启动 **`scripts\bot_telegram.py`**，因此日常用该批处理开机启动 Jarvis 时，**Telegram Bot 会一并启动**（**Polling（轮询）** 模式）。

### 手动启动

在项目环境中执行：

```powershell
python c:\jarvis\scripts\bot_telegram.py
```

### `bot_telegram.pid` 与重复实例

- 启动时会写入同目录 **`bot_telegram.pid`**，记录当前进程 **PID**。
- 再次启动前，脚本会尝试结束旧实例（含 **Windows wmic** 按命令行匹配 `bot_telegram` 的进程），降低 **409 Conflict（冲突）**（多实例抢 **getUpdates**）概率。
- 退出时删除 **PID 文件**。

---

## 7. 安全（Security）

| 要点 | 说明 |
|------|------|
| **Owner-only（仅所有者）** | 仅 **`TELEGRAM_OWNER_ID`** 与发起者 **User ID** 一致时执行命令；他人收到 `Unauthorized.` |
| **Token 不入库** | **Bot Token** 放在 **`.env` / `bot_telegram.env`** 或环境变量中，不由代码硬编码 |
| **回复内容** | 避免在聊天中粘贴密钥；机器人回复为业务摘要，仍勿当作脱敏审计的唯一依据 |

---

## 8. 代理配置（Proxy Configuration）

### 为何需要代理

部分网络对 **Telegram Bot API** 不可达，会导致无法 **Polling** 或频繁超时。此时让本机 **SOCKS5** 客户端（如 **10808** 端口）出网，再把地址填给机器人进程。

### `SOCKS_PROXY` 格式

示例：

```text
socks5://127.0.0.1:10808
```

### 作用范围

在 `bot_telegram.py` 中，**`HTTPXRequest`** 的 **`proxy`** 同时用于 **Bot API 请求** 与 **`get_updates`**，即 **Telegram 侧**走代理；访问本机 **18888 / 18889** 一般为 **localhost**，通常仍走本机直连（取决于系统路由，与代理工具配置有关）。

---

## 9. 故障排除（Troubleshooting）

| 现象 | 可能原因 | 处理建议 |
|------|----------|----------|
| 启动报 **409 Conflict** | 另一进程仍在 **Polling** 同一 **Token** | 结束所有 **`bot_telegram.py`** 进程；依赖 **PID 文件** 与脚本的清理逻辑后重开 |
| **`/stock` 超时** | 完整分析耗时长（脚本对单次请求约 **10 分钟** 级 **Read timeout**） | 稍后重试；确认 **Agent** 与 **Ollama** 负载正常 |
| **`/ask` 无正文或极短** | **SSE** 未解析到 **`answer_chunk` / `token`**；或 **Ollama** 未就绪 | 检查 **18889** `/api/health` 中 **Ollama**；本机确认 **`http://localhost:11434`** 可用 |
| **机器人完全不回** | 网络、代理、或服务未起 | 检查 **`SOCKS_PROXY`**；确认 **18888、18889** 已启动；看运行窗口日志 **`[TelegramBot]`** |

---

## 10. 架构说明（实现要点）

| 主题 | 说明 |
|------|------|
| **手动 Polling 循环** | 未使用库自带的 **`run_polling()`**，改为循环 **`get_updates`** + **`process_update`**，便于在 **409** 时自行退避 |
| **409 退避（Backoff）** | 捕获 **`Conflict`** 后 **Sleep**，**Backoff** 指数增长并有上限（实现中上限约 **30 秒**） |
| **httpx 超时（Timeout）** | **`/stock`** 使用约 **600s** **read**；**`/ask`** 使用约 **300s** **read**；其余多数请求走共享 **`AsyncClient`**（默认 **read** 上限更高，以脚本为准） |
| **`_truncate()`** | 单条回复限制约 **4000** 字符，避免超过 **Telegram 消息长度** |
| **Formatter** | 如 **`_fmt_stock_analyze`**、**`_fmt_scan_result`** 等，将 **JSON** 转为分段可读文本 |

---

*文档对应 `c:\jarvis\scripts\bot_telegram.py` 与 `bot_telegram.env`；若代码变更，请以仓库内实现为准。*
