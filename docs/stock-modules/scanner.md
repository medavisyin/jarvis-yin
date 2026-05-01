# AI 股票扫描器 (scanner) — 详细功能文档

**文件路径**: `scripts/stock/scanner.py`  
**最后更新**: 2026-05-01

---

## 1. 模块概述

- **核心职责**: 对**全市场 A 股**执行「三层漏斗」扫描，输出**可买性（buyability）**导向的短期推荐列表（最多 5 只），而非单纯动量排名。设计哲学（2026-04 改版）：**宁可 0 推荐，也不输出「看起来强但不宜买」的标的**。
- **系统角色**: Stock 子系统的**短期全市场入口**；结果写入 `STOCK_REPORTS_ROOT/scans/`（JSON + Markdown），可选索引到 RAG；与 `hot_sectors`、`technical_analysis`、`fundamental_analysis`、`fetch_market_data`、`china_market_data`、`model_cross_sectional`、`model_xgboost`、`model_price_predictor`、`config.call_deepseek` 等协作。
- **上下游关系（文字描述）**  
  - **上游**: `akshare`/`东方财富备用` 全市场行情；`hot_sectors.get_hot_stock_set`；各分析子模块与 config。  
  - **本模块**: Layer1 → Layer2 **截面 XGBoost 排序**（失败则规则逐批）→ Layer3 LLM → Phase4 综合分析 → Phase5 DeepSeek 补充报告（条件）→ 落盘与 RAG。  
  - **下游**: 前端轮询 `scan_progress.json`；用户阅读 `YYYY-MM-DD-report.md`；`history.json` 供业绩跟踪；`get_latest_result` 等 API。

```
[全市场行情] → Layer1 快筛(~100)
    → Layer2 主路径: 截面 XGBoost rank:pairwise + 行业中性 Top-N
       (失败/空 → 回退 Layer2 规则逐批 enriched, 同原 analyze_batch 逻辑)
    → Layer3 LLM 买入判断(≤30) → [满足 verdict+分数] → Phase4 综合星标
    → Phase5 DeepSeek 报告(仅本地已判股票) → JSON/MD/RAG/history
```

---

## 2. 金融理论基础

- **多因子与筛选漏斗**: 将全市场信息成本控制在可接受范围，采用**宽基流动性/估值门槛**（Layer1）+ **技术+基本面+情绪+资金**（Layer2）+ **主观可买性**（Layer3），符合业界「先横截面再时序、先规则再专家」的框架。
- **动量 vs 可买性**: 单纯涨幅排序在 A 股易诱发**追涨停/次日 T+1 锁损**；本模块在 Layer1/2/3 中显式**惩罚追高价**、**关注回撤买点**与**聪明钱阶段**。
- **价值与 PE 分档**: Layer1 使用 PE 的**分段计分**（8–15、15–25 等），体现「合理区间」而非越低越好（极端低 PE 可能含价值陷阱，代码中对 PE<8 有较低分数）。
- **A 股特殊性**: 文档与 prompt 中强调 **T+1**、**涨跌停附近不追**、**ST 排除**、**成交额/换手率**流动性要求；**主力净流与价量背离**（`china_market_data.stock_fund_flow_signals`）用于识别「吸筹/出货」。
- **行为金融**: 新闻标题关键词加权反映**有限关注**与**负面消息权重更大**（负面系数绝对值更大）的简洁实践。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **进度/状态** (`_load_progress` / `get_scan_status`): 字典，含 `status`（`layer1` / `layer2_in_progress` / `layer3` / `comprehensive` / `deepseek` / `done` / `error` / `stopped`）、`started_at`、`market_total`、`layer1_candidates`、`layer2_results`、`analyzed_count`、`top_picks`、`use_deepseek`、`error` 等。
- **Layer1 单只候选** (`picks` 中元素): `symbol`, `name`, `price`, `change_pct`, `turnover_rate`, `pe`, `amount`, `market_cap`, `score_l1`, `is_hot`。
- **Layer2 在候选上 `update`**  
  - **截面排序主路径**（`model_cross_sectional.cross_sectional_rank` 成功时）: 在 Layer1 字段基础上写入 `score_l2`（XGBoost 截面打分）、`xgb_rank`（全截面合并后的序号）、`industry`（行业标签）、`xgb_alpha`（预测的行业中性 Alpha）、`model_ndcg`（本次训练验证集 NDCG@10，各候选相同方便排查）。`progress` 可含 `layer2_mode`: `xgb_cross_sectional` 或 `rule_fallback`。  
  - **规则回退路径**（逐批 `_layer2_rule_scoring`）: `tech_score`, `fund_score`, `ff_score`, `ff_signals`, `sentiment_score`, `hot_bonus`, `rsi`, `overbought`, `score_l2`, `signals`, 可选 `fund_dimensions`。
