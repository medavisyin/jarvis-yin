# AI 右侧交易扫描器 (right_side_scanner) — 详细功能文档

**文件路径**: `scripts/stock/right_side_scanner.py`
**最后更新**: 2026-07-01

---

## 1. 模块概述

- **核心职责**: 对全市场 A 股执行**右侧交易**导向的三层漏斗扫描，输出"主力资金由流出转为持续净流入 + 趋势/突破确认"的右侧入场推荐。与 `scanner`（左侧/抄底吸筹）互补。
- **设计哲学**: **确认后跟进**——不抄底，等待主力资金反转与趋势确认后再入场；**无信号即不入场**，0 推荐是正常且负责任的结果。
- **系统角色**: Stock 子系统的**右侧全市场入口**；结果写入 `STOCK_REPORTS_ROOT/data/right_side_scan/`（JSON）与 `STOCK_REPORTS_ROOT/right_side_scan_reports/`（Markdown），可选索引到 RAG。
- **上下游关系**
  - **上游**: akshare / 东财直连 / 新浪分页三重兜底的全市场行情；`china_market_data.stock_fund_flow_signals`（主力资金）；`fetch_market_data.fetch_daily_ohlcv` + `technical_analysis`（K 线与均线）；`scan_cache`（与左侧共享 enrichment 缓存）；`config.call_deepseek`。
  - **本模块**: Layer1 活跃度快筛 → Layer2 资金反转 + 技术确认 → Layer3 DeepSeek 右侧判断 → 落盘与 RAG。
  - **下游**: 前端轮询 `get_right_side_scan_status`；统一扫描器 `unified_scanner` 编排调用；用户阅读 `right_side_scan_report_{date}.md`。

```
[全市场行情] → Layer1 活跃流动性快筛(~5000 → ~60)
    → Layer2 资金反转(10日流出→3日转正且强度达标) + 技术确认(MA5/MA20/RSI/量比)
       (fund_reversal=True 硬过滤，否则不进 Layer3)
    → Layer3 DeepSeek 右侧入场判断 → JSON/MD/RAG
```

---

## 2. 金融理论基础

- **右侧交易 vs 左侧交易**: 右侧 = 趋势确认后跟进，核心是"不预测底，等反转证据"。本模块的反转证据 = 主力资金行为 + 价格趋势。
- **主力资金反转**: 股票前期被持续卖出（10 日主力净流出），近期大资金态度转变（近 3 日持续净流入且回流力度 ≥3%），预示趋势可能反转向上。
- **趋势确认**: 价格站上 MA5（短期转强）、逼近或突破 MA20（中期趋势反转）、放量（资金真实参与，非对倒）。单纯资金流入但价格未响应视为假信号。
- **A 股特殊性**: T+1 制度下追高锁仓风险大，故 Layer1 限制涨幅 ≤ +7%（排除涨停板追高）；允许温和上行（右侧追高），但拒绝涨停板与大跌股。
- **风控铁律**: 右侧交易最忌死扛，每只推荐必带严格止损 + 目标价 + 持有周期，跌破止损即走。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **扫描状态** (`_scan_status`，持久化于 `sys._rs_scan_status` 以规避 `_with_stock_imports` 模块重导入): 含 `status`（`running`/`completed`/`failed`/`idle`/`stopped`）、`progress`、`step`、`started_at`、`elapsed_ms`、`error`、`results_count`。
- **扫描线程** (`sys._rs_scan_thread`)、**停止事件** (`sys._rs_stop_event`) 均挂 `sys` 以跨请求保持。
- **Layer1 候选**: `symbol`, `name`, `price`, `change_pct`, `turnover_rate`, `amount`, `market_cap`, `pe`。
- **Layer2 enriched 单只**: 在候选上 `update` 加入 `tech_score`, `ff_score`, `ff_signals`, `fund_reversal`(bool), `price_above_ma5`, `near_ma20`, `ma20`, `rsi`, `volume_ratio`, `composite_score`。
- **Layer3 输出**: `final_score`, `reasoning`, `risk`, `buy_low`/`buy_high`, `stop_loss`, `target_price`, `strategy`, `verdict`(`买入`/`不买入`), `judged_by`(`deepseek`/`local`)。
- **结果 JSON**: `{scan_type, date, started_at, ended_at, picks[], all_candidates_count, message}`。

