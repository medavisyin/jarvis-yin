# config — 详细功能文档

**文件路径**: `scripts/stock/config.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：为 Jarvis 股票子系统提供**集中化的路径、环境变量、本地 LLM/云端 API 与输出语言**配置；在模块加载时**自动创建**股票数据相关的子目录；封装 **DeepSeek API** 的密钥读取与单次聊天补全调用。
- **系统角色**：处于整个 `scripts/stock/` 链路的**最底层配置层**。`fetch_market_data`、`watchlist`、`technical_analysis`、`fundamental_analysis` 等均通过 `from config import ...` 引用本模块中的目录与常量；本模块还通过 `importlib` **动态加载**上级 `scripts/config.py` 以继承 `JARVIS_ROOT`、`REPORTS_ROOT` 等全局 Jarvis 配置。
- **上下游关系（文字描述）**：
  - **上游**：操作系统环境变量、`scripts/config.py`（父级）、可选的 `scripts/rag/.global_settings.json`（DeepSeek 密钥）。
  - **下游**：所有需要 `STOCK_DATA_DIR`、`OLLAMA_HOST`、`OLLAMA_MODEL_*`、`call_deepseek()` 等的股票脚本与后续分析流程。

```
[环境变量 / scripts/config.py]
         │
         ▼
   [stock/config.py] ──► STOCK_* 路径、OLLAMA、MODEL_USAGE、OUTPUT_LANGUAGE
         │
         ├──► 股票数据目录创建 (STOCK_DATA_DIR / MODELS / CACHE)
         └──► DeepSeek: get_deepseek_key / call_deepseek
```

---

## 2. 金融理论基础

- **配置与投研的关系**：量化/基本面/技术分析依赖**一致、可复现的数据根目录**与**可审计的模型选择**。本模块将「重模型」用于推理类任务、「轻模型」用于分类与摘要，对应投研中**成本—精度权衡**（高频小任务用轻量模型，深度论证用重模型）。
- **为何需要集中配置**：A 股数据与报告若分散在多处，会导致**回测与实盘结论不可比**；统一 `STOCK_REPORTS_ROOT` 与输出语言 `OUTPUT_LANGUAGE = "zh"`，符合**面向中文用户的投资报告**习惯。
- **中国市场的语境**：默认报告根目录在 Windows 下为 `C:/reports/stock`（可通过 `STOCK_REPORTS_ROOT` 覆盖），便于与本地磁盘、备份策略对齐；**代理** `STOCK_PROXY` 在部分网络环境下是访问行情与财务 API 的**必要前提**。
- **DeepSeek 的用途**（在系统中）：用于需要强推理的 API 调用（与 Ollama 本地模型形成互补），在合规与数据许可前提下辅助生成分析文本；**不构成投资建议本身**，配置项只解决「如何连上、用哪个端点」。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **无独立类**；以模块级常量和函数字典为主。
- **`MODEL_USAGE: dict[str, str]`**：键为**任务名**（如 `news_classification`），值为**模型名称字符串**（与 Ollama 或实际部署的 tag 一致）。
- **`call_deepseek` 返回的 `dict`**（成功/失败结构）：
  - `ok: bool`
  - 成功时：`content: str`，`reasoning_content: str`（链式思考，若 SDK/模型支持），`model: str`，`usage: dict`（含 `prompt_tokens` / `completion_tokens` / `total_tokens`）
  - 失败时：`error: str`；当未配置密钥时 `ok=False`，`error="No DeepSeek API key configured"`

### 3.2 关键函数/类

| 符号 | 作用 |
|------|------|
| **父级 config 注入** | `importlib.util.spec_from_file_location` 加载 `scripts/config.py` 为 `jarvis_config`，取出 `JARVIS_ROOT`、`REPORTS_ROOT`。 |
| **`get_deepseek_key() -> str`** | 优先从 `_AGENT_SETTINGS_FILE`（`scripts/rag/.global_settings.json`）读取 `deepseek_api_key`；若无效则使用环境变量 `DEEPSEEK_API_KEY`。 |
| **`_get_deepseek_client()`** | 内部函数：若存在密钥则 `from openai import OpenAI`，`OpenAI(api_key=..., base_url=DEEPSEEK_BASE_URL)`，否则 `None`。 |
| **`call_deepseek(system_prompt, user_prompt, max_tokens=4096, reasoning_effort="high") -> dict`** | 调用 `client.chat.completions.create`，`model=DEEPSEEK_MODEL`（`deepseek-v4-pro`），`stream=False`，`timeout=120`，`extra_body={"thinking": {"type": "enabled"}}`。从 `response.choices[0].message` 取 `content` 与可选的 `reasoning_content`；异常时返回 `ok=False` 与 `error` 字符串。 |

**模块级常量（路径与模型）**：

- `STOCK_REPORTS_ROOT` ← 环境变量 `STOCK_REPORTS_ROOT`，默认 `C:/reports/stock`
- `STOCK_DATA_DIR` = `STOCK_REPORTS_ROOT/data`
- `STOCK_MODELS_DIR` = `STOCK_REPORTS_ROOT/models`
- `STOCK_CACHE_DIR` = `STOCK_REPORTS_ROOT/.cache`
- `WATCHLIST_FILE`、`PORTFOLIO_FILE`：分别为 `watchlist.json`、`portfolio.json`（位于 `STOCK_REPORTS_ROOT` 下）
- `OLLAMA_HOST`（默认 `http://localhost:11434`）
- `OLLAMA_MODEL_FAST` / `NORMAL` / `HEAVY`：默认 `qwen3:1.7b`、`qwen3.5:4b`、`qwen3.5:4b`
- `DEEPSEEK_BASE_URL = "https://api.deepseek.com"`，`DEEPSEEK_MODEL = "deepseek-v4-pro"`
- `OUTPUT_LANGUAGE = "zh"`
- `STOCK_PROXY`：空字符串或代理地址，供**其他模块**在发起 HTTP 请求时使用（本文件自身仅在注释中说明其存在）

