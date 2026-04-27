# 长期股票扫描器 (long_term_scanner) — 详细功能文档

**文件路径**: `scripts/stock/long_term_scanner.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 基于**近 14 天**国际新闻、AI/科技简报、黑天鹅预警、热门板块、全球情绪指标，结合**上海金/银基准价（SGE）**的**强制贵金属分析**，经多步 **LLM** 输出 **3–5 个投资主题**与**最多 5 只**长期推荐个股，并生成 Markdown + JSON + RAG 索引。
- **系统角色**: Stock 子系统中的**中长期主题/宏观驱动**分支，与短期全市场 `scanner.py` 互补；强调**宁缺毋滥**（可无推荐）。
- **上下游**  
  - **上游**: 环境变量或默认 `JARVIS_REPORTS_ROOT`（如 `C:/reports/ai`）下的 `YYYY-MM-DD/world-news/world-news-data.json`、`briefing-data.json`；`black_swan_detector`、`hot_sectors`、`market_sentiment`、`akshare` SGE 贵金属、`technical_analysis`、`china_market_data`。  
  - **下游**: `STOCK_REPORTS_ROOT/long_term/` 下 `YYYY-MM-DD.json`、`-report.md`、`history.json`；RAG `item_type=stock_scan_long`。

```
[14日新闻+简报] + [黑天鹅] + [热门板块] + [全球情绪]
       → 贵金属(SGE) + LLM展望
       → LLM 主题 → 主题映射个股 → 基本面过滤 → 逐只 _upside_assessment
       → 取 viable 子集 → LLM 最终精选 ≤5 → 落盘/RAG/历史