- **Layer3 输出**: 增加 `final_score`, `reasoning`, `risk`, `buy_low`/`buy_high`, `strategy`, `verdict`（解析后为 `买入` 或 `观望`）, `judged_by`（`deepseek` / `local` / `fallback`）, 以及 DeepSeek 时的 `deepseek` 子字典。
- **全市场行数据**: `ak.stock_zh_a_spot_em()` 的 DataFrame，列名含 `代码`、`名称`、**分钟级 PE** `市盈率-动态`、**成交额**、**涨跌幅**、**换手率** 等。备用为新浪 `Market_Center.getHQNodeData` 拉平后的同名兼容列。

### 3.2 关键函数/类

| 函数 | 作用 |
|------|------|
| `start_scan(use_deepseek=False)` | 若无线程在跑则启动**守护线程**执行 `_run_scan`；设全局 `_use_deepseek`。 |
| `stop_scan()` | 置 `_stop_event`，请求优雅停止。 |
| `get_scan_status()` | 合并 `scan_progress.json` 与线程是否存活。 |
| `get_latest_result` / `get_result_by_date` / `list_scan_dates` / `get_history` | 读结果与历史。 |
| `update_history_performance` | 按历史推荐补充 1/3/7 日收益。 |
| `_layer1_quick_filter(hot_stocks)` | 全市场快筛，返回 `(picks, market_total)`。 |
| `_layer2_xgb_cross_sectional(candidates, progress)` | **Layer2 主路径**：调用 `model_cross_sectional.cross_sectional_rank` 做截面 rank:pairwise 排序；失败或空结果时回退规则评分。 |
| `_layer2_rule_scoring_all(candidates, progress)` | 规则回退：按 `LAYER2_BATCH` 分批调用 `_layer2_rule_scoring`。 |
| `_layer2_rule_scoring(batch, progress)` | 对一批股票执行原 Layer2 规则打分（技术/基本面/情绪/资金等）并写回进度。原函数名 `_layer2_analyze_batch` 已重命名为此。 |
| `_layer3_llm_rank(candidates)` | 排除 RSI 超买，取 score_l2 Top 30，DeepSeek+本地 混合判断。 |
| `_layer3_deepseek_judge` / `_layer3_local_judge` | 分别调用 `call_deepseek` 与 Ollama `/api/chat`。 |
| `_run_comprehensive_for_picks` | Phase4 星标：技术+ML+价格预测+资金+扫描结论。 |
| `_run_deepseek_for_picks` | Phase5：仅对 **非** `judged_by==deepseek` 的 pick 写长报告。 |
| `_save_results` | 写 JSON、Markdown 报告、RAG 索引。 |

**重要常量**: `TOP_N=5`, `LAYER2_BATCH=20`, `LAYER2_CANDIDATE_CAP=100`, `LAYER3_CAP=30`, `MIN_BUYABILITY_SCORE=60`, `DEEPSEEK_LAYER3_CAP=10`。

### 3.3 算法与计算逻辑

**Layer1 — 基础掩码**  
- 排除：名称含 `ST`；涨跌幅 ∉ [-7,8] 由代码写的是 `between(-7,8)` 且单独 `涨跌幅 < 9.5`；换手率 ≥ 0.5%；成交额 ≥ 3e7；`0 < PE(动态) < 80`（且 Layer1 掩码中要求 PE 与涨跌幅在合理区间 — 与「接近涨停」抑制一致）。

