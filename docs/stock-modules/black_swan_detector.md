# 黑天鹅检测器 (black_swan_detector) — 详细功能文档

**文件路径**: `scripts/stock/black_swan_detector.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 从 **Daily Fetch** 产出的 `world-news-data.json` 中**扫头条与摘要、要点**，用**多组正则关键词**（中英）匹配 **7 类风险主题**，为每条主题输出**行业映射**、**严重度**与**样例标题**，并落盘**缓存**；提供 `check_stock_risk` 将**单只股票行业**与**当日(缓存)预警**做粗匹配。  
- **系统角色**: **非预测收益**，而是**尾部风险/极端事件的轻量级预警**；被 `long_term_scanner` 的 Step1、以及**价格预测 PDF** 等作为**环境风险摘要**使用。  
- **上下游**  
  - 上游: `JARVIS_REPORTS_ROOT`（或默认 `C:/reports/ai`）下 `YYYY-MM-DD/world-news/world-news-data.json`；日期默认可回退**昨日**若今日无文件。  
  - 下游: 缓存 `STOCK_REPORTS_ROOT/market_sentiment/black_swan_alerts.json`；`load_cached_alerts` 供**快速读**不重复全量扫描。  

---

## 2. 金融理论基础

- **「黑天鹅」与纳西姆·塔勒布**: 在 **《黑天鹅》** 中，塔勒布强调**高冲击、难预测、事后可解释**的事件；**本模块不预测黑天鹅本身**，而是对**可文本化的灾难性类型**做**近似的模式预警**（战争、金融危机、大流行、制裁等） — 属于**启发式、偏误警（false positive）可能较高**的**早筛**。
- **尾部风险 (Tail risk)**: 对权益组合而言，这些事件常对应**非正态的左尾**；本模块以**行业列表**做粗粒度传导（军工、航空、科技等），不估计**协方差或 CVaR**。  
- **A 股适用性**: 监管、**出口管制/实体清单**、**贸易战关税** 等与 A 股科技/制造产业链高度相关；国内「反垄断、整顿」等也有独立关键词。资产层面用户常关注**黄金/油运**在冲突期的映射 — 行业表中含「黄金」等。  
- **与「真正黑天鹅」的区别**: 媒体已报道的事件多属**灰犀牛或信息噪声**；本工具价值在于**同一段新闻窗口内的重复命中**时提高 **severity**（多标题命中 → high）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`RISK_PATTERNS`**: 键为 `war`, `sanctions`, `pandemic`, `financial_crisis`, `natural_disaster`, `regulation`, `tech_ban`；值含 `keywords`（**正则字符串列表**）, `label`（中文）, `industries`（**受影响行业**关键词列表，用于与股票板块字符串**子串**匹配）。  
- **`scan_world_news` 返回**（概览）:  
  - `date`, `alerts`（每元素: `type`, `label`, `severity`, `match_count`, `matched_headlines` 最多 5, `affected_industries`）, `risk_summary`（`overall_level`, `affected_industries`, `recommendation` 等）, `scanned_at`。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `scan_world_news(date_str=None)` | 默认今日→昨日 尝试读 JSON；全文 `_extract_text` 得 `(headline, body)`；每模式**去重**匹配（同一 headline 同一 pattern 只计一次，实现上为**每条 headline 命中该 pattern 至少一条正即加入**并 break 内层）。 |
| `check_stock_risk(symbol, sector)` | 读**缓存**；`sector` 与 `affected_industries` 双向 **lower 子串**匹配；返回匹配警报列表与 `max_severity`。 |
| `_load_world_news` | 路径拼接与读文件。 |
| `_extract_text` | `categories[].items[]` 取 `title`, `summary`, `points` 拼接。 |
| `_build_risk_summary` | 无警报 → `normal`；`high` 数 ≥2 → `critical`；=1 → `high`；否则看中档数量 → `elevated` / `low`；**recommendation** 为中文固定映射。 |
| `load_cached_alerts` | 读 `black_swan_alerts.json`。 |
| `_save_result` | 写缓存。

**严重度**（单**类型**内）: 匹配**不同** headline 数 ≥3 → `high`，≥2 → `medium`，否则 `low`（**不是**同一条新闻内重复计数）。

### 3.3 算法与计算逻辑

- **双循环**: 对 `(headline, body)` 拼成 `combined`，对每个 `re.search(pat, combined, re.IGNORECASE)`，命中则记录该 `headline` 并**跳出当前 pattern 的内层 keyword 循环**（避免同一条多关键词重复加）。  
- **关键词类型**: 覆盖战争、制裁、大流行、金融系统性、自然灾害、**监管/反垄断**、**芯片/科技禁令**。  
- **局限**: **纯规则**，无法理解讽刺、否定句（"no war" 仍可能因含 `war` 误中 — 视具体英文块而定）。  

---

## 4. 外部依赖与数据源

- **仅标准库** + `config.STOCK_REPORTS_ROOT`；无 HTTP。  
- **数据**: 本地 `world-news-data.json` 结构为 `{"categories": [{"items": [...]}]}` 风格（**与 long_term_scanner 中 world 新闻**同源格式）。  
- **缓存目录**: `STOCK_REPORTS_ROOT/market_sentiment/`。

---

## 5. 配置项与可调参数

- **无运行时 CLI 配置**；`RISK_PATTERNS` 在源码中**静态定义**。  
- 环境: `JARVIS_REPORTS_ROOT` 可覆盖 `C:/reports/ai`。  
- **调优**: 增删**正则**以平衡**漏报/误报**；行业列表可针对用户持仓**细分**（如**锂电**、**光模块**） — 需改代码。  

---

## 6. 使用示例与工作流

```python
from black_swan_detector import scan_world_news, load_cached_alerts, check_stock_risk
result = scan_world_news()          # 全量扫描并更新缓存
cached = load_cached_alerts()
risk = check_stock_risk("000001", "银行")  # 与银行业相关的警报
```

**与长期扫描**: `_collect_signals` 中 `load_cached_alerts() or scan_world_news()` — 优先**快取**，无则**现场扫**。  

---

## 7. 已知限制与改进方向

- **无语义理解**；否定、条件句、低质量标题易误判。  
- `check_stock_risk` 用**板块名字符串**匹配，**板块粒度粗**、中英文混乱时失效。  
- 未与**个股权重**、**事件研究法**的异常收益结合。  
- 改进: 轻量**Embedding 相似度**、NER **实体**（国家/公司）、**只读权威源**白名单、与**期权隐含波动**联动（需新数据源）。  