```

---

## 2. 金融理论基础

- **主题投资 (Thematic investing)**: 从政策、技术、地缘、大宗等**长期驱动**归纳**1–3 个月**级机会，优于单只股票的短期噪声；本模块由 LLM 显式输出 `time_horizon`、`catalysts`、`risk`、`confidence`。
- **贵金属与宏观对冲**: 黄金常被视为**实际利率/货币信用/避险**的定价对象；白银工业属性更强。**金银比**（代码中约 >80 白银相对便宜、<60 白银偏贵）为经典**相对价值**参考，在 A 股映射到有色、资源品情绪。
- **新闻与预期差**: 世界新闻与 AI 简报代表**信息流**；与 A 股传导通过**政策预期、海外科技映射、避险情绪**等（LLM prompt 要求同时考虑国际与国内政策线）。
- **分位与过热**（`_upside_assessment`）: 使用**个股自身历史**的 60 日收益分位、52 周位置、RSI、量价、资金阶段，体现**「白酒涨 50% 与银行涨 25% 意义不同」**的行业自适应思想。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **信号** `_collect_signals` 返回: `world_news`, `ai_tech_news`（列表项含 `date`, `source_type`, `headline`, `summary` 等）, `black_swan`, `hot_sectors`, `market_sentiment`, `collection_window`。  
- **贵金属** `_analyze_precious_metals`: `gold`/`silver` 为 `_analyze_metal` 结果，另含 `gold_silver_ratio`, `ratio_signal`。  
- **主题** LLM 数组元素: `name`, `logic`, `industries`, `catalysts`, `time_horizon`, `risk`, `confidence` 等（以实际解析为准）。  
- **候选** `_map_themes_to_candidates`: 每只有 `symbol`, `name`, `theme`, `match_reason`, `time_horizon`, `upside`（由 Step5 填充）等。  
- **结果 JSON** `_save_results`: `date`, `meta`, `precious_metals`, `themes`, `picks`。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `start_lt_scan(use_deepseek=False)` | 后台线程 `_run_lt_scan`，设 `_use_deepseek`。 |
| `stop_lt_scan` / `get_lt_status` | 停止与状态。 |
| `get_lt_latest_result` / `get_lt_result_by_date` / `list_lt_scan_dates` / `get_lt_history` | 查询结果与历史。 |
| `_collect_signals` | 滚动 14 日读 JSON，拼新闻；拉黑天鹅/热门/情绪。 |
| `_extract_news_items` | 支持 `categories`/`sections` 与 `list` 两种结构。 |
| `_analyze_precious_metals` / `_analyze_metal` | SGE 数据、RSI、60 日分位、`upside_score`、趋势标签。 |
| `_build_signal_summary` | 拼成 LLM 可读长文本（含贵金属摘要）。 |
| `_llm_theme_analysis` | 主题 JSON 数组。 |
| `_llm_metals_outlook` | 贵金属 LLM JSON（`llm_outlook` 挂到 `metals`）。 |
| `_map_themes_to_candidates` | 主题 `industries` 与热门板块名**子串匹配**，取龙头+成分。 |
| `_filter_candidates` | 全市场 spot 过滤：非 ST、PE 0–200、市值 ≥ 30 亿（`3e9`）。 |
| `_upside_assessment(symbol)` | 五维加权综合 `upside_score` 与结论文本。 |
| `_llm_final_selection` | 对最多 20 只候选文本化，要求空间分等，返回 ≤5。 |
| `_generate_report` / `_save_results` / `_index_report_to_rag` | Markdown、JSON、RAG（chunk 800）。 |

**常量**: `SIGNAL_WINDOW_DAYS=14`, `MAX_PICKS=5`。

### 3.3 算法与计算逻辑

**贵金属单品种 `_analyze_metal`**  
- 需 ≥30 个有效 `date+price` 行；价来源 `spot_golden_benchmark_sge` / `spot_silver_benchmark_sge`，取含「早盘/晚盘」列。  
- 计算：`change_14d_pct`, `change_60d_pct`, 简化 RSI(14), `ma20_deviation_pct`, 52 周（最长 252 行）`position_vs_52w`, `percentile_60d`；`upside_score` 自 100 起按 RSI>70、高位分位、MA 偏离等扣分；**趋势** 过热/上涨/下跌/震荡。  
- **金银比** = 金/银最新价，阈值 80/60 出中文提示。

**行业自适应空间 `_upside_assessment`**  
- 五维: `price_position`（60 日收益在历史滚动分布的分位）, `week_52_position`, `technical`（RSI+可选 MACD 顶背离）, `trend_health`（量比与涨跌）, `fund_flow`（聪明钱阶段）。  
- 权重: 0.25, 0.15, 0.20, 0.20, 0.20 → `upside_score`；结论文本四档。  

**主流程中候选缩减**（`_run_lt_scan_inner`）: 对候选逐一算 `upside` 后，`scored` 为 `upside_score>0`，降序；`min_viable = max(5, len(scored)//2)`，**取前 `min_viable` 只**进最终 LLM（无候选则结束）。这是**动态取半**的启发式，而非固定 Top-K。

**LLM 调用** `_call_llm_json`: DeepSeek 优先（若 `_use_deepseek` 且 key 成功），否则 Ollama，`temperature=0.4`；**JSON 解析**含 markdown 围栏与片段修复。

---

## 4. 外部依赖与数据源

- **akshare**: `spot_golden_benchmark_sge`, `spot_silver_benchmark_sge`, `stock_zh_a_spot_em`（过滤用）。  
- **文件系统**: `JARVIS_REPORTS_ROOT` 或 `C:/reports/ai` 下按日 `world-news-data.json`, `briefing-data.json` — **无文件则该部分为空**，流程仍可跑（但主题质量下降）。  
- **模块**: `black_swan_detector`, `hot_sectors`, `market_sentiment`, `china_market_data`, `technical_analysis`（`load_ohlcv`/`compute_indicators`）, RAG `index_briefing` + `qdrant_client`。  
- **缓存**: `STOCK_CACHE_DIR` 目录保证存在；OHLCV 依赖与短期扫描相同的数据子系统。

---

## 5. 配置项与可调参数

| 项 | 默认 | 说明 |
|----|------|------|
| `SIGNAL_WINDOW_DAYS` | 14 | 新闻回溯天数 |
| `MAX_PICKS` | 5 | 最终只数上限 |
| `_REPORTS_AI_ROOT` | 环境变量或 `C:/reports/ai` | 新闻根路径 |
| `MODEL_USAGE["prediction_reasoning"]` | 依 config | 本地 Ollama 模型 |
| `start_lt_scan(use_deepseek)` | False | 主题/终选/贵金属是否优先 DeepSeek |

**调优**: 增大会新闻与简报覆盖率（跑通 Daily Fetch）；`SIGNAL_WINDOW_DAYS` 平衡时效与信噪；`min_viable` 逻辑对候选多时有较强剪裁 — 若希望更多进入终选，需在代码层调整该策略（当前为固定实现）。

---

## 6. 使用示例与工作流

```python
from long_term_scanner import start_lt_scan, get_lt_status, get_lt_latest_result
start_lt_scan(use_deepseek=True)
# 轮询 get_lt_status() 至 status=="done"
data = get_lt_latest_result()  # 含 themes, precious_metals, picks
```

与 `scanner.start_scan` **并行**时应注意 CPU/网络；共用 `hot_sectors` 与行情接口。

---

## 7. 已知限制与改进方向

- 主题→个股的匹配为**中文字符串子串**与热门板块，**易漏配或误配**；未使用行业码表。  
- 世界新闻/简报**缺失**时主题推断几乎仅靠板块与情绪，**方差大**。  
- `min_viable = max(5, len(scored)//2)` 在 `scored` 很少时仍可能只取 5 只进终选，**小样本**下 LLM 可选项有限。  
- 贵金属 SGE 与**国际金价**存在价源差异，跨市场对冲解读需谨慎。  
- 改进: 行业映射表、Embedding 聚类新闻、可配置 `min_viable`、将北向/利率等**国内因素**也并入 signal_summary（若数据源可用）。
