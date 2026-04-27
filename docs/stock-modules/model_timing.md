# 择时模型（双 XGBoost 分类）— 详细功能文档

**文件路径**: `scripts/stock/model_timing.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 为单只股票建立 **两个二分类器**  
  1. **买入模型**: 是否在未来 **3 个交易日内** 出现相对 **T+1 开盘价** 超过 **+3%** 的 **最高价空间**；  
  2. **退出模型**: 是否在未来 **5 个交易日内** 相对 **当日收盘** 的 **最大回撤** 达到/超过 **5%**（用未来最低价刻画）。  
  推理时根据 **两模型硬分类结果** 组合为「买入 / 观望偏多 / 回避 / 观望」。
- **系统角色**: **事件型择时**，把连续价格路径压缩为可学习的 **二值标签**；与纯方向或价格点预测形成互补。
- **上下游关系**:
  - **上游**: `features.build_features`、`get_feature_names`；`technical_analysis.load_ohlcv`（补全 OHLC 到特征表）；`china_market_data` 在模块注释中提及（与 A 股数据拉取相关，具体由 `features`/`load_ohlcv` 间接使用）。  
  - **下游**: 模型与指标写入 `{STOCK_MODELS_DIR}/{symbol}/timing/`；`backtest_engine` 的 **timing 策略** 会加载同路径下的 `buy_model.json` / `exit_model.json` / `buy_features.json` 生成逐日信号。  
  - **简图**: `load_ohlcv` + `build_features` → 构造 `buy_target`/`exit_target` → Walk-Forward 训练两模型 → 保存；`predict_timing` 仅依赖 **已存模型 + 当前 `build_features` 末行**。

---

## 2. 金融理论基础

- **「空间」与「风险」解耦**: 买入标签刻画 **上行动量或弹性**（是否出现足够大的相对 T+1 开的冲高）；退出标签刻画 **短期下行深度**（是否跌穿 5% 级回撤）。二者组合对应实务中的 **机会 vs 风险** 框架。  
- **投资动机**: 择时不是预测精确点位，而是 **进出场窗口** 与 **是否参与**；在 A 股 T+1 下，**T+1 开** 作为 buy 的基准价，可理解为「次日能成交后是否仍有肉」的粗糙 proxy。  
- **A 股**: 高波动、跳空与涨跌停会扭曲「未来 3 日高」的可达性；标签仍基于 **历史实现路径**，**极端行情下正样本** 会稀少或 **被涨跌停截断**，需在回测中结合 `backtest_engine` 的 **不可成交** 规则理解。  
- **学术上** 可类比 **双状态预测** 与 **多期限风险度量** 的工程化变体，非标准 CVaR，但 **最大回撤** 与实务风控语言一致。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`_build_timing_targets` 在 `feat_df` 上新增**:
  - `buy_t[i]`: 若 `i+_BUY_HORIZON+1 >= n` 则置 **-1** 后变 **NaN**（无未来）；否则  
    `future_max_high = max(high[i+1 : i+1+3])`, `gain_pct = (future_max_high / open[i+1] - 1) * 100`, `buy_t[i] = 1` 当 `gain_pct >= 3.0` 否则 `0`（**注意**: `t1_open<=0` 时本轮 **不写入 buy** 会保持 0 循环默认，与正常可区分依赖后续有效样本）。  
  - `exit_t[i]`: 以 `close[i]` 为 **入场参考价**，`future_lows = low[i+1 : i+1+5]`，  
    `max_drawdown = (entry_price - min(future_lows)) / entry_price * 100`，`>= 5%` 则 1 否则 0。尾部不足则 -1 → NaN。  
- 最终 `buy_target` / `exit_target` 列与特征对齐；训练时只取 `notna` 子集。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `_model_dir` | `STOCK_MODELS_DIR/symbol/timing/`，`exist_ok` 创建。 |
| `_get_feature_df` | 合并 `ohlcv` 到 `feat_df`，再 `_build_timing_targets`。行数、OHLCV 行数与 `_MIN_DATA_ROWS` 检查。 |
| `_walk_forward_train(X, y, feature_cols, model_type)` | 多轮时序切分，折内中位数插补、**inf→0**；`scale_pos_weight` 按训练集类比设置；在 **多轮中保留 F1 最高** 的那次 `XGBClassifier` 作为 `best_model`；**平均指标** 为各轮 acc/prec/rec/f1 的 **均值**（注意：与 best_model 的筛选指标 **不完全同一口径**）。 |
| `train_timing_model` | 分别对 `buy_target` 与 `exit_target` 调 `_walk_forward_train`，写 `buy_model.json` / `exit_model.json`、`*_features.json`、`*_metrics.json` 与 `train_result.json`。 |
| `predict_timing` | 加载 `buy` 与（若存在）`exit` 模型，用 `build_features` **最后一行**；特征需至少 **70%** 与训练时列一致；缺失与 inf 处理为 `fillna(0)`。信号由 **`predict` 的类标** 组合，**不是** 纯概率阈值。 |
| `predict_batch` | 多标的循环，单票异常不中断。 |

- **`_impute_fold`**: 与分类模块类似，多一步 **将 ±inf 置 0**。

### 3.3 算法与计算逻辑

- **XGBoost 分类器（择时子模型）** 典型参数: `n_estimators=200`, `max_depth=4`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.7`, `reg_alpha=1`, `reg_lambda=2`, `min_child_weight=5`, `scale_pos_weight=...`, `early_stopping_rounds=15`, `eval_metric=logloss`。
- **Walk-Forward 索引**（`r` 从 0 递增）: `test_end = n - r*5`, `test_start = test_end - 5`, `train_end = test_start`, `train_start = max(0, train_end - 400)`；要求 `train_end - train_start >= 50`。
- **组合规则**（`predict_timing`）:
  - 买=1 且 退=0 → **「买入」**  
  - 买=1 且 退=1 → **「观望偏多」**  
  - 买=0 且 退=1 → **「回避」**  
  - 否则 **「观望」**  
