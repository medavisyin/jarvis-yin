---
tags:
  - guide
  - laya
  - intent
category: guide
status: current
last-updated: 2026-09-28
---

# Laya 在 Jarvis 里做什么

Laya 是本地的**封闭标签分类器**。你事先写好允许的答案，它从这份名单里选一个，并给出概率。它不写回复、不念简报、不预测股价。

Jarvis 只用它做一件事：聊天意图还没被关键词命中时，从固定意图名单里选一个。代码在 `scripts/rag/intent.py`。

---

## 1. Laya 能干什么

一次前向计算里可以回答三种固定题型：

| 题型 | 返回 | Jarvis 是否使用 |
|------|------|-----------------|
| **choice** | 名单里的一个标签，加上概率 | 使用。意图名单约 13 项 |
| **score** | 有顺序的分数 | 不使用 |
| **noul** | 是或否的概率 | 不使用 |

它还可以做语言路由、批量打分、HTTP 服务、MCP、微调。这些没有接进 Jarvis。本机是 CPU，没有 CUDA。英文检查点已经缓存在本机；中文不直接送给这个检查点。

Jarvis 里的意图名单：

`knowledge_qa`、`jira_report`、`commit_summary`、`confluence_wiki`、`project_query`、`team_activity`、`explain_topic`、`trend_analysis`、`ai_news_kb`、`finance_news`、`stock_analysis`、`smalltalk`、`out_of_scope`。

学习会话（AI 学习、英语、AWS、深读）由会话类型决定，不经过 Laya。

---

## 2. 怎么安装

Jarvis 启动脚本 `bin/jarvis-start.bat` 用的是命令 `python`，也就是 Microsoft Store 的 Python 3.13。Laya 装在这个解释器里，不在 `py` 启动器指向的另一份 Python 3.13 里。

已安装时可检查：

```powershell
python -c "import laya; print(laya.__version__)"
```

应打印 `0.3.21`（或你后来升级的版本）。`py -m pip show laya` 找不到包是正常的。

尚未安装时，用同一个 `python`：

```powershell
python -m pip install laya
```

第一次真正分类会从 Hugging Face 读取英文检查点 `convaiinnovations/laya`。这台机器上 `huggingface.co` 会超时。两条路：

```powershell
# 下载时走本机 SOCKS5
$env:HTTP_PROXY = "socks5://127.0.0.1:10808"
$env:HTTPS_PROXY = "socks5://127.0.0.1:10808"
$env:ALL_PROXY = "socks5://127.0.0.1:10808"
laya "I was charged twice, please refund" --predict
```

缓存完成以后，Jarvis 进程会把 Hub 设为离线（`HF_HUB_OFFLINE=1`），和 RAG 读本地向量模型的方式一样。缓存目录：

`C:\Users\rong.yin.MEDAVIS\.cache\huggingface\hub\models--convaiinnovations--laya`

Ollama 里需要已有快速模型 `qwen3:1.7b`。中文查询要先译成英文，这一步由它完成。

---

## 3. 在 Jarvis 里怎么起作用

用户发来一句话之后，`classify_intent` 按这个顺序走：

1. **学习会话**已经知道意图，直接返回。
2. **关键词**命中且置信度至少 0.8，直接返回。例如「分析一下股票行情」含「股票」，结果是 `stock_analysis`，不会翻译，也不会调用 Laya。
3. **其余中文**交给 Ollama `qwen3:1.7b`，译成英文。译文只给分类器用。后面检索和回答仍用原来的那句话。翻译失败，或译文里还带着汉字，就跳过 Laya。
4. **Laya 英文检查点**做 `choice`。`answer_confidence` 达到 **0.6** 就采用这个标签。
5. **达不到 0.6**，或 Laya 报错，改用原来的快速模型分类器（仍是 `qwen3:1.7b`）。

英文句子跳过第 3 步，直接进入第 4 步。

第一次没命中关键词的请求要把检查点载入内存，会比后面的请求慢。检查点留在进程里，不会每次重新下载。

Laya 不替换这些部分：会话路由、关键词规则、话题新旧判断、财经新闻的正则过滤、股票数值模型、Ollama 写出来的回答和语音。

---

## 4. 怎么看得出它在起作用

### 聊天时看 Agent 窗口

用 `bin/jarvis-start.bat` 启动。它会另开一个标题为 **Jarvis Agent** 的黑窗口。分类行打在这个窗口里，不在 `jarvis-start.log`，也不在网页上。

先重启一次，让窗口加载当前代码。浏览器打开 `http://localhost:18889`，在聊天框发一句**不会命中关键词**的话，例如「那个缓存是怎么做的」。

Laya 采纳标签时，黑窗口会出现：

```text
Laya intent: knowledge_qa (0.91) query='那个缓存是怎么做的'
```

后面还会有流水线总行，里面的意图名和上面一致：

```text
Pipeline: query='那个缓存是怎么做的' → intent=knowledge_qa (0.91) | ...
```

其它几种日志表示没采用 Laya：

| 日志 | 含义 |
|------|------|
| `Laya skipped: Chinese translation failed, using fast LLM` | 中文没译成英文 |
| `Laya skipped: classify failed, using fast LLM` | 检查点没载入或调用失败 |
| `Laya intent below 0.60 (got 0.42), using fast LLM` | 有结果，但概率不够 |
| 只有 `Pipeline:` 行，没有 `Laya` | 被会话类型或关键词提前接走了 |

界面上不单独显示「这是 Laya」。以日志里的 `Laya intent:` 为准。

### 不启动服务时单独看

在 PowerShell 里，工作目录是 `scripts\rag`：

```powershell
cd c:\jarvis\scripts\rag
python -c "from intent import classify_intent; r = classify_intent('那个缓存是怎么做的'); print(r.intent.value, r.confidence, r.reasoning)"
```

`reasoning` 以 `Laya English choice:` 开头，并且置信度不小于 0.6，就是 Laya 做的决定。

关键词句子不会出现这句：

```powershell
python -c "from intent import classify_intent; r = classify_intent('分析一下股票行情'); print(r.intent.value, r.reasoning)"
```

这里应是 `stock_analysis`，原因是关键词，不是 Laya。

只想确认安装和检查点，不经过 Jarvis：

```powershell
$env:HF_HUB_OFFLINE = "1"
laya "I was charged twice, please refund" --predict
```

能打印 `Model : english` 和若干分数，说明检查点可离线运行。这不是 Jarvis 的意图名单。
