# 明日价格预测（XGBoost 回归）— 详细功能文档

**文件路径**: `scripts/stock/model_price_predictor.py`  
**最后更新**: 2026-07-01

---

## 1. 模块概述

- **核心职责**: 为单只股票训练 **三个独立的 XGBoost 回归器**，分别预测 **下一交易日** 的 `close` / `high` / `low` 相对 **当日收盘** 的 **百分比收益**；输出还原后的绝对价格、经 **A 股涨跌幅限制** 截断的变动百分比、Walk-Forward 的 MAE/MAPE/方向命中率（对 close）、**综合置信度**，以及一个 **方向标签（direction_label）** 用于弱信号弃权提示。
- **系统角色**: 在 `features` 技术特征与 OHLCV 之上增加 **价量序列与情绪** 特征，是 stock 子系统中 **点预测 + 区间（高/低）** 的核心模块。
- **上下游关系**:
  - **上游**: `features.build_features`、`get_feature_names`；`technical_analysis.load_ohlcv`；`market_sentiment.load_cached_sentiment`（仅最新行）；可选 `config` 路径。
  - **下游**: `STOCK_DATA_DIR/{symbol}/price_prediction.json`；模型 `STOCK_MODELS_DIR/{symbol}/price_{close|high|low}_model.json`；`generate_price_report` → `price-prediction-report.md`；常与 `prediction_tracker` 联用做 **事后验证**。

---

## 2. 金融理论基础

- **预期价格与无套利直觉**: 下一日 OHLC 在 A 股受 **前收 ±涨跌停** 硬约束；将预测先放在 **收益空间** 再映回价格，符合「收益率建模 + 价格还原」的实务流程。
- **高/低/收联合**: 分别回归三条曲线可捕捉 **波动区间**（盘中振幅）与 **收盘** 的独立信息；但三条独立训练 **不保证** 日内 high ≥ low 的 **逻辑一致性**，代码在输出阶段对 high/low 做了 **若颠倒则交换** 的修正（见 3.3）。
- **A 股特别性**:
  - **主板的 10%、创业板/科创 20%、北交所 30%** 等由 `_get_price_limit` 按代码前缀粗分，用于 **变动百分比** 的 clamp。  
  - 情绪类（VIX、恐惧贪婪）在特征里 **仅对最后一行** 注入，减少 **用未来全序列情绪** 的错配（见源码注释）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`_build_price_features` 返回的 DataFrame**:
  - 合并 `ohlcv` 的 `open/high/low/close` 到特征表。  
  - 为每个 `target` 建列: `target_{name} = (次日价格 / 当日 close - 1) * 100`（**百分比**）。  
  - `attrs["feature_cols"]` = 原 `get_feature_names()` + 通过 **缺失率 ≥50% 筛选** 的 `price_seq_*`、`sent_*` 列。  
- **有效训练行**: 各目标上 `dropna(subset=[target_col])`；特征矩阵 `X` 对 `inf` 变 `NaN`，折内中位数填充。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `_get_price_limit(symbol)` | `300`→20%，`688`→20%，`8`/`4` 开头→30%，否则 **10% 主板**。 |
| `_clamp_prediction(pred, current, limit)` | 将绝对价格限在 `[current*(1-limit), current*(1+limit)]`；**主流程**另在百分比层 clamp（见下）。 |
| `_build_price_features` | 拼特征、价格序列、情绪，注册 `feature_cols`。 |
| `_add_price_sequence_features` | 滞后收益、均线比、动量、HL 比、简易 VWAP 代理等。 |
| `_add_sentiment_features` | 缓存里读 Fear&Greed、VIX，**仅填最后一行索引**。 |
| `_select_top_features` | 方差 + 与 **该目标** 相关性的 **秩和**，取 Top `_MAX_FEATURES=40`。**2026-07-01 起**只在 **训练切片**（逐折）与 **最终训练窗口** 上调用，**不再在全量 `valid` 上选**，避免把未来测试折目标纳入筛选（look-ahead 泄露）。 |
| `_impute_fold` | 折内训练 **中位数** 填充，返回训练/测试数组及（回归流程中可丢弃的）`medians` 元组。 |
| `_compute_confidence` | 据 close 的 Walk-Forward `overall_mae`、`direction_accuracy` 与 `change_pct` 的绝对值，输出 `level` / `signal_strength` / 英文 `note`。 |
| `train_price_prediction` | 对 close/high/low 各跑一遍 Walk-Forward + 最终窗重训，再 **把百分比 clamp 到涨跌停** 后换算为价格；并输出 `direction_label`（震荡/方向不确定/看涨/看跌）。 |
| `load_price_prediction` / `generate_price_report` | 读盘与写 Markdown 报告。 |

### 3.3 算法与计算逻辑

