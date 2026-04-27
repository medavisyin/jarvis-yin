# A 股回测引擎 — 详细功能文档

**文件路径**: `scripts/stock/backtest_engine.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 在 **日频 OHLCV** 上，按给定 **策略信号序列** 模拟单标的 **开平仓、现金、权益曲线**，并施加 **A 股常见交易约束**（T+1 可卖、涨跌停不成交、手续费、滑点、仓位上限的 **部分** 实现）与 **绩效指标**（总收益、年化、夏普、最大回撤、胜率、盈亏比、平均持仓日等）。  
- **系统角色**: 为 **择时/均线** 等策略提供可重复的 **历史压力测试**；`strategy="timing"` 时与 `model_timing` 产出的 `timing` 模型深度集成。  
- **上下游关系**:
  - **上游**: `technical_analysis.load_ohlcv`、`compute_indicators`；`strategy=timing` 时 `build_features` + 加载 `{STOCK_REPORTS_ROOT}/models/{symbol}/timing/buy_*.json` 等。  
  - **下游**: 结果 JSON 存 `STOCK_REPORTS_ROOT/backtest/{symbol}_{strategy}_{date}.json`；`load_latest_backtest` 读取最新文件。

**依赖关系（文字）**:  
`load_ohlcv` → 指标计算 → 生成 `signals`（同长度 `ohlcv` 索引）→ `_simulate` → `BacktestResult` → 落盘。

---

## 2. 金融理论基础

- **回测与可信性**: 回测是 **已发生信息** 下的反事实执行，**不能** 代表未来；需防 **前视、幸存者、过拟合参数**。本引擎在 **信号侧** 使用与训练时相同的特征/模型 **逐日** 前推（在 timing 实现内），在 **执行侧** 用 T+1、涨跌停、成本等贴近 A 股 **现货 T+1** 的简化规则。  
- **T+1（当日买入次日可卖）**: 法规上限制 **卖出时点**，本实现用 `Position.can_sell` 在 **买入后下一交易日** 才允许卖出类成交。  
- **涨跌停无法买卖**: 以 **前收** 的涨跌幅与 **9.5%** 阈值比较（见下技术节），**涨停不买、跌停不卖**（简化，未分板块）。  
- **成本与摩擦**: 佣金、印花税、滑点使 **可交易的边际 alpha** 被侵蚀；A 股 **卖出** 才征收 **千一印花税** 为常见券商口径。  
- **绩效指标**: 夏普用 **日收益序列** 年化；最大回撤为 **历史权益峰值回撤**；胜率/盈亏比基于 **已平仓** 的卖出腿（不含强行期末清仓若被单独处理——见实现）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`Position`**: `symbol`, `shares`（**整百股**）, `cost_price`, `entry_date`, `can_sell`（T+1 标志）。  
- **`Trade`**: `date`, `symbol`, `action`, `price`, `shares`, `cost`（**费用**）, `pnl`, `reason`。  
- **`BacktestResult`**: 摘要指标 + `equity_curve`（`date, equity, cash, position_value`）+ `trades` + `metrics` 扩展。  
- **`signals`**: `pd.Series`, 与 `ohlcv` 索引对齐，取值 **0** 无操作、**1** 买意图、**-1** 卖意图。

### 3.2 关键函数/类

| 符号 | 作用 |
|------|------|
| `_apply_slippage` | 买：`price*(1+SLIPPAGE)`；卖：`price*(1-SLIPPAGE)`。 |
| `_calc_commission` | 买卖佣金率各 **万 2.5**，**每边最低 5 元**；**卖** 另加 **千 1 印花税**（基于成交金额）。 |
| `_is_limit_up` / `_is_limit_down` | `change_pct` 为 **相对前收 %**；`>= 0.095*100=9.5%` 视为涨停不可买；`<= -9.5%` 为跌停不可卖。 |
| `run_backtest` | 数据过滤 → 选策略生成 `signals` → `_simulate` → `_save_backtest`。 |
| `_generate_timing_signals` | 加载择时 `buy/exit` 模型，对 `feat_df` 与 `ohlcv` 按 **日期** 对齐；**仅当** 买=1 且 退=0 时 `signals[i]=1`；**若 exit=1** 而 **未** 形成买=1&退=0，则 `signals[i]=-1`（**仅与 exit 有关的分支**）。买模型缺失则 **回退** `_generate_ma_signals`。 |
| `_generate_ma_signals` | **MA5 上穿/下穿 MA20** 的交叉信号。 |
| `_simulate` | 主状态机，处理 **pending 订单、T+1、涨跌停、仓位**。 |
| `_compute_metrics` | 由权益曲线和 trades 算夏普、回撤、胜率、 profit factor、平均持仓。 |
| `_empty_result` / `load_latest_backtest` | 空结果与读最新回测。 |

- **`_generate_timing_signals` 中 exit 的语义**（与 `predict_timing` **不同**）: 回测里当 `exit_preds[idx]==1` 且 **非** (买1且退0) 时直接给 **-1**（倾向减仓/回避），而不仅是「买0退1=回避」；属于 **为模拟持仓退出** 而设的 **更激进** 的映射。

### 3.3 算法与执行逻辑（核心循环）

- **日序**: 对 `i` 从 `0` 到 `len-1`：  
  1. `change_pct = (close[i]-prev_close[i])/prev_close[i]*100`（`prev_close` 为 shift 1 的收盘）。  
  2. 若已有 **持仓** 且 `not can_sell`，在 **本日循环开头** 将 `can_sell=True`（表示 **自本日起** 可卖，符合 T+1）。  
  3. 处理 **昨日挂起的** `pending_buy` / `pending_sell`：  
     - 买：若前一日信号触发了 `pending_buy` 且当前无仓，**当日**若 **非涨停**；以 **开盘价+滑点** 为买价；`max_invest = cash * MAX_TOTAL_POSITION`（**0.8**），股数 `floor(max_invest/price/100)*100`；检查现金足够则建仓，`can_sell=False`。  
     - 卖：若 `pending_sell` 且 **可卖** 且 **非跌停**；以 **开盘价+滑点** 卖出。  
  4. 再根据 **当日** `signal` 更新 `pending_buy` / `pending_sell`：信号 1 且无仓 → 次日执行买；信号 -1 且有仓 → 次日可卖时执行卖。  
  5. 记录 **当日收盘** 权益（现金 + 持股市值）。

- **T+1 含义**: 买入发生当日 **`can_sell=False`**，**下一日** 循环开始才置真，故 **不能当日卖出**；卖单在 `pending` 后 **至少等到下一日开盘** 尝试（与信号滞后一致）。  
- **涨跌停**: 以 **9.5%** 为界（`LIMIT_UP_THRESHOLD=0.095`），**不区分 10% / 20% 板**，属 **简化**（见限制）。  
- **成本**: `BUY_COMMISSION=SELL_COMMISSION=0.00025`，`STAMP_TAX=0.001`，`SLIPPAGE=0.001`，`MIN_COMMISSION=5.0`。  
- **仓位**: 代码中 **`max_invest = cash * MAX_TOTAL_POSITION`（0.8）**；`MAX_SINGLE_POSITION=0.30` **在 `_simulate` 中未使用**，与模块注释「单只最大30%」**不一致**。

- **回测结束**: 若仍持仓，在 **最后一日收盘价** 强平并记一笔 `reason="回测结束清仓"` 的卖单；**`_compute_metrics` 的胜率/盈亏比** 统计 **排除** `reason="回测结束清仓"` 的卖出。

---

## 4. 外部依赖与数据源

- `numpy`, `pandas`, `config.STOCK_REPORTS_ROOT`。  
- `technical_analysis`；`model_timing` 的 `_build_timing_targets` 被 import 但在所附源码片段中 **回测路径未调用** 该函数（**可能为预留** 或导入副作用）。  
- 择时模型路径: `os.path.join(STOCK_REPORTS_ROOT, "models", symbol, "timing")`，与 `STOCK_MODELS_DIR` 一致。

---

## 5. 配置项与可调参数

| 常量 | 值 | 说明 |
|------|-----|------|
| 佣金 | 各万 2.5 | 与 `MIN_COMMISSION` 联用。 |
| 印花税 | 千 1（仅卖） | |
| 滑点 | 0.1% | 方向性执行劣化。 |
| `MAX_TOTAL_POSITION` | 0.8 | 单次可 **调用现金的 80%** 计买入力。 |
| `MAX_SINGLE_POSITION` | 0.3 | **当前未参与模拟** |
| 涨跌停阈值 | ±9.5% | 对 `change_pct` 比较 |

`run_backtest` 的 `start_date` / `end_date` 可裁剪样本区间。

---

## 6. 使用示例与工作流

```python
from backtest_engine import run_backtest, load_latest_backtest

