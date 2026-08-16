# 优质低估扫描器 (quality_value_scanner) — 详细功能文档

**文件路径**: `scripts/stock/quality_value_scanner.py`  
**最后更新**: 2026-08-16

---

## 1. 模块概述

- **核心职责**: 全市场 **同业相对低估** 粗筛（踢 ST、创业板 300/301、非正 PE）→ 仅对 Layer1 入围（**硬上限 100**）拉同花顺年报与分红 → 基本面排雷 → PB-ROE 排序 + 近 5 年 PE 分位 → **一次** DeepSeek 批量终审，输出最多 **5 只**（可为 0），并生成 Markdown + JSON + RAG 索引。
- **系统角色**: Stock 子系统中的**独立价值选股**分支，与左侧/右侧/长期/午盘并列；强调 **6 个月～2 年** 持有口径与**宁缺毋滥**。
- **上下游**  
  - **上游**: 东财 `clist`（`VALUE_CLIST_FIELDS` 含 PE/PB/股息）或 `ak.stock_zh_a_spot_em`；只读 `STOCK_CACHE_DIR/.industry_map.json`；`ak.stock_financial_abstract_ths`；分红经 `eastmoney_throttle`；`valuation.fetch_valuation_history`；`llm_reasoning.build_quality_value_system_prompt` + `config.call_deepseek`。  
  - **下游**: `STOCK_REPORTS_ROOT/quality_value/` 下 `YYYY-MM-DD.json`、`-report.md`；RAG `item_type=stock_scan_quality_value`；PDF `report_type=quality_value`。

```
[全市场快照 PE/PB/股息] + [只读行业缓存]
       → Layer1 同业便宜（先踢创业板）cap 100
       → fetch_fundamentals_for_value（24h 缓存）
       → Layer2 财务门槛 → Layer3 PB-ROE + 5y PE 分位
       → 一次 LLM JSON 数组终审 ≤5 → 落盘/RAG
```

---

## 2. 金融理论基础

- **相对估值 (Relative valuation)**: PE/PB **必须同行业**比较；跨行业直接比 PE 无意义。Layer1 用行业均值，金融股 PB&lt;1 记为低估信号。
- **质量因子**: ROE、利润增长、负债约束（**金融业豁免负债硬门槛**，否则会清空银行）。
- **PB-ROE**: `ROE/PB`，在「同样净资产回报」下偏好更低 PB。
- **历史分位**: 当前 PE 在近 5 年自身分布中的位置；高分位表示相对自己也不便宜。窗口用 `>` 起始日，避免年终边界多算第 6 年。
- **价值陷阱与周期**: 规则层不建模；由独立价值人设 LLM 输出 `cycle` / `trap`。**商誉暴雷不在规则层**。
- **A 股板差异**: 创业板用户不可交易 → `board_filters.is_chinext` 在均值计算前剔除，避免污染同行统计。科创板保留。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **快照行**: `symbol`, `name`, `pe`, `pb`, `div_yield`, `industry`。  
- **Layer1 统计**: `in/out`, `dropped_st`, `dropped_pe`, `dropped_chinext`。  
- **财报缓存 JSON** `STOCK_CACHE_DIR/.quality_value/{symbol}.json`: `fetched_at`, `roe`, `np_cagr_3y`, `debt_ratio`, `nonrecurring_ratio`, `payout_stable`。  
- **结果 JSON**: `date`, `picks`, `stats`, `use_deepseek`, `llm_skipped`。  
- **LLM 元素**: `symbol`, `verdict`, `score`, `cycle`, `trap`, `reason`, `risk`, `strategy`。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `layer1_coarse_filter` | 踢创业板/ST/PE≤0；同业 PE、PB 均低于均值；已知股息 &lt;2.5 踢；`cheapness` 排序后 cap 100。 |
| `layer2_fundamental_filter` | ROE≥10、CAGR≥5；非金融负债&lt;60；金融已知低息踢；扣非 &lt;0.80 踢、None→unknown；`payout_stable is False` 踢。 |
| `layer3_rank_and_cap` | `pb_roe_score = ROE/PB`，每行业最多 2，top 20。 |
| `pe_percentile_in_window` / `apply_pe_percentile_gate` | 本地百分位（**不** import `valuation._percentile_rank`）；未知保留。 |
| `parse_ths_annuals` | 年报 ROE/负债/三年净利润 CAGR；扣非 `%` 当比例，亿/万当金额÷净利润。 |
| `infer_payout_stable` | 近 3 个年度中 ≥2 年现金分红 → True；有 3 年历史但不够 → False；数据不足 → None。 |
| `fetch_fundamentals_for_value` | THS + 分红；24h 按 JSON `fetched_at`；失败字段保持 None。可注入 `ths_fetcher` / `dividend_fetcher`。 |
| `attach_pe_percentile` | 对 Layer3 入围调 `valuation.fetch_valuation_history`。 |
| `parse_value_verdict_list` / `apply_layer4_batch` / `select_final_picks` | 批量 JSON；否决非买入、trap、衰退；按 score 最多 5。 |
| `start_qv_scan` / `stop_qv_scan` / `get_qv_status` | 后台线程挂在 `sys._qv_*`（与长期扫描同一生命周期模式）。 |
| `get_qv_latest_result` / `get_qv_result_by_date` / `list_qv_scan_dates` | 查询。 |