### 3.2 关键函数/类

| 函数 | 作用 |
|------|------|
| `start_right_side_scan(use_deepseek=True, market_df=None)` | 启动守护线程执行 `_run_rs_scan_thread`；状态挂 `sys`。`market_df` 由统一扫描器透传共享行情，非空时 Layer1 跳过网络抓取。 |
| `stop_right_side_scan()` | 置 `sys._rs_stop_event`。 |
| `get_right_side_scan_status()` | 返回 `sys._rs_scan_status` 副本 + 线程存活标记。 |
| `get_latest_right_side_result()` / `get_right_side_result_by_date(date)` / `list_right_side_scan_dates()` | 读结果与历史。 |
| `set_shared_market_df(df)` / `clear_shared_market_df()` | 旧式模块级全局注入/清除共享 DataFrame；**统一扫描路径已改用 `market_df` 参数透传**，这两个函数仅留作独立启动场景兜底。 |
| `_run_rs_scan_thread(use_deepseek, market_df=None)` | 线程入口，把 `market_df` 直接转发给 `_run_rs_scan_inner`（不再读模块级 `_shared_market_df`）。 |
| `_run_rs_scan_inner(use_deepseek, market_df=None)` | 主逻辑：Layer1 → Layer2 → Layer3 → 落盘。 |
| `analyze_single(stock_dict)` | Layer2 单只分析：技术面 + 资金反转判定 + 复合得分。 |
| `_build_rs_prompt` / `_parse_rs_json` / `_call_local_rs_judge` | Layer3 DeepSeek prompt 构造 / JSON 解析 / 本地 LLM 兜底。 |
| `_save_rs_results` / `_save_results_empty` | 写结果 JSON + Markdown 报告。 |
| `_generate_rs_markdown_report` / `_index_rs_report_to_rag` | 报告生成 / RAG 索引。 |
| `_fetch_market_eastmoney_direct` / `_fetch_market_sina_pagination` | 行情兜底数据源。 |

**重要常量**: `LAYER2_CAP=60`, `REVERSAL_3D_NET_MIN=0.0`, `REVERSAL_3D_PCT_MIN=3.0`, `REVERSAL_10D_NET_MAX=0.0`。

### 3.3 算法与计算逻辑

**Layer1 — 活跃流动性快筛**
- 排除：名称含 `ST`/`退`；代码非 `60/00/30` 开头。
- 价格 ∈ [3, 100]；涨跌幅 ∈ [-1, +7]（允许温和上行，排除涨停板与大跌）。
- 换手率 ≥ 1.5%；成交额 ≥ 3000 万。
- **总市值 20 亿~500 亿**：⚠️ 单位归一化——akshare `总市值` 为【万元】、东财直连可能为【元】，过滤前 `if _mcap.max() < 1e10: _mcap *= 1e4` 归一化到元，再 `between(2e9, 50e9)`（2026-07-01 修复，旧版万元单位下此条件把所有股票筛掉）。
- 按 `换手率 × 成交额` 降序取前 `LAYER2_CAP` 只。

**Layer2 — 资金反转 + 技术确认**
- **技术面**（`fetch_daily_ohlcv` + `load_ohlcv` + `compute_indicators`，命中 `scan_cache` 即复用）:
  - 价格 > MA5 → `price_above_ma5=True`, tech_score +15
  - 价格 > MA20 → +15；逼近 MA20 (±3%) → +8, `near_ma20=True`
  - MA5 > MA20（多头排列）→ +10
  - RSI ∈ [50,70] → +10；RSI > 80 → -10（超买预警）
  - 量比 ≥ 1.5 → +10
- **资金面**（`stock_fund_flow_signals`，命中 `scan_cache` 即复用）:
  - `reversal_ok = (main_net_10d <= 0) and (main_net_3d >= 0) and (main_pct_3d >= 3.0)`
  - 即：前期 10 日净流出 + 近 3 日转正 + 3 日净占比 ≥ +3%
