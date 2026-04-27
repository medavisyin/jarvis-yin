# 预测追踪系统 — 详细功能文档

**文件路径**: `scripts/stock/prediction_tracker.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 在 **`train_price_prediction` 等产生价格预测之后**，将 **预测日、目标价、当前收** 等写入 **按标的维度的 JSON 日志**；在行情更新后 **回填下一交易日的真实 OHLC**，计算 **绝对误差、百分比误差、方向是否命中**；并对外提供 **MAPE/MAE/方向命中率** 的 **滚动统计** 与 **模型健康分（health）**、多标的 **聚合统计**。  
- **系统角色**: **ML 运营与质控** — 把「点预测」变成 **可审计的时间序列真值比较**，支持 UI 的「最近验证」与自监控。  
- **上下游关系**:
  - **上游**: 典型由 `model_price_predictor.train_price_prediction` 的结果传入 `record_prediction`；`backfill_actuals` 用 `technical_analysis.load_ohlcv`。  
  - **下游**: 读 `STOCK_DATA_DIR/{symbol}/predictions_log.json`；`get_accuracy_stats` / `get_latest_verification` / `get_aggregate_stats` 供看板与告警。

**简图**: `train_price_prediction` → `record_prediction` → 日志（待验证） → `load_ohlcv` → `backfill_actuals` → 已填日志 → `get_accuracy_stats` + `_calc_model_health`。

---

## 2. 金融理论基础

- **预测可验证性**: 投资中任何 **可检验** 的预测都应对齐 **可观测基准**；此处以 **T+1（下一交易日）** 的实现高低收与预测对比，符合 **前推一日** 的日频习惯。  
- **误差度量**:  
  - **MAPE/平均绝对百分比** 在实务中常用来 **量纲化** 不同股价下的误差，但受 **小分母** 影响大；本实现用 **|误差|/|实际价|**，对 `close` 在 `error_pct_close` 中体现。  
  - **方向准确率**: 以 **预测价 vs 预测当日的 current_close** 与 **实际收 vs 同一 current_close** 的符号是否一致，衡量 **是否猜对涨跌**，与方向分类器的评价类似但 **仅基于已成交收盘价**。  
- **A 股**: 下一日若有 **停牌、长假期**，`next_row` 取 **date 上严格大于 prediction_date 的第一行**，与「下一交易日」在日历上可能 **间隔多日**，需在解读聚合指标时知悉。  
- **健康度**: 将 **最近若干次的误差与方向** 映射为 A/B/C/D 等级，属于 **简单启发式** 的 **监控仪表盘**，**非** 统计假设检验。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **单条 `entry`（`record_prediction` 写入）** 字段含: `prediction_date`（与 `latest_date` 一致）、`target_date`（回填后）、`predicted_at`、`current_close`、`predicted_{close,high,low}`、`actual_*`、**误差** 与 `error_pct_*`、`direction_correct` 等。  
- **存储位置**: `os.path.join(STOCK_DATA_DIR, symbol, "predictions_log.json")`（`config` 中 `STOCK_DATA_DIR` 为 `C:/reports/stock/data` 下默认）。与模块文件头 `C:/reports/stock/data` 的表述 **一致**（通过 config）。  
- **列表按 `prediction_date` 字符串排序** 后保存。

### 3.2 关键函数/类

| 函数 | 行为摘要 |
|------|----------|
| `_log_path` / `_load_log` / `_save_log` | 路径、安全加载、落盘。 |
| `record_prediction` | 从 `prediction_result` 取 `predictions` 与元数据；**同一 prediction_date 覆盖** 旧条；新条 `append`；未预测则 `return`。 |
| `backfill_actuals` | 对 `actual_close is None` 的条目，在 `ohlcv` 找 **date_str > pred_date** 的 **首行** 作为「下一根K线」；写实际 OHLC 与各类误差。`filled` 计数为 **本函数尝试处理的条数**（含多条连续回填场景下的增量）。若 `entries` 空则 0。 |
| `get_accuracy_stats` | 子集 `filled` 上算 **整体 / 最近7条 / 最近30条** 的 `avg_mape`（**基于 error_pct_close 等**）、`avg_mae`（|error_close| 均值）、高/低 MAPE、方向命中率；`health = _calc_model_health(filled)`；`recent` 为最近 10 条已填、**时间倒序**。 |
| `get_latest_verification` | 已填条目中 **最后一条**（时间顺序上最新），用于 **昨日预测 vs 实际** 展示。 |
| `get_aggregate_stats` | 多标的：合计预测数/已验/待验、**方向合计**、**全样本平均 MAPE/MAE**、拼接各标的 `last_7`/`last_30` 条做窗口统计、**per_symbol 排行**（按 `direction_accuracy` 降序）。 |
| `_calc_model_health` | 见 3.3。 |
| `_safe_float` | 安全转 float，过滤 NaN。 |

### 3.3 算法与计算逻辑

- **收盘价误差**: `error_close = actual_close - predicted_close`；`error_pct_close = abs(error_close) / abs(actual_close) * 100`（**为绝对百分比偏差**，在 `stats` 里被 **标为 avg_mape** —— 即 **以平均 APE 作为 MAPE 代理**）。  
- **高/低**: 同理用绝对误差与分母为实际 high/low 的百分比。  
- **方向**: `pred_dir = sign(predicted_close - current_close)`，`actual_dir = sign(actual_close - current_close)`，**相等为 True**；**若预测价等于 current_close，pred_dir=0** 等。  
- **健康分 `_calc_model_health`**:
  - 需 **已填条数 ≥ 5**；取 **最近 5 条** 的 `error_pct_close` 均值 `avg_mape` 与 `direction_correct` 比例 `dir_acc`。  
  - 分级:  
    - **A**: `avg_mape ≤ 1.5` 且 `dir_acc ≥ 0.7`  
    - **B**: `avg_mape ≤ 3.0` 且 `dir_acc ≥ 0.5`  
    - **C**: `avg_mape ≤ 5.0` **或** `dir_acc ≥ 0.4`（**注意 OR**）  
    - **D**: 其他  
  - `action`: `continue` / `monitor` / `review`。  
  - **trend**（当 `len(filled) ≥ 10`）: 比较 **最近5条** 与 **再往前5条** 的平均 MAPE，判断 `improving` / `degrading` / `stable`（0.8/1.2 倍阈值）。  
  - 返回 `grade`, `color`（十六进制色）, `message`, `action`, `trend`, `recent_mape`, `recent_direction_acc`, `sample_size`（= **全部已填条数**）。

---

## 4. 外部依赖与数据源

- 标准库 `json`, `os`, `datetime`；`logging`。  
- `config.STOCK_DATA_DIR`；`technical_analysis.load_ohlcv` 用于回填。  
- 无独立缓存，**唯一事实来源** 为 per-symbol 的 `predictions_log.json`。

---

## 5. 配置项与可调参数

- **无** 文件级可调常量；健康阈值 **硬编码** 在 `_calc_model_health` 中。  
- **运维**: 可定期跑 `backfill_actuals` 在批任务中；**同一 symbol 同日复跑** `record_prediction` 会 **覆盖** 同日条目。

---

## 6. 使用示例与工作流

```python
from model_price_predictor import train_price_prediction
from prediction_tracker import record_prediction, backfill_actuals, get_accuracy_stats

r = train_price_prediction("600519")
record_prediction("600519", r)
# 隔日有行情后
backfill_actuals("600519")
print(get_accuracy_stats("600519"))
```

- 与 **多标的 watchlist** 配合: `get_aggregate_stats(symbols)` 输出组合层 MAPE/方向命中。

---

## 7. 已知限制与改进方向

- **MAPE 命名** 与部分文献中 `mean(|pe|), pe=(y-ŷ)/y` 的严格定义需区分；分母为 **实际价** 的 **绝对百分比误差** 之 **平均**。  
- **C 级** 使用 **OR** 条件，**高误差但方向尚可** 或 **反过来的情况** 会进入 C 档。  
- `backfill_actuals` 的 `filled` 计数为 **成功写入处理的条目数** 逻辑上每条 **仅** 在 `actual_close` 仍空时进分支；**多条一次跑完** 时统计行为以源码为准。  
- **高/低** 与 **日内** 关系未做 high≥low 一致性校验。  
- 可改进: 分位数与置信区间、**Wilson 区间** 下的方向率、**漂移检测**（PSI）、与 **模型重训** 联动。

---

*建议在 UI 中同时展示 `health.trend` 与 **样本量 `sample_size`**，避免在 **5–10 条** 上过度解读等级。*