- **回归目标**: 单位为 **相对当日收盘的百分比**；`XGBRegressor` 用 `reg:squarederror`。
- **超参（摘录）**: `max_depth=4`, `n_estimators=300`, `learning_rate=0.05`, `min_child_weight=8`, `subsample=0.7`, `colsample_bytree=0.6`, `reg_alpha=0.5`, `reg_lambda=2.0`, `early_stopping_rounds=15`。
- **特征选择（2026-07-01 重构）**: 每个目标在 **每一折的训练切片** 内独立做特征裁剪（`fold_cols`），最终模型再在 **最终训练窗口** 内选一次（`final_cols`）。三者子集可能不同。**关键**：筛选只用训练数据，**不含未来测试折目标**，消除 look-ahead 泄露；最终窗口终点早于"明日"预测点，对线上预测无前视。
- **Walk-Forward**: 与 `model_xgboost` 类似的时间窗与轮次；每轮对测试段算 **MAE**（|pred−y|，y 为百分比）、**每点百分比误差** `pct_errors = errors / max(|y|, 0.5) * 100` 的均值作为该轮 **mape 字段**（**非标准 MAPE 定义**时需注意分母为 max(|y|,0.5)）；仅 **close** 目标算 **方向一致率**（`sign(pred)` vs `sign(y)`）。注意：因逐折重选特征，`wf_results` 指标 **诊断性** 反映"逐折模型"而非"最终模型"，已在 `model_info.wf_note` 声明。
- **最终预测（2026-07-01 off-by-one 修复）**: 在 **最近 train_size 窗** 上重训后，用 **`df` 最后一行（今日）的特征** 得到 `pred_pct`（该行 `target_*` 为 NaN，但后向特征齐全）；然后  
  - `clamped_pct = clip(raw_pct, -limit*100, +limit*100)`  
  - `price = current_close * (1 + clamped_pct/100)`；若 high < low 则 **交换** high/low 与对应 `change_pct`。  
  > **历史问题**：2026-07-01 前推理用的是 `X_all.iloc[[-1]]`，而 `X_all` 来自 `valid = df.dropna(target)`，其最后一行实为 **df 倒数第二行**——模型预测的是"已实现K线"的收益，却被 `prediction_tracker` 按"下一根"评估，导致方向准确率塌到 ~44%（低于随机 50%）。修复后 `latest_date`（= `df["date"].iloc[-1]`）与 tracker 评估的"下一根"对齐。
- **方向标签 `direction_label`**: `close_pct == 0 → 震荡`；非零且 `signal_strength == "noise"`（\|预测涨跌幅\| < 历史 MAE）`→ 方向不确定`；否则 `看涨`/`看跌`。对噪声带预测 **诚实弃权**，避免在随机波动上给出伪方向。
- **防过拟合**: 子采样/列采样/正则/早停/折内填充/逐折与最终窗特征裁剪到 40 维。

---

## 4. 外部依赖与数据源

- **库**: `numpy`、`pandas`、`xgboost`（各训练分支内 `import`）。  
- **项目模块**: `features`、`technical_analysis.load_ohlcv`、`market_sentiment.load_cached_sentiment`（可失败静默）。  
- **存储**: `STOCK_DATA_DIR`、`STOCK_MODELS_DIR`（见 `config`）。

---

## 5. 配置项与可调参数

| 项 | 默认 | 说明 |
|----|------|------|
| `_TRAIN_WINDOW` / `_TEST_WINDOW` / `_N_ROUNDS` | 500 / 5 / 15 | 与方向模型同量级设计。 |
| `_MAX_FEATURES` | 40 | 控制维数。 |
| `_LIMIT_PCT` | 0.1/0.2/0.3 | 与板块前缀绑定；**ST 等其它规则未单独编码**。 |
| XGB 超参 | 见源码 | 可针对波动大的标的略增 `min_child_weight` 或 `reg_lambda`。 |

---

## 6. 使用示例与工作流

```python
from model_price_predictor import train_price_prediction, generate_price_report

r = train_price_prediction("600519")
# 与 prediction_tracker.record_prediction(r) 配合形成闭环验证
text = generate_price_report("600519", r)
```

---

## 7. 已知限制与改进方向

- 板块通过 **代码前缀** 粗分，**ST、注册制细微差别** 等未实现。  
- 三条回归 **独立训练**，高/低/收 **联合分布** 未用多任务或排序约束。  
- `_clamp_prediction` 在 **训练输出路径** 中未单独调用，实际以 **百分比 clamp** 实现等价边界。  
- 置信度 `_compute_confidence` 的 **`note` 为英文**，若 UI 全中文需外层翻译。  
- 情绪特征仅 **末行有值**，历史行为是否充分利用取决于下游。
- **逐折特征选择** 使 `wf_results` 指标反映"逐折模型"而非"最终上线模型"（`model_info.wf_note` 已声明）；如需更干净的指标，可改为固定前置训练窗口选一次特征、所有折复用，但须避免与后续测试折目标重叠。
- **方向准确率上限**: A 股日频接近有效市场，即便 off-by-one 修复后，方向准确率也应预期在 **50% 附近** 而非 70%+；`direction_label="方向不确定"` 是对噪声带预测的诚实弃权，**不代表模型坏了**。
- `_save_model` 接收 `feature_cols` 但 **未持久化特征顺序**（既有问题），未来若要"加载已存模型做离线推理"需补 sidecar 文件。

---

*报告模块末尾含投资风险提示，与 `generate_price_report` 一致。*
