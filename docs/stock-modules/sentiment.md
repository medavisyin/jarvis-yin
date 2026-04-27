# sentiment — 详细功能文档

**文件路径**: `scripts/stock/sentiment.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：读取已落盘的**个股新闻 JSON**，通过本地 **Ollama HTTP API** 调用 LLM，对单条新闻打 **[-1, 1]** 情绪分，再聚合为日度综合分、趋势与 Markdown 报告。
- **在系统中的角色**：将非结构化文本转为数值化「新闻情绪」因子，与技术面、资金面特征互补；结果写回 `STOCK_DATA_DIR/{symbol}/sentiment.json`。
- **上下游关系**：

```
  STOCK_DATA_DIR/{symbol}/news/*.json  -->  _load_news()
  STOCK_DATA_DIR/{symbol}/profile.json   -->  股票简称(可选)
                    |
                    v
         analyze_sentiment_single()  -->  Ollama /api/chat
                    |
                    v
         analyze_stock_sentiment()  -->  sentiment.json
                    |
                    v
         generate_sentiment_report()  -->  Markdown 字符串
```

- **依赖**：`requests`、`config`（`STOCK_DATA_DIR`、`OLLAMA_HOST`、`MODEL_USAGE`）。

---

## 2. 金融理论基础

- **有效市场与信息扩散**：在 semi-strong 形式下，价格应反映公开信息；实务中新闻到达与解读存在**滞后**与**偏误**，文本情绪可捕捉短期定价偏差。
- **NLP 情绪分析在量化中的位置**：传统词典法（Loughran-McDonald 等）与深度/LLM 法相比，后者对中文财经语境与同义词更灵活，但**可重复性与成本**是权衡点。
- **A 股特殊性**：政策公告、行业文件、媒体标题博眼球；需警惕「标题党」、传闻与**监管词**对模型的干扰；**单一新闻情绪不宜单独作为交易依据**。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **单条新闻输入字段**（兼容）：`新闻标题`/`title`，`新闻内容`/`content`，`发布时间`/`date`。
- **`analyze_sentiment_single` 返回**：`{"score": float, "reason": str}`，`score` 裁剪到 `[-1, 1]`。
- **`analyze_stock_sentiment` 返回**（主要字段）：
  - `symbol`, `name`, `daily_score`, `article_count`, `articles`（含 `title`, `score`, `reason`, `date`）
  - `top_positive`, `top_negative`（最利好/最利空标题）
  - `trend`：`"improving"` / `"declining"` / `"stable"`
  - `shift_alert`：bool
  - `analyzed_at`：ISO 时间
  - 无新闻时：`error: "无新闻数据"`

### 3.2 关键函数

| 函数 | 说明 |
|------|------|
| `_load_news(symbol, days=3)` | 取 `news` 目录下**最近 N 个自然日文件**（按文件名排序后取前 N 个 `*.json`），每个文件可为 list，合并为文章列表（**非严格按自然日去重**） |
| `analyze_sentiment_single(article, stock_name="")` | 拼接标题+内容前 500 字；`MODEL_USAGE.get("sentiment_batch", "qwen3:1.7b")`；`POST {OLLAMA_HOST}/api/chat`，system prompt 要求只输出 JSON；解析时处理 `<think>` 后缀 |
| `analyze_stock_sentiment` | 最多分析 **20 条**；`daily_score` 为**已分析条目的算术平均**；按日期排序后前后半段均值差 >0.2 判 improving，<-0.2 判 declining；`shift_alert`：最近 5 条均与全日均差 >0.5 |
| `generate_sentiment_report` | 无 `sentiment.json` 则先 `analyze_stock_sentiment`；输出 Markdown 表格 |

### 3.3 算法与计算逻辑

- **综合得分**：\(\text{daily\_score} = \frac{1}{n}\sum_{i=1}^{n} s_i\)，\(s_i \in [-1,1]\)。
- **趋势**：有日期且条数 ≥3 时，将**按日期排序**后的分数序列拆半比较均值；差值阈值 **0.2**。
- **Ollama 参数**：`temperature=0.1`, `num_predict=200`, `stream=False`, `think=False`。

---

## 4. 外部依赖与数据源

- **Ollama**：OpenAI 兼容的 `/api/chat`（非 `/api/generate`）。
- **本地文件**：`{symbol}/news/*.json`（上游爬虫或同步任务需预先写入）。
- **无服务端缓存**；结果每次写入 `sentiment.json`。

---

## 5. 配置项与可调参数

| 项 | 默认值/来源 | 说明 |
|----|-------------|------|
| `days` | `_load_news` 默认 3 | 控制读取文件数量（按文件名倒序前 N 个） |
| `MODEL_USAGE["sentiment_batch"]` | 缺省 `qwen3:1.7b` | 可覆盖为其他本地模型 |
| `OLLAMA_HOST` | `config` | 基址，如 `http://127.0.0.1:11434` |
| 分析条数上限 | 20 | 控制 LLM 调用次数 |
| `timeout` | 30s | 单次 HTTP |

---

## 6. 使用示例与工作流

```python
from sentiment import analyze_stock_sentiment, generate_sentiment_report

d = analyze_stock_sentiment("600519", days=3)
md = generate_sentiment_report("600519")
print(md)
```

- **协作**：与 `features.build_features` 无直接 import；与新闻抓取模块配合形成「采→存→评」链路。

---

## 7. 已知限制与改进方向

- `_load_news` 按**文件数**而非严格日历日筛选；跨月边界可能不如预期。
- 基本面/重复新闻未去重；未使用 FinBERT 等轻量专门模型，**成本与延迟**依赖 Ollama。
- JSON 解析依赖模型合规输出，异常时回退 `score=0, reason=分析失败`。