**Layer1 — 分项得分**  
- `pe_score`: 分段 8–15→90, 15–25→80, 25–40→55, 40–60→30, ≥60→10, <8→40（**曲线评价**避免纯低价陷阱）。  
- `chg_score`: 涨幅过大显著降分，**小涨小跌/温和回调**得高分，体现「不追涨停」。  
- `turn_score`: 1–5% 换手 80 分，5–10% 为 60，>10% 为 30，<1% 为 40。  
- **综合** `score_l1 = 0.30*pe + 0.30*chg + 0.20*turn + 0.5*clip(成交额/1e8,0,20)`；热门股 `is_hot` **+3**。  
- 取 `score_l1` 降序前 `LAYER2_CANDIDATE_CAP` 只。

**Layer2 — 主路径（截面 XGBoost，默认）**  
- `_execute_layer2_and_3` 始终先走 `_layer2_xgb_cross_sectional`。在候选集合上拉取历史 K 线、构造截面特征，**当日内训练** `rank:pairwise` XGBoost，目标对齐行业中性化超额收益（Alpha）；预测分写入 `score_l2`，并做**按行业分组、组内取 Top N** 的组合约束，得到 `xgb_rank`、`industry`、`xgb_alpha`、`model_ndcg`。  
- **回退条件**：`model_cross_sectional` 导入异常、`cross_sectional_rank` 抛错或返回空、有效历史样本过少等 → 调用 `_layer2_rule_scoring_all`，并可将 `layer2_mode` 记为 `rule_fallback`。  
- **耗时**: 每轮扫描需在 Layer2 内完成特征构建与模型拟合，**XGBoost 训练延迟**显著高于纯规则批处理；属于运维与排期上的新考量。

**Layer2 — 总分（仅规则回退路径）**  
`total_score = 0.30*ff + 0.25*fund + 0.20*tech + 0.10*sentiment + 0.10*score_l1 + 0.05*_valuation_bonus(pe) + hot_bonus(5/0)`。

**Layer2 — 规则回退分项**  
- **技术** `load_ohlcv` + `compute_indicators` + `evaluate_signals`；**多头/空头信号数**差 ×10+50 限幅得 `tech_score`；RSI>75 记 `overbought` 且 `tech_score` 再减 20。  
- **基本面** `fetch_fundamentals` + `score_fundamentals` → `fund_score` 与 `fund_dimensions`。  
- **情绪** 最近 5 条新闻标题，正负面关键词分级加权，归一化到 [0,100] 得 `sentiment_score`。  
- **资金** 同上 `ff_score`。  
- 上式汇总为规则路径的 `score_l2`。

**Layer3**  
- 剔除 `overbought`；按 `score_l2` 取前 `LAYER3_CAP`。  
- 提示词构建：若候选含 `xgb_rank`，在 Layer3 评分 prompt 中追加 **「截面模型排名」** 块（`xgb_rank`、`industry`、`xgb_alpha`、`model_ndcg`），便于 LLM 结合截面信号与规则/多维得分做可买性判断。  
- 若 `_use_deepseek` 且 `get_deepseek_key()`：前 `DEEPSEEK_LAYER3_CAP` 只走 DeepSeek，其余走本地 LLM。  
- DeepSeek：`call_deepseek(system_prompt, _build_deepseek_scoring_prompt(stock), max_tokens=1200, reasoning_effort="medium")`；解析 JSON。  
- 本地：Ollama `MODEL_USAGE["prediction_reasoning"]`，`temperature=0.3`。  
- **保留条件**（同时满足）: `verdict == "买入"` 且 `final_score >= 60`；再按 `final_score` 取前 5 只。  
- `_parse_llm_score`：去 ``、剥 ```json```、**宽松 JSON**（单引号换双引号等），`verdict` 需含「买入」且不含独字「不」的否定歧义时判买入，否则**观望**。

