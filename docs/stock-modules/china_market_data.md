# china_market_data — 详细功能文档

**文件路径**: `scripts/stock/china_market_data.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：通过 **akshare** 聚合 A 股特色数据：**北向资金**、**个股/板块/大盘资金流**、**龙虎榜**、**融资融券**、**涨跌停池与市场温度**、**大盘 ETF「国家队」份额监控**、**机构持股与季报持仓细节**等；统一**分目录缓存**，并提供 `fetch_all_china_data()` 一键汇总。
- **在系统中的角色**：  
  - **ML/特征**：供 `features.py` 懒加载（资金流向、北向、融资情绪等）；  
  - **Scanner/UI**：选股层与市场概览；  
  - **知识库**：国家队监控可输出 RAG 用 Markdown（`JARVIS_REPORTS_ROOT`）。
- **上下游关系**：

```
                    akshare (东财/新浪等)
                           |
     +---------------------+---------------------+
     |      |       |      |      |      |     |
  北向   个股流  板块流  龙虎榜  两融  涨跌停  大盘流
     |      |       |      |      |      |     |
     +------+-------+------+------+------+-----+
                           |
              national_team_* (ETF 份额 SSE/SZSE)
                           |
              institution_* / national_team_fund_signals
                           |
              fetch_all_china_data() --> 汇总 dict
                           |
        下游: features.py, 报表, CLI --test