- **无 exit 文件时** `exit_pred` 保持 0，主要依赖 buy 支路。  
- **防过拟合**: 时序外推、折内填值、`scale_pos_weight`、L1/L2 与采样；若全部轮次失败，代码尝试在 **全数据** 上拟合一个默认参数的模型（见 `_walk_forward_train` 尾部）。

---

## 4. 外部依赖与数据源

- `numpy`, `pandas`, `xgboost`, `sklearn.metrics`（`accuracy_score` 等，在 `_walk_forward_train` 内 import）。  
- `config.STOCK_DATA_DIR`（`train` 主流程未直接写预测 JSON，**主要落盘在 model 目录**）; `STOCK_MODELS_DIR`。  
- 特征/行情来源同 `features` 与 `technical_analysis`。

---

## 5. 配置项与可调参数

| 常量 | 默认 | 含义 |
|------|------|------|
| `_BUY_THRESHOLD_PCT` | 3.0 | 未来 3 日内高相对 **次日开盘** 的最小 **百分比** 涨幅。 |
| `_EXIT_DRAWDOWN_PCT` | 5.0 | 未来 5 日最大回撤（相对今日收）阈值（百分比）。 |
| `_BUY_HORIZON` / `_EXIT_HORIZON` | 3 / 5 | 向前看的交易日数。 |
| `_TRAIN_WINDOW` / `_TEST_WINDOW` / `_N_WF_ROUNDS` | 400 / 5 / 12 | 与 Walk-Forward 范围相关。 |
| `_MIN_DATA_ROWS` | 200 | 全表、目标有效行等门槛。  

**调优建议**: 提高买入阈值会 **减少正样本**；提高退出阈值会 **更挑剔风险**。二者改变需 **重新训练** 并观察 precision/recall 平衡（代码已记录 F1）。

---

## 6. 使用示例与工作流

```python
# 训练
from model_timing import train_timing_model, predict_timing
train_timing_model("600519")
# 预测
print(predict_timing("600519"))
```

- **回测**: `backtest_engine.run_backtest(..., strategy="timing")` 会 **用当前 checkpoint 的模型** 在 **全历史** `build_features` 上滚动预测，与**单日** `predict_timing` 的 **特征末行** 场景不同，属 **全样本序列推理**。

---

## 7. 已知限制与改进方向

- **历史回测** 与 **线上单日预测** 特征处理不一致（如 `predict_timing` 用 `fillna(0)`，而训练折用中位数/0 inf）。  
- `best_model` 选 **F1 最大** 的 **单轮** 模型，与 `avg_metrics` 的 **平均 F1** 可能不一致，对外解释需注意。  
- 买入/退出 **门限为固定常数**，未随波动率分位数自适应。  
- `t1_open<=0` 等边界在循环中可能留下 **未改写的 0**；真实数据上极少见。  
- 可改进: 使用 **概率校准** 与 **可调阈值**、多任务或共享主干、与 **交易成本** 联合优化。

---

*择时训练完成后由 `backtest_engine` 消费时，请确认 `STOCK_REPORTS_ROOT` 下 `models/{symbol}/timing/` 与训练输出路径一致（与 `config` 中 `STOCK_MODELS_DIR` 相同）。*
