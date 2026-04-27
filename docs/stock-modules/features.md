# features — 详细功能文档

**文件路径**: `scripts/stock/features.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：对单只股票，从本地 `daily.csv` 加载 OHLCV，经 `technical_analysis.compute_indicators` 得到技术指标，再**派生**收益/动量/波动/均线距离/量能/形态/基本面/日历/中国特色资金/涨跌停与 T+1/情绪代理/「追高惩罚」等列，拼成 **特征矩阵 + 目标变量** `target`、`target_ret`，供监督学习使用。
- **在系统中的角色**：**特征工程中枢**；输出列集合由 `_get_feature_columns` **动态筛选**（按非空比例阈值），故不同股票、不同数据完整度下列数可能不同，但**设计意图**是 55+ 维（在数据齐全时）。
- **上下游关系**：

```
daily.csv --> load_ohlcv --> compute_indicators (technical_analysis)
                                    |
        +---------------------------+---------------------------+
        |        |        |         |        |        |        |
   收益率   动量    波动    均线距离  量     形态    基本面   日历
        |        |        |         |        |        |        |
        +--------+--------+---------+--------+--------+--------+
                                    |
        china_market_data (懒加载) --> 资金流向 / 北向 / 融资情绪
                                    |
                          T+1 / 情绪(mood) / 追高惩罚(penalty)
                                    |
                          _add_target(forward_days, threshold)
                                    |
                          _get_feature_columns() --> FEATURE_COLS 全局