**Phase4 综合**  
- 多维度 `total_support`/`total_dims` 计星；`comprehensive.conclusion` 中文结论。  
- Phase5: 有 DeepSeek key 且 `use_deepseek` 时，对 **judged_by != deepseek** 的仍调用 `call_deepseek` 写长文报告到 `pick["deepseek"]`。

**报告与持久化**  
- `SCAN_DIR/YYYY-MM-DD.json` 含 `meta`, `top_picks`, `candidates`（前 50）；同日期 `-report.md`（存在截面字段时写入排名、行业、Alpha、NDCG 等摘要）；可选 Qdrant 索引（chunk 400/ overlap 60）。

---

## 4. 外部依赖与数据源

- **库**: `akshare`, `pandas`, `requests`, 标准库 `json/threading/time`；RAG 侧 `qdrant_client`、项目内 `index_briefing`。  
- **项目内模块**: `model_cross_sectional`（Layer2 截面排序：`cross_sectional_rank`，依赖 `numpy`、`xgboost`、`config` 路径与缓存）。  
- **网络**: 东财/新浪全市场行情；Ollama `OLLAMA_HOST`；`config.get_deepseek_key` / `call_deepseek`；`STOCK_PROXY` 代理。  
- **缓存**: `STOCK_CACHE_DIR`；K 线等由 `fetch_market_data.fetch_daily_ohlcv` 等写入。  
- **RAG 索引失败**仅打日志，不阻断主流程。

---

## 5. 配置项与可调参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `TOP_N` | 5 | 最终推荐只数上限 |
| `LAYER2_BATCH` | 20 | Layer2 每批只数，影响单批耗时与 IO |
| `LAYER2_CANDIDATE_CAP` | 100 | Layer1 进入 Layer2 上限 |
| `LAYER3_CAP` | 30 | 进入 LLM 的合并排序上限 |
| `DEEPSEEK_LAYER3_CAP` | 10 | 走 DeepSeek 的只数，控制成本 |
| `MIN_BUYABILITY_SCORE` | 60 | 买入判定最低 `final_score` |
| `start_scan(use_deepseek)` | 默认 False | 是否启用 DeepSeek 双轨策略 |
| `MODEL_USAGE["prediction_reasoning"]` | 如 `qwen3.5:4b` | 本地判断模型 |

**调优建议**: 市场极端低迷时可略降 `MIN_BUYABILITY_SCORE` 或提高 Layer1 的 PE 上界以扩大池子（**慎改**，易引入噪声）；`DEEPSEEK_LAYER3_CAP` 与 API 成本线性相关。

---

## 6. 使用示例与工作流

- **启动**: `from scanner import start_scan, get_scan_status; start_scan(use_deepseek=True)`。  
- **轮询**: `get_scan_status()` 至 `status == "done"`。  
- **续跑**: 若上次 `layer2_in_progress` 有 `layer1_candidates` 与 `layer2_results`，再次启动会从**未分析代码**续跑。  
- **与长期扫描**: 本模块为**日频短期**全市场；`long_term_scanner` 为**主题+贵金属+新闻**长期，两者输出目录与报告类型不同。

---

## 7. 已知限制与改进方向

- Layer1/2 对财务异常、停牌、新股的处理依赖底层数据质量；**无竞价阶段**与**盘中停牌**的细粒度处理。  
- 新闻仅标题关键词，**无 NLP 深度**；情绪分偏噪声。  
- LLM 输出解析在模型乱输出 JSON 时回落到「观望+数值分」。  
- 新浪备用分页 `page>80` 时停止，若接口结构变化需回归测试。  
- Layer2 截面路径每次扫描需 **当日训练 XGBoost**，耗时与 CPU 负载高于纯规则；行业映射依赖东财板块接口，缓存失效或接口变更时可能影响行业中性筛选。  
- 改进: 多周期 PE、Layer2 批大小动态（主要用于规则回退路径）、更稳健的 JSON schema 约束（函数调用 / tool 模式）、截面模型预训练/增量训练以压低在线延迟（设计向）。