```

---

## 2. 金融理论基础

### 2.1 北向资金（沪深港通）

- **含义**：香港市场投资者经互联互通买卖 A 股的净流量，常被视为**外资情绪与配置意愿**的代理（虽含交易型资金）。
- **理论意义**：跨境资本流动、MSCI 纳入因子、人民币与海外流动性环境均会影响北向；短期净买额与指数有相关性但**非因果**。
- **A 股**：北向披露日频，与「聪明钱」叙事常一起出现；需注意**交易日与数据修订**。

### 2.2 个股/板块/大盘主力资金流

- **含义**：按成交单大小拆分「主力/超大单/大单」等（数据源定义），反映**订单流方向**的统计。
- **理论意义**：与价量分析、订单流不平衡（Order Flow Imbalance）相关；东方财富等口径为**披露级聚合**，非逐笔委托。

### 2.3 龙虎榜（LHB）

- **含义**：涨跌幅、换手率等触及交易所披露规则时，公开买卖前五席位；机构席位净买受关注。
- **理论意义**：极端交易行为、机构参与度的**事件型信号**；亦有「上榜后短期回调」的经验现象（行为金融）。

### 2.4 融资融券

- **含义**：融资余额上升常解读为**杠杆多头**增加；融券为做空规模（本模块 `fetch_margin_data` 侧重**上交所融资融券汇总**，`margin_sentiment` 用融资余额列做变化率）。
- **A 股**：融券规模与券源约束下，**多空结构**解读需结合制度。

### 2.5 涨跌停池与市场温度

- **含义**：涨停家数多往往表示**题材活跃/情绪高**；跌停多表示**恐慌或流动性收缩**。
- **本实现**：`market_temperature` 用涨/跌停数量比与阈值输出「极热/偏热/恐慌/偏冷/正常」。

### 2.6 大盘主力资金流（`fetch_market_fund_flow`）

- **含义**：全市场层面主力净流入时间序列，用于与个股/ETF 监控**对照**。

### 2.7 国家队 / 宽基 ETF 份额

- **市场 narrative**：中央汇金等通过 ETF 增持宽基指数被视为**稳定市场**或长期配置信号；**份额变动**与申购赎回、净值波动、分红再投均有关，**不能简单等同「国家队单向买卖」**。
- **本模块定位**：用**核心宽基+行业 ETF 列表**监控份额水平与**日间/历史间变化**，输出「温和/大幅」增减持语文标签与异常列表；属**启发式监控**而非官方身份识别。

### 2.8 机构持股与社保/QFII/保险持仓

- **含义**：季报披露的长期机构配置；关键词「汇金、社保、保险、证金…」用于**国家队相关机构**粗筛。
- **限制**：披露滞后、仓位为时点数；`stock_report_fund_hold` 系列提供**基金/社保等**分类持仓。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **通用**：大量函数返回 `pd.DataFrame` 或 `dict`；缓存路径见下节「缓存目录」。
- **北向**：`fetch_northbound` 清洗后 CSV 含 `日期`、**`当日成交净买额`**（列名以 ak 实际为准）。
- **国家队监控** `national_team_monitor()`：  
  - `etf_snapshot[]`：`code`, `name`, `index`, `type`（宽基/行业）, `shares`, `shares_yi`（亿份）  
  - `total_broad_shares_yi`, `total_sector_shares_yi`  
  - `signals.broad_total_change`，`signals.anomalies[]`（单只 ETF 变动超 3%）

### 3.2 关键函数与 public API

#### 工具与重试

| 符号 | 说明 |
|------|------|
| `_today_str` | 当前日 `YYYYMMDD` |
| `_cache_fresh(path, max_age_hours)` | 文件存在且**修改时间**在窗口内 |
| `_retry(fn, *args, retries=2, delay=1.5, **kwargs)` | 递增 sleep 重试 |

#### 北向

| 函数 | 签名要点 | 返回值/逻辑 |
|------|----------|-------------|
| `fetch_northbound` | `days=120` | 优先读 `STOCK_CACHE_DIR/.northbound/history_clean.csv`（8h 内）；否则 `ak.stock_hsgt_hist_em(symbol="北向资金")`，删净买额 NaN，写缓存，`tail(days)` |
| `northbound_momentum` | `window_short=5`, `window_long=20` | `net_today`, `net_5d`, `net_20d`, `momentum=短均/长均`, 从**最新向历史**数连续净买天数, `trend` 文本档 |

#### 个股资金流

| 函数 | 说明 |
|------|------|
| `fetch_stock_fund_flow(symbol)` | 缓存 `.fund_flow/{symbol}.csv`；`ak.stock_individual_fund_flow`，市场 `sh/sz` 由代码首位判断 |
| `stock_fund_flow_signals(symbol)` | 汇总 3 日/10 日主力净额、净占比、超大单占比、`accumulation_signal`，并调用 `detect_smart_money_accumulation` |
| `detect_smart_money_accumulation` | 用近 5 日资金与 `stock_zh_a_hist` 近 15 日价；**布局期/拉升期/出货期**等规则 + `accumulation_score` 0–100 |

#### 板块资金流

| 函数 | 说明 |
|------|------|
| `fetch_sector_flow` | `sector_type` 默认「行业资金流」；`period`「今日/5日/10日」；`ak.stock_sector_fund_flow_rank`；缓存 `.sector_flow/{type}_{period}_{date}.json` |
| `sector_rotation_score(sector_name)` | 在「今日」「5日」表里**按名称包含**匹配；`rank_*` 为**排名分位** `1-idx/len`；`momentum=今日分位-5日分位`；`is_hot`：`rank_today>0.7` |
| `get_hot_sectors(top_n)` | 今日表 `name_col` 前 N 个板块名 |

#### 龙虎榜

| 函数 | 说明 |
|------|------|
| `fetch_lhb_institutional` | `ak.stock_lhb_jgzz_sina(symbol=str(recent_days))` |
| `fetch_lhb_detail` | `ak.stock_lhb_jgmx_sina` |
| `stock_lhb_activity(symbol)` | 在机构追踪表中**代码包含**匹配首行，汇总机构买卖额与次数 |

#### 融资融券

| 函数 | 说明 |
|------|------|
| `fetch_margin_data` | `ak.stock_margin_sse`；`sse.csv` 缓存；`start_date` 约为 `now-days*2` 至 `end_date` |
| `margin_sentiment(window=5)` | 融资余额列 `W日` 前与最新比**百分比变化**；分档 `杠杆加速`…`快速去杠杆` |

#### 涨跌停与市场温度

| 函数 | 说明 |
|------|------|
| `fetch_limit_pool(date, direction)` | `ak.stock_zt_pool_em` / `ak.stock_dt_pool_em` |
| `market_temperature` | `ratio=zt/(zt+dt)` 与家数阈值输出 `mood` |

#### 大盘资金流

| `fetch_market_fund_flow(days)` | `ak.stock_market_fund_flow` → `.market_flow/history.csv` |

#### 国家队与 ETF

| 常量 | `CORE_ETF_LIST` 约 16 只，含 510300/510500/510050、创业板/科创/行业等 |
|------|---------------------------------------------------------------------|
| `fetch_etf_shares_sse` | `ak.fund_etf_scale_sse`，失败则**回溯近 5 个工作日**重试；`sse_latest.csv` |
| `fetch_etf_shares_szse` | `ak.fund_etf_scale_szse`；按日 `szse_{date}.csv` |
| `_get_etf_share` | 在 SSE/SZSE DataFrame 中按代码取份额列 |
| `fetch_etf_share_history(etf_code, dates?)` | 多日期调 `fetch_etf_shares_sse`（**注意设计**：`szse_df` 常为空，深交所需依赖后续快照） |
| `national_team_monitor` | 聚合并 ` _detect_share_anomalies`，写 `snapshot_{date}.json`，`_append_history`，`_save_national_team_knowledge` |
| `_detect_share_anomalies` | 与**上一日非今**历史快照比，宽基总份额变幅 → `broad_total_change`；单 ETF \|变化\|>3% 入 `anomalies` |
| `national_team_trend(days=30)` | 历史**宽基总和**首末变化率分档：大规模建仓~大规模撤退 |
| `national_team_backfill_history(days=90)` | 每约 5 日采样、SSE+`fund_scale_daily_szse` 补深交数据、修历史 `history.json` 最多 365 条 |
| `national_team_period_stats` | 1周/1月/3 月 宽基/行业及**每只 ETF** 的区间变动 |
| `fetch_institution_holdings(quarter)` | `ak.stock_institute_hold`；**季度**自动推最近已披露 |
| `national_team_fund_signals` | 近 5 日大盘主力**连续**流入/流出信号 + `fetch_institution_holdings` 里关键词**计数**（非持仓明细行） |
| `national_team_institution_detail` | 对「社保持仓、QFII、保险」`stock_report_fund_hold` 多日期，提取**增仓/减仓/新进** Top 列表与汇总 |

#### 综合

| `fetch_all_china_data` | 顺序执行：北向+signals、板块行数、LHB 行、两融+signals、temperature、market_flow 行数、`national_team_monitor`；附 `errors`、`success_count` |

### 3.3 算法与计算逻辑（择要）

- **北向动量**：短窗均值 / 长窗均值；连续天数从**最新一天向前**数正负 streak。
- **聪明钱布局**：资金强度分（净额、正日数、净占比）+ 近 5 日涨跌幅**横盘**（\(|Δp|<2\%\) 等）综合评分；与价**背离**时倾向「布局期」。
- **板块轮动分位**：`1 - index/total` 为**排名越前越大**的映射。
- **国家队宽基变幅**：相邻快照 `total_broad_shares_yi` 变 **>5%** 为「大幅」档；单 ETF **>3%** 为异常。

---

## 4. 外部依赖与数据源

- **库**：`akshare`、`pandas`。
- **配置**：`STOCK_DATA_DIR`, `STOCK_CACHE_DIR`, `STOCK_REPORTS_ROOT`；国家队知识库路径还读 `JARVIS_REPORTS_ROOT`（缺省 `C:/reports/ai`）下 `knowledge/stock`。
- **缓存子目录**（均在 `STOCK_CACHE_DIR` 下）：  
  `.northbound`, `.fund_flow`, `.sector_flow`, `.lhb`, `.margin`, `.limit_pool`, `.market_flow`, `.national_team`（国家级另有 `history.json`、`inst_detail.json` 等）。

---

## 5. 配置项与可调参数

| 项 | 典型值 | 说明 |
|----|--------|------|
| `_RETRY_DELAY` / `_MAX_RETRIES` | 1.5s / 2 | 全局重试（部分调用覆盖 retries/delay） |
| 各 `max_age_hours` | 6–12、北向8、机构72h | `_cache_fresh` 门控 |
| `CORE_ETF_LIST` | 16 只 | 可增删监控标的 |
| `national_team_backfill` / `days` | 90 | 回填跨度与约 5 日步长 |
| 异常阈值 | 宽基 5%、单 ETF 3% | 可据波动调参 |

---

## 6. 使用示例与工作流

```bash
python china_market_data.py --test
python china_market_data.py --test 600519
```

```python
from china_market_data import fetch_northbound, margin_sentiment, national_team_monitor
nb = fetch_northbound(60)
mg = margin_sentiment(5)
nt = national_team_monitor()
```

- **与 `hot_sectors` 区分**：同仓库另有 `get_hot_sectors`（**资金流排名板块名**），与 `hot_sectors.fetch_hot_sectors`（**概念涨跌幅+成分**）不要混用。

---

## 7. 已知限制与改进方向

- 北向数据**节假日与延迟**导致尾部 NaN 已在清洗中 drop，长度可能变短。
- `fetch_etf_share_history` 多日期循环中深交所 DataFrame 常未填充，**历史深交只 ETF 精度**依赖 `backfill` 与 monitor 的联合。
- 龙虎榜、两融、涨停池**依赖交易日**，非交易日或收盘前可能为空。
- 「国家队」基于 ETF 份额**推断**，**非监管披露的直接账户数据**；研究级用途需交叉验证。