```

---

## 2. 金融理论基础

- **监督学习标签**：`target` 为未来 `forward_days` 日**总收益率**相对阈值的三分类（涨/平/跌），对应投资者「是否达到可交易幅度的方向」；`target_ret` 为连续收益率，用于回归或分析。
- **动量与反转**：短中期收益、RSI/MACD/KDJ 变化刻画**趋势与超买超卖**；A 股短期动量与政策事件可能冲突，需与波动、流动性一起使用。
- **波动与风险**：ATR%、日振幅、20 日年化波动率等与**仓位与止损**相关；布林带宽变化与**挤压突破**叙事相关。
- **均线带与乖离**：价格相对 MA 的偏离在 A 股常被用于**均值回归**与趋势过滤；`ma5_ma20_spread` 等类似「均线开口」。
- **量价**：量比、量变化与**价量确认**；形态比（实体/影线）与**K 线博弈**。
- **基本面**：PE/PB/ROE 等**仅填在最后一行**以避免前视偏差（见代码注释）；反映**估值与质量**截面。
- **聪明钱与北向**：主力资金、北向净流、融资余额变化反映**边际资金**；与 `features` 中中国特色列一致。
- **T+1 与涨跌停**： near_limit、隔夜缺口等刻画**流动性约束与极端价格**下的行为差异。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **输入**：`STOCK_DATA_DIR/{symbol}/daily.csv`；可选 `fundamentals.json`（`valuation`, `financials`）。
- **输出**：`DataFrame` 列包含 `date`、**动态特征列**、`target`（-1/0/1）、`target_ret`（%）。
- **最小行数**：`len(df) >= 120`，否则返回 `None`。

### 3.2 `build_features` 主流程

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `load_ohlcv` / `compute_indicators` | 见 `technical_analysis.py` |
| 2 | `_add_return_features` | 见下表 |
| … | `_add_momentum_features` … `_add_chase_penalty_features` | 见下表 |
| 最后 | `_add_target` | `target_ret = close[t+forward]/close[t]*100-100`；`\|ret\|>threshold` 则 ±1，否则 0 |
| 筛选 | `_get_feature_columns` | 排除原始价量及部分指标名；**数值列** 非空比例 ≥50%（`ff_`/`nb_`/`mood_` 前缀 **≥15%**） |

**参数**：

- `forward_days`（默认 5）：预测 horizon。
- `threshold`（默认 2.0）：涨跌分类阈值（%）。

### 3.3 关键函数（内部）

| 函数 | 作用 |
|------|------|
| `_safe_import_china_data` | 延迟 import `china_market_data`，失败则跳过中国特色列 |
| `_get_feature_columns` | 自动收集特征名到模块级 `FEATURE_COLS` |
| `get_feature_names` | 返回最近一次 `build_features` 的 `FEATURE_COLS` |

### 3.4 算法与计算逻辑（目标变量）

- \( \text{target\_ret}_t = \frac{P_{t+h}}{P_t}\times 100 - 100 \)，\(h=\) `forward_days`。
- `target_t = 1` 若 `target_ret > threshold`；`-1` 若 `< -threshold`；否则 `0`。

---

## 3.5 全量特征说明（设计列 + 金融含义）

以下按模块列举**代码中构造或从 `compute_indicators` 保留**、且可能进入 `FEATURE_COLS` 的列（实际是否入选取决于 `_get_feature_columns` 非空比例）。**技术指标中** `MACD_*`、`STOCH*`、`BBL/BBM/BBU/BBB/BBP_*`、原始 `ma*`、`bb_lower/mid/upper`、`vol_ma*`、`atr_14`、`obv` 等被**显式排除**，但由它们**派生**的列可保留。

#### A. 来自 `technical_analysis` 且通常保留的指标列

| 列名 | 金融含义（简要） |
|------|------------------|
| `rsi_14` | 14 日相对强弱，0–100，超买超卖 |
| `kdj_k`, `kdj_d`, `kdj_j` | 随机指标系，J 线更敏感 |
| `bb_width` | 布林带宽度，波动扩张/收缩 |
| `bb_pct` | 价格在带内位置（%B） |
| `amount` / `turnover` / `amplitude` | 若 CSV 存在且通过比例检验，可为**流动性/换手/振幅**截面（非本文件构造，来自源数据） |

#### B. 收益率 `_add_return_features`

| 列名 | 公式/逻辑 | 含义 |
|------|-----------|------|
| `ret_1d` … `ret_20d` | `close.pct_change(n)*100` | n 日简单收益率% |
| `gap` | `(open/prev_close-1)*100` | 开盘跳空% |
| `pct_change` | 若原数据无则 `close` 一日涨跌% | 日涨跌幅 |

#### C. 动量 `_add_momentum_features`

| 列名 | 含义 |
|------|------|
| `rsi_delta` | `rsi_14` 日差 |
| `rsi_5d_delta` | `rsi_14` 5 日差 |
| `macd_hist_delta` | MACD 柱（首列匹配 `MACDh_*`）日差 |
| `macd_hist_sign_change` | 柱正负切换的绝对差分（0/1 跳变） |
| `kdj_j_delta` | J 线日变化 |

#### D. 波动 `_add_volatility_features`

| 列名 | 含义 |
|------|------|
| `atr_pct` | `atr_14/close*100`，ATR 占价比 |
| `daily_range_pct` | `(high-low)/close*100` 实体日振幅 |
| `range_5d_avg` | 日振幅 5 日均 |
| `bb_width_delta` | 布林带宽日差 |
| `volatility_20d` | 日收益滚动 20 标准差×√252×100，**年化波动率尺度** |

#### E. 均线距离 `_add_ma_distance_features`

| 列名 | 含义 |
|------|------|
| `dist_ma5` … `dist_ma60` | `(close-ma)/ma*100` 乖离率% |
| `ma5_ma20_spread` | 短期与中期均线相对位置 |
| `ma10_ma60_spread` | 中短期与中长期相对位置 |

#### F. 成交量 `_add_volume_features`

| 列名 | 含义 |
|------|------|
| `vol_change_1d`, `vol_change_5d` | 成交量 1/5 日变化率% |
| `vol_ratio_20` | `volume/vol_ma20`，量比 |

#### G. 形态 `_add_pattern_features`

| 列名 | 含义 |
|------|------|
| `body_ratio` | 实体/全日范围 |
| `upper_shadow_ratio` | 上影线占比 |
| `lower_shadow_ratio` | 下影线占比 |
| `is_bullish` | 收盘>开盘 |
| `bullish_streak` | 连续阳线根数（按日循环写入） |

#### H. 基本面 `_add_fundamental_features`（仅最后一行非空）

| 列名 | 来源键 | 含义 |
|------|--------|------|
| `feat_pe` | `valuation.pe_dynamic` | 动态 PE |
| `feat_pb` | `valuation.pb` | 市净率 |
| `feat_roe` | `financials.roe` | 净资产收益率 |
| `feat_debt_ratio` | `financials.debt_ratio` | 资产负债率 |
| `feat_profit_yoy` | `financials.profit_yoy` | 利润同比类指标（以源数据为准） |

#### I. 日历 `_add_calendar_features`

| 列名 | 含义 |
|------|------|
| `day_of_week` | 0=周一 … 6=周日 |
| `month` | 1–12（**季节/季末效应**代理） |

#### J. 个股资金流向 `_add_fund_flow_features`（前缀 `ff_`）

需 `china_market_data.fetch_stock_fund_flow` 成功且有 `日期` 列。

| 列名 | 含义 |
|------|------|
| `ff_main_net_3d` | 主力净流入 3 日滚动和（列名动态匹配「主力…净额」） |
| `ff_main_net_10d` | 10 日滚动和 |
| `ff_main_pct_3d` | 主力净占比 3 日滚动和 |
| `ff_super_large_ratio` | 超大单净额滚动 5 日 / 主力净额绝对 5 日和 |
| `ff_price_diverge_5d` | 主力净额 5 日均**分位** 与 `ret_5d` 分位之差（价资背离） |

#### K. 北向 `_add_northbound_features`（前缀 `nb_`）

需 `fetch_northbound`；与行情行**尾部对齐**最近 n 行。

| 列名 | 含义 |
|------|------|
| `nb_net_1d` | 当日北向净买额（与 A 股日对齐的尾部序列） |
| `nb_net_5d` | 5 日累计净买 |
| `nb_momentum` | 北向 5 日均 / 20 日均 |
| `nb_consecutive` | 连续净买为正的天数（负为卖出 streak） |

#### L. T+1 与涨跌停代理 `_add_t1_features`

| 列名 | 含义 |
|------|------|
| `near_limit_up` | 日涨跌幅 >9%（**近似主板的板**，未按 ST/创业板分档） |
| `near_limit_down` | 日涨跌幅 <-9% |
| `gap_up_pct` | 开盘相对昨收缺口% |
| `overnight_risk` | `(昨高-昨收)/昨收*100`，隔夜上影风险代理 |

#### M. 市场情绪代理 `_add_market_mood_features`（前缀 `mood_`）

| 列名 | 来源 | 含义 |
|------|------|------|
| `mood_margin_chg_5d` | `margin_sentiment(window=5)[balance_change_pct]` | 全市场融资余额 **5 日变化%**（仅最后一行） |
| `mood_north_strength` | `northbound_momentum()[momentum]` | 北向短长动量比（仅最后一行） |

#### N. 追高惩罚 `_add_chase_penalty_features`

| 列名 | 含义 |
|------|------|
| `penalty_consec_up` | 连续 **日收益>0** 天数 streak |
| `penalty_dist_ma20_pct` | 收盘相对 ma20 乖离% |
| `penalty_rsi_with_outflow` | `RSI>70` 且 `ff_main_net_3d<0` 记 1 |
| `penalty_volume_diverge` | 3 日均价涨而量趋势 <-5% 记 1 |

---

## 4. 外部依赖与数据源

- **库**：`numpy`、`pandas`；`technical_analysis`、`config`；可选 `china_market_data`。
- **文件**：`daily.csv`、`fundamentals.json`；资金流向与北向来自 **akshare（经 china_market_data 缓存）**。

---

## 5. 配置项与可调参数

| 项 | 默认值 | 说明 |
|----|--------|------|
| `forward_days` | 5 | 预测 horizon |
| `threshold` | 2.0 | 三分类阈值（%） |
| 特征非空阈值 | 一般 0.5；`ff_`/`nb_`/`mood_` 0.15 | 适应中国数据**仅近期有值** |
| `FEATURE_COLS` | 模块全局 | 最后一次 `build_features` 结果 |

---

## 6. 使用示例与工作流

```python
from features import build_features, get_feature_names

df = build_features("600519", forward_days=5, threshold=2.0)
cols = get_feature_names()
```

- **与模型训练**：通常对 `df` 做时间切分，注意**基本面列仅尾部有值**时对训练集的影响。

---

## 7. 已知限制与改进方向

- **前视**：`fundamentals.json` 若含未来修正值，仍仅点在最末行，但**非历史 T 时点真值**的系统性缺失无法由本模块解决。
- **北向/资金流对齐**：北向与个股日频**按尾部 n 行硬对齐**，假日错配时可能偏差。
- **涨跌停阈值 9%**：未区分 20% 板、ST 5% 板。
- **目标变量**：未扣交易成本、滑点与涨跌停不可成交性。