- **复合得分**: `composite = ff_score*0.50 + tech_score*0.35 + (tr_score+vr_score)/2*0.15`；`reversal_ok and price_above_ma5` 时 +5 bonus。
- **硬过滤**: 仅 `fund_reversal=True` 的进入 Layer3。`Layer 2: 资金反转成立 X / Y 只` 日志可见通过率。

**Layer3 — DeepSeek 右侧判断**
- DeepSeek（`call_deepseek`，`reasoning_effort="medium"`）用右侧专属 system prompt：允许追高突破，但要求严格止损 + 目标价 + 持有周期。
- 解析 JSON verdict；失败降级本地 LLM（`_call_local_rs_judge`）。
- `verdict="买入"` 且得分达标 → 入选 picks。

**落盘**: `_save_rs_results` 写 `right_side_scan_{date}.json` + `right_side_scan_report_{date}.md` + RAG 索引；无候选时 `_save_results_empty` 写空结果。

### 3.4 与左侧 scanner 的关键差异

| 维度 | 左侧 scanner | 右侧 right_side_scanner |
|------|--------------|------------------------|
| 入场时机 | 下跌/回调中抄底 | 趋势确认后跟进 |
| Layer1 偏好 | 低 PE、回调、未超买 | 活跃、温和上行、流动性好 |
| 资金信号 | 布局期/悄悄吸筹（资金进、价格没涨） | 资金由出转进（10日流出→3日转正） |
| 技术要求 | 不追高 | 站上 MA5、逼近/突破 MA20、放量 |
| Layer2 主路径 | 截面 XGBoost 排序 | 资金反转硬过滤 + 复合得分 |
| 持有周期 | 2 周~3 个月 | 2 周~2-3 个月 |
| 风控 | 买入区间 | 严格止损 + 目标价（铁律） |

---

## 4. 外部依赖与数据源

- **库**: `akshare`, `pandas`, `requests`, `concurrent.futures`。
- **项目内模块**: `china_market_data`（资金流向）、`fetch_market_data`（OHLCV）、`technical_analysis`（指标）、`scan_cache`（共享缓存）、`config`（DeepSeek/代理/路径）。
- **网络**: 东财/新浪行情；Ollama `OLLAMA_HOST`；DeepSeek API。
- **RAG 索引失败**仅打日志，不阻断。

---

## 5. 配置项与可调参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LAYER2_CAP` | 60 | Layer1 进入 Layer2 上限 |
| `REVERSAL_3D_NET_MIN` | 0.0 | 3 日主力净流入下限（必须为正） |
| `REVERSAL_3D_PCT_MIN` | 3.0 | 3 日主力净占比下限（%） |
| `REVERSAL_10D_NET_MAX` | 0.0 | 10 日主力净流入上限（必须曾为负） |
| `start_right_side_scan(use_deepseek)` | True | 是否用 DeepSeek 判断 |

**调优建议**: 放宽 `REVERSAL_3D_PCT_MIN` 到 2.0 可增加候选但降低信号强度；牛市可放宽，震荡市保持严格。

---

## 6. 使用示例

```python
from right_side_scanner import start_right_side_scan, get_right_side_scan_status
start_right_side_scan(use_deepseek=True)
# 轮询 get_right_side_scan_status() 至 status == "completed"
```

统一扫描器会自动调用本模块（**通过 `market_df` 参数透传共享行情** + 共享 enrichment 缓存），无需单独启动。

---

## 7. 已知限制与改进方向

- 右侧条件严格，多数交易日 0 推荐——**这是设计如此**，非 bug。
- 资金流向数据依赖 `china_market_data` 抓取质量；偶发空响应时该股票反转判定为 False。
- Layer3 DeepSeek 偶发 JSON 格式问题（未转义引号）→ 降级本地 LLM。
- 改进: 引入成交量突破量化阈值、板块联动确认、止损位基于 ATR 动态计算。