**常量**: `LAYER1_CAP=100`；金融行业关键字 `银行/非银金融/保险/证券/多元金融`。

### 3.3 算法与计算逻辑

**三年 CAGR**: 取最近 3 个年报净利润，`(latest/oldest)**(1/2)-1`（两个间隔年）。利润非正则无法算，保持 None。

**扣非**: 列名含「扣非」；带 `%` → `/100`；带亿/万 → 金额/净利润。

**行业映射**: `attach_industry` **只读缓存**，禁止在本扫描里 `stock_board_industry_cons_em` 全市场重建。缓存未命中 → 空行业 → Layer1 `industry_unknown`（跳过相对均值，仍受股息规则约束）。

**主流程 `_run_qv_scan`**: 快照 → 行业 → Layer1 → 逐只财报 → Layer2 → Layer3 → 分位门 → 可选 `_call_value_llm`（`call_deepseek(system, user)`，不是 messages 列表）。

---

## 4. 外部依赖与数据源

- **东财 clist**: `f9` PE、`f23` PB、`f133`/`f37` 股息。akshare 回退列名「市盈率-动态 / 市净率 / 股息率」。  
- **同花顺**: `ak.stock_financial_abstract_ths(..., indicator="按年度")`。  
- **分红**: `ak.stock_fhps_detail_em`，失败则 `stock_history_dividend_detail`；必须包在 `eastmoney_slot` 内。  
- **估值历史**: `valuation.fetch_valuation_history`（东财 `stock_value_em`，自带缓存）。  
- **板过滤**: `board_filters.is_chinext`（300/301）。  
- **缓存**: `STOCK_CACHE_DIR/.quality_value/` 24h；行业图只读。

---

## 5. 配置项与可调参数

| 项 | 默认 | 说明 |
|----|------|------|
| `LAYER1_CAP` | 100 | Layer2 拉财报上限 |
| Layer2 ROE / CAGR | 10 / 5 | 百分比门槛 |
| 非金融负债 | &lt;60 | 金融跳过 |
| 扣非占比 | ≥0.80 | None 保留 |
| 5y PE 分位 | ≤30 | None 保留 |
| Layer3 | 每行业 2，top 20 | PB-ROE |
| 最终只数 | ≤5 | 含 0 |
| `start_qv_scan(use_deepseek)` | False | 是否一次批量终审 |

**调优**: 放宽 Layer2 会增加 DeepSeek 候选；收紧 Layer1 cap 会减少年报请求。不要为了「每天都有 5 只」而放宽宁缺毋滥。

---

## 6. 使用示例与工作流

```python
from quality_value_scanner import start_qv_scan, get_qv_status, get_qv_latest_result
start_qv_scan(use_deepseek=True)
# 轮询 get_qv_status() 至 status=="done"
data = get_qv_latest_result()  # picks, stats
```

HTTP：`POST /api/stock/quality-value/start`，`GET .../status|result|history`，`POST .../stop`。  
UI：`index.html` `openQualityValueModal`；PDF `exportStockPdf('quality_value','qv')`。

与 `scanner.start_scan` / `start_lt_scan` 并行时注意东财限流（分红路径已走全局 throttle）。

---

## 7. 已知限制与改进方向

- 东财 `f133` 股息字段未在全市场交叉验证；另映射 `f37` 与 akshare「股息率」。  
- 同花顺列名随接口漂移；扣非可能缺失 → unknown。  
- `stock_fhps_detail_em` 列名可能与「年度/现金分红」测试夹具不同，实盘分红经常 unknown。  
- 行业缓存冷启动为空时，相对估值退化。  
- 商誉无规则层；完全依赖 LLM 定性。  
- 首次扫描对最多 100 只拉年报会慢；24h 缓存后会快。  
- 改进: 稳定分红率≥30% 的加严字段、商誉定量（若有可靠源）、行业缓存刷新与本扫描解耦的运维文档。
