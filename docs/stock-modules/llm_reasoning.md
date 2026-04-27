# LLM 综合推理 (llm_reasoning) — 详细功能文档

**文件路径**: `scripts/stock/llm_reasoning.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 为**单只股票**聚合并格式化 **技术分析、基本面、新闻情绪、（可选）XGBoost 方向预测、（DeepSeek 版）近 20 日 OHLCV、资金流向、价格预测、大盘情绪** 等多源信息，由 **Ollama 本地大模型** 或 **DeepSeek API** 生成**中文投资预测报告**（并写入 `STOCK_DATA_DIR/{symbol}/` 下 Markdown）。
- **系统角色**: Stock 子系统的**「综合研判与叙事输出」**层，衔接 `technical_analysis.analyze`、`fundamental_analysis`、`sentiment`、`china_market_data`、`market_sentiment`、以及磁盘上的 `xgb_prediction.json` / `price_prediction.json`。
- **上下游**  
  - 上游: 各分析模块与已缓存的 ML 输出。  
  - 下游: 前端展示 `prediction-report.md` 或 `prediction-report-deepseek.md`；可被 `agent` 或其它 API 直接调用 `generate_prediction` / `generate_prediction_deepseek`。

```
[TA + FA + 情绪] → (可选) xgb/price 文件
       → _build_prompt / _build_deepseek_prompt
       → Ollama (stream 可选) 或 call_deepseek
       → Markdown 落盘
```

---

## 2. 金融理论基础

- **多源信息融合 (Information fusion)**: 将价量技术位、财务与估值、媒体情绪、**订单流/主力阶段**、**盘感型 ML 概率**置于同一上下文中，由 LLM 做**一致化叙事**与**风险权衡** — 符合「不依赖单一 α 源」的实务框架。
- **贝叶斯/概率化表述 (DeepSeek 版)**: 系统提示要求**给出概率、情景**而非点估计一句话，与行为金融中**过度自信**的纠正一致。
- **A 股微观结构**: DeepSeek 提示词显式要求 **T+1、涨跌停、散户结构、主力吸筹/出货解读**，与**市场微观结构**相关表述一致；本地版强调**可操作建议与关键价位**以约束幻觉。
- **本模块未单独实现「因子」**，而是**特征汇总 + 语言模型** — 理论上的限制是**不可保证校准的概率**，但提升了**可解释性**（面向散户用户）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- `_load_or_compute(symbol)` 返回的 `dict`:  
  - `technical`: `technical_analysis.analyze` 全量。  
  - `fundamental`: 含 `profile`, `financials`, `valuation` 等。  
  - `fund_score`: `score_fundamentals` 结果。  
  - `sentiment`: `STOCK_DATA_DIR/.../sentiment.json` 或现场 `analyze_stock_sentiment`。  
  - `xgb_prediction`: 若存在 `xgb_prediction.json` 则载入（含 `prediction`, `probabilities`, `walk_forward`, `feature_importance` 等键 — 以文件为准）。  

- **DeepSeek 报告返回** `generate_prediction_deepseek`：`{"report", "reasoning", "model", "usage"}` 或 `{"error"}`。

### 3.2 关键函数/类

| 函数 | 签名与行为 |
|------|------------|
| `_load_or_compute(symbol)` | 拉齐 TA/FA/情绪/XGB 缓存。 |
| `_build_prompt(symbol, data)` | 紧凑中文摘要，供**本地** Ollama。 |
| `generate_prediction(symbol, stream=False)` | `POST {OLLAMA_HOST}/api/chat`，`model=MODEL_USAGE["prediction_reasoning"]`，`temperature=0.6`, `num_predict=1500`；去 ``；写 `prediction-report.md`；`stream=True` 时返回**逐 token 生成器**并过滤 think 段。 |
| `_build_deepseek_prompt(symbol, data)` | **扩展版**：`daily.csv` 近 20 行表、**全量**指标与信号、**全部新闻条**表格、XGB 细节、`price_prediction.json`、**`stock_fund_flow_signals`**、**`get_market_sentiment()`** 大盘。 |
| `generate_prediction_deepseek(symbol)` | `call_deepseek(..., max_tokens=8192)`，写 `prediction-report-deepseek.md`，返回 report/reasoning/usage。 |
| `_make_system_prompt` | 本地版**段落结构**要求（方向、信心、1–2 周、风险、操作、价位）。 |

### 3.3 算法与计算逻辑

- **非模型训练**：本文件不包含训练逻辑；XGB/价格预测**依赖其他模块**事先写入 JSON。  
- **Prompt 工程**: 本地版**截断**为关键指标子集；DeepSeek 版**富数据**以支持**交叉验证**指令（技术×资金×基本面×情绪矛盾分析）。  
- **流式**: 对 `in_think` 状态机跳过 `` 间内容。  
- **HTML 与文件**: 报告为 Markdown 文本；无 PDF（PDF 在 `stock_pdf`）。

---

## 4. 外部依赖与数据源

- **Ollama**: `OLLAMA_HOST`, `MODEL_USAGE["prediction_reasoning"]`。  
- **DeepSeek**: `config.call_deepseek`（如 deepseek-v4-pro 等以 config 为准）。  
- **磁盘**: `STOCK_DATA_DIR/{symbol}/daily.csv`, `sentiment.json`, `xgb_prediction.json`, `price_prediction.json`。  
- **动态 import**: `china_market_data.stock_fund_flow_signals`, `market_sentiment.get_market_sentiment` — 失败时对应章节静默省略。

---

## 5. 配置项与可调参数

| 项 | 默认值/来源 | 说明 |
|----|-------------|------|
| `MODEL_USAGE["prediction_reasoning"]` | 如 `qwen3.5:4b` | 本地报告模型 |
| Ollama `options` | `temperature=0.6`, `num_predict=1500`, `num_ctx=4096` | 可调创造性长度 |
| `call_deepseek` | `max_tokens=8192` | DeepSeek 长报告 |
| `stream` | `False` | True 时用于 SSE 接口 |

**调优**: 长报告易超时 — 可降 `num_predict` 或换更快模型；DeepSeek 成本高，适合**重点标的**。

---

## 6. 使用示例与工作流

```python
from llm_reasoning import generate_prediction, generate_prediction_deepseek
text = generate_prediction("600519", stream=False)   # 本地
result = generate_prediction_deepseek("600519")     # 需 API key
```

**协作**: 先跑技术分析 + 拉财务 + 情绪分析；再跑 `model_xgboost` / `model_price_predictor` 以填满 DeepSeek 上下文，否则相关章节空白。

---

## 7. 已知限制与改进方向

- 本地 `_build_prompt` 对**指标全量**有删减，与 DeepSeek 版**信息密度**不一致。  
- 无自动**事实核查**；财务数据错误会传导进报告。  
- 未对 LLM 输出做结构化 schema（如强制 JSON 评分）。  
- 改进: 统一两版本提示结构、增加引用编号（[1] 对应具体新闻/数据行）、对接 `stock_pdf` 一键出 PDF。