**启动副作用**：对 `[STOCK_DATA_DIR, STOCK_MODELS_DIR, STOCK_CACHE_DIR]` 执行 `os.makedirs(..., exist_ok=True)`。

### 3.3 算法与计算逻辑

- **无数值型金融算法**；`call_deepseek` 为**单次非流式** REST 式聊天补全，**不负责** RAG 检索或股票计算。
- **参数选择**：`max_tokens=4096` 作为较长报告类输出的上限；`reasoning_effort` 与 `extra_body` 的 `thinking` 与 DeepSeek 的「思考模式」产品行为对齐，具体以当时 API 为准。

---

## 4. 外部依赖与数据源

- **标准库**：`importlib.util`、`os`、`sys`；`get_deepseek_key` 在读取 JSON 时使用 `json`（函数内 import）。
- **第三方**：`openai`（`OpenAI` 客户端，用于兼容 DeepSeek 的 OpenAI 式接口）——**仅在** `_get_deepseek_client` / `call_deepseek` 时导入。
- **数据文件**：`scripts/rag/.global_settings.json`（可选），键 `deepseek_api_key`。
- **缓存策略**：本模块不实现行情缓存；`STOCK_CACHE_DIR` 仅创建目录，供其他模块或未来扩展使用。

---

## 5. 配置项与可调参数

| 配置 | 来源 | 默认值 | 说明 |
|------|------|--------|------|
| `STOCK_REPORTS_ROOT` | 环境变量 | `C:/reports/stock` | 股票数据与列表根目录 |
| `STOCK_PROXY` | 环境变量 | 空 | HTTP(S) 代理，供其他模块网络请求 |
| `OLLAMA_HOST` | 环境变量 | `http://localhost:11434` | 本地 Ollama |
| `OLLAMA_MODEL_FAST/NORMAL/HEAVY` | 环境变量 | 见代码 | 与 `MODEL_USAGE` 引用名对应 |
| `MODEL_USAGE` | 代码内写死 | 多任务到模型名映射 | 改任务分档时编辑此字典 |
| `DEEPSEEK_API_KEY` | 环境变量 | 无 | 与 global_settings 二选一或备用 |
| `max_tokens` / `reasoning_effort` | `call_deepseek` 参数 | 4096 / `"high"` | 可按任务调整 |

**调优建议**：生产环境用环境变量或统一的 secrets 管理注入密钥，避免将 `global_settings.json` 提交到版本库；`MODEL_USAGE` 中重任务与轻任务**模型名**应根据本机 Ollama 已拉取的镜像名实际填写。

---

## 6. 使用示例与工作流

```python
from config import STOCK_DATA_DIR, call_deepseek, MODEL_USAGE, OLLAMA_MODEL_FAST

# 读取目录（其他模块常见写法）
import os
symbol_dir = os.path.join(STOCK_DATA_DIR, "600519")

# 调用 DeepSeek（需已配置 key）
r = call_deepseek("你是一名A股分析助手。", "用一句话说明PE的含义。")
if r.get("ok"):
    print(r["content"])
else:
    print(r.get("error"))
```

与 **watchlist / fetch** 等协作：子模块只 import 常量，**不**重复解析路径；与 **RAG/Agent** 协作：DeepSeek 密钥与 `scripts/rag` 共用同一配置文件逻辑。

---

## 7. 已知限制与改进方向

- **硬编码的默认盘符路径**（`C:/reports/stock`）在 Linux/macOS 上需通过环境变量覆盖。
- `call_deepseek` 使用固定的 `DEEPSEEK_MODEL` 与 `base_url`，若厂商升级模型名需改代码或改为环境变量可配置。
- 模块加载即 `makedirs`：在**只读或沙箱挂载**的目录上可能失败，需由部署侧保证可写或延迟创建。
- `STOCK_PROXY` 在本文件中**未直接参与** `requests`；若某脚本忘记读取该变量，代理将不生效（属于调用方责任）。

---
