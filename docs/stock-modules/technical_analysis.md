# technical_analysis — 详细功能文档

**文件路径**: `scripts/stock/technical_analysis.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：从本地 `daily.csv` 加载**日线数据**，用 **pandas-ta** 计算多种技术指标，结合**经验规则**输出各指标**多空/中性**信号、**综合方向**、**K 线/均线形态**列表，并计算 **Pivot 支撑/阻力** 与**近期高/低**；结果写入 `technical.json`。
- **系统角色**：**技术分析引擎**，依赖 `fetch_market_data` 事先写入的**标准化列名**（中文表头经 `load_ohlcv` 映射为英文列），为上层报告或 LLM 摘要提供**可机器消费的 JSON**。
- **上下游**：

```
[STOCK_DATA_DIR/{symbol}/daily.csv] ── load_ohlcv
         │
         ▼
[compute_indicators: pandas_ta] ── evaluate_signals + detect_patterns
         │
         ▼
[calc_support_resistance]
         │
         ▼
[analyze] ── 写入 technical.json
```

---

## 2. 金融理论基础

- **趋势与均线**：**移动平均**用于平滑价格、识别**趋势**与**支撑阻力**的近似。A 股投资者常参考 **5/10/20/60/120/250 日**均线（约一周至一年交易日量级），**250 日线**在实务中常被视为**年均线**的近似（非严格等于自然年交易日）。
- **动量与振荡类**：**MACD** 属趋势+动量混合；**RSI、KDJ(随机指标)** 用于**超买超卖**与**短线拐点**；在趋势极强的 A 股标的上，**超买可延续**（**钝化**），需结合趋势过滤。
- **波动与成交量**：**布林带**刻画价格相对**均值与标准差**的偏离；**ATR** 为**真波动幅度均值**，与涨跌停制并存时仍具**相对波动**参考；**OBV、成交量均线**用于**价量配合**假说（上涨放量、下跌缩量为多头常见叙述）。
- **形态分析**：**锤子/射击之星/吞没/早晨之星** 等属**经典道氏/价格形态**的简化实现；A 股 K 线受**涨停限制**，极端一字板可能使形态**失真**。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`load_ohlcv` 输出列**（在存在对应中文源列时重命名）：`date, open, high, low, close, volume, amount, pct_change, price_change, turnover, amplitude`；数值列 `to_numeric`。
- **`compute_indicators` 在 `df` 上追加的列**（及 pandas_ta 默认列名，部分会 rename）见下表。

**指标清单（与金融含义、本模块参数、代码行为）**：

| 列名/逻辑 | 金融含义 | 本模块实现参数/公式要点 |
|------------|-----------|------------------------|
| `ma5, ma10, ma20, ma60, ma120, ma250` | 简单移动平均，刻画短中长期趋势与均线多空结构 | `ta.sma(close, length=…)` |
| `MACD_*` / `MACDs_*` / `MACDh_*` | 快慢指数平滑差、信号线、柱=MACD-信号，用于趋势/拐点 | `ta.macd(close, fast=12, slow=26, signal=9)`（Gerald Appel 经典参数） |
| `rsi_14` | 相对强弱，0–100，衡量**涨跌力度**的振荡器 | `ta.rsi(close, length=14)`；Wilder 平滑口径由 pandas_ta 实现 |
| `kdj_k, kdj_d, kdj_j` | 随机指标经平滑；**J=3K-2D** 为 A 股常用**放大灵敏**线 | 先 `ta.stoch(high,low,close,k=9,d=3,smooth_k=3)` 再对列 rename，手算 `kdj_j` |
| `bb_lower, bb_mid, bb_upper, bb_width, bb_pct` | 布林带：中轨多为 SMA(20)、上下轨为 ±2σ，**%B** 为价格在带内位置、**宽度**为波动**挤压**示警 | `ta.bbands(close, length=20, std=2)` |
| `obv` | 能量潮：累积「方向×成交量」的**量流** | `ta.obv(close, volume)` |
| `vol_ma5, vol_ma20` | 成交量均线，用于**放量/缩量**对比 | 对 `volume` 的 SMA |
| `atr_14` | 平均真实波幅，**止损/幅度**的常用尺度 | `ta.atr(h,l,c,14)` |

**`evaluate_signals` 返回结构**（成功）：

- `date`, `price`（`close, change_pct, high, low, volume`）, `signals`（中文字段名到中文信号串）, `indicators`（部分数值回显）, `overall`（`看涨/看跌/偏多/偏空/中性`）, `patterns`（列表）

### 3.2 关键函数/类

| 函数 | 行为摘要 |
|------|-----------|
| `load_ohlcv(symbol)` | 路径 `STOCK_DATA_DIR/{symbol}/daily.csv`；<30 行不拒绝加载，**后续** `compute_indicators` 对 `<30` 会警告并**原样返回** |
| `compute_indicators(df)` | 行数 **< 30 直接 return df 且不计算**（与 docstring 说「需要至少 30 行」一致） |
| `_safe(val)` | 非数/ NaN 变 `None`；否则 `round(float, 4)` |
| `evaluate_signals(df)` | 用**最后两行**做 MACD 柱穿越与 K 线**金叉/死叉**；综合 `bullish`/`bearish` 子串计数，门槛「**差>1**」才标「看涨/看跌」否则「偏…/中性」；见下 |
| `detect_patterns(df)` | 需 **至少 5 行** 才非空；看 **最近 1–3 根** K 与均线、量 |
| `calc_support_resistance(df, lookback=60)` | 以**最后一日** H/L/C 算 pivot**日内**点，不区分盘中；再取近 `lookback` 日极值 |
| `analyze(symbol)` | `load_ohlcv` → `compute_indicators` → `evaluate_signals` → 合并 `support_resistance` 与 `symbol` → 写 `technical.json` |

**`evaluate_signals` 核心规则**（与代码一一对应）：

1. **均线趋势**：若 `close` 与 `ma5` 均与 `ma20` 同侧，则「看涨/看跌」；否则「中性」；`indicators` 回显 `ma5, ma20, ma60`（**不**在 signals 用 ma10/ma120）。
2. **MACD**：取列名以 `MACDh_` 开头的**柱**；若 `hist_now` 与 `hist_prev` 跨 0 则标「金叉(看涨)」「死叉(看跌)」；否则柱>0 为「多头」、<0 为「空头」。
3. **RSI**：>80 严重超买、>70 超买、<20 严重超卖、<30 超卖、否则中性。
4. **KDJ**：J>100 超买、<0 超卖；否则比较 **K 与 D** 与**前日** 判金叉/死叉。
5. **布林带 %B**（`bb_pct`）：>1 突破上轨(超买)、<0 跌破下轨(超卖)；`bb_width<0.05` 标「收窄(即将变盘)」。
6. **成交量比**：`volume / vol_ma20`；>2 显著放量、>1.5 温和放量、<0.5 极度缩量、否则正常。
7. **ATR**：回显 `atr_14` 与 `atr_pct = atr/close*100`。
8. **综合**：`bullish` 数：信号值含「看涨」或「金叉」或**「超卖」**；`bearish`：含「看跌」或「死叉」或**「超买」**；然后比大小并加 1 的裕度。  
   - **重要**：**「超卖」计为对多头有利**、**「超买」计为对空头有利**，属代码实现的**简化的反向指标含义**；与传统「超买应谨慎追多**不完全一致**，解读时需同步阅读分项 `RSI`/`布林带` 原文。

**`detect_patterns` 条件摘要**（代码逻辑）：

- **锤子线**：下影 > 2×实体、上影 < 0.5×实体、当前阳线；且收盘价低于近 5 根**均值**（用 `df[-6:-1]` 的 close 平均）时视为在相对低位，标「看涨/中等」。
- **射击之星**：上影 > 2×实体、下影 < 0.5×实体、阴线；收盘价**高于**近 5 根均值，标「看跌」。
- **十字星**：实体 < 全价区间 10% → 「待确认/弱」。
- **吞没形态**：对前根实体与开收关系的经典不等式，「强」。
- **早晨之星**：三天组合（代码用 `prev2, prev, cur`）阴线→小实体→阳线。
- **MA 金叉(5/20) / 死叉(5/20)**：用**两天**的 `ma5` 与 `ma20` 交叉。
- **放量突破/放量下跌**：`volume > 2*vol_ma20` 且阴阳线。

### 3.3 算法与计算逻辑

- **Pivot 经典公式**（最后一日 H,L,C）：

\[
P = \frac{H+L+C}{3},\quad R1 = 2P - L,\quad S1 = 2P - H,\quad R2 = P + (H-L),\quad S2 = P - (H-L)
\]

  与**日内**枢轴点理论一致，若用于 A 股**日频收盘后**规划，属于**对次日/下一时段**的参考，**非保证价位**。

- **MA、MACD、RSI 等**由 pandas_ta 实现，**与教材手工公式在边界（首批 NaN、平滑法）** 可能略有浮点差。

- **数据不足路径**：`compute_indicators` 在 `<30` 时**不计算指标**；`evaluate_signals` 若 `len<2` 仅返回 `{"error": "数据不足"}`。因此 **30~60 行** 时，若有指标列仍可能**大量 NaN**，部分 `signals` 缺失属预期。

---

## 4. 外部依赖与数据源

- **第三方**：`pandas`, `pandas_ta`。
- **数据**：**仅本地文件**，不直接访问网络与 akshare；输入依赖 `fetch_market_data` 的 CSV 质量。
- **输出**：`STOCK_DATA_DIR/{symbol}/technical.json`，**覆盖写入**。

---

## 5. 配置项与可调参数

- **无环境变量**；`lookback=60` 在 `calc_support_resistance` 的函数参数中可调。
- **指标参数** 全部写死在本文件中（5/10/20/60/120/250、12/26/9、RSI 14、Stoch 9/3/3、Boll 20-2、ATR 14 等）。修改需**直接改代码**。

**调优建议**：A 股**高波动**小盘股可适当缩小布林带 std 或改用**百分比通道**；**震荡市**可缩短 MACD/RSI 参数，但会增**假信号**；修改前应**用同一 `daily.csv` 做前后对比**。

---

## 6. 使用示例与工作流

```python
from technical_analysis import analyze, load_ohlcv, compute_indicators

result = analyze("600519")
# result: signals, indicators, overall, patterns, support_resistance, symbol

df = load_ohlcv("600519")
df2 = compute_indicators(df)  # 行数<30 时与 df 可能相同
```

**工作流**：`update_stock_data` 或 `fetch_daily_ohlcv` 更新 `daily.csv` → 本模块 `analyze` → 下游消费 `technical.json`。

---

## 7. 已知限制与改进方向

- **`compute_indicators` 的 30 行门槛**与 `load_ohlcv` 不统一；刚上市或数据**截短**的标的，可能出现「无指标但仍有 error 以外」的**不一致**需上层处理。
- `evaluate_signals` 的 **综合投票** 与「超卖/超买」字符计数是**非常粗糙**的集成，**不能**作为单独交易依据。
- **MACD/均线列名**依赖 pandas_ta 版本的前缀**约定**；库升级时若列名变化，需**回归测试** `evaluate_signals`。
- 形态检测为**简化的启发式**，未做**成交量确认**的完整规则集；涨停板上影线与实体的**比例**可能异常。

---