r = run_backtest("600519", strategy="timing", initial_capital=100_000)
# 或基线: strategy="simple_ma"
latest = load_latest_backtest("600519", "timing")
```

- **前提**: `timing` 回测前需在 `models/.../timing/` 下存在训练好的 `buy_model.json` 等。  
- **择时信号与单日 `predict_timing`** 的 **组合规则不同**（上节），回测更偏 **强制风控出场**（exit=1 常映射为 -1 信号）。

---

## 7. 已知限制与改进方向

- **涨跌停 9.5% 固定**，未随板块/ST 调整。  
- **`MAX_SINGLE_POSITION` 未实现**；**单标的多策略资金分配** 未建。  
- **成交价** 简化为 **开盘±滑点**（买用 open，卖用 open），**未** 用 VWAP/盘口。  
- 择时信号在全历史上用 **与当日对齐的** 特征行，**严格前推** 需自行确认 `build_features` 无未来函数。  
- 夏普 **日频** 基于 **权益一阶差分/前一日权益**；**非对数收益**，短线样本少时波动大。  
- 可改进: 分板块涨跌停、ST、科创板交易规则；成交量冲击；**组合级** 回测与多标的。

---

*本文档以仓库中 **实际代码** 为准；若与文件头 docstring 中「单只 30%」等表述冲突，**以 `_simulate` 实现为准**。*
