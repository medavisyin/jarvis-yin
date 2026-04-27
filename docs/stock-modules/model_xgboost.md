# XGBoost 方向预测 — 详细功能文档

**文件路径**: `scripts/stock/model_xgboost.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 使用 **XGBoost 多类分类**（`multi:softprob`）对单只股票在 **未来若干交易日收益相对阈值** 的离散标签进行预测，输出 **涨 / 平 / 跌** 三分类、各类概率、特征重要性、以及 **Walk-Forward** 历史准确率。
- **系统角色**: 作为 stock 子系统中的 **机器学习方向引擎**；与 `features.py` 生成的特征与 `target` 标签配合，为报告/UI 提供可解释的短线方向判断。
- **上下游关系**:
  - **上游**: `features.build_features()`、`features.get_feature_names()`（若未传入 `feature_df`）；`config` 中的 `STOCK_DATA_DIR`、`STOCK_MODELS_DIR`。
  - **下游**: 将结果写入 `{STOCK_DATA_DIR}/{symbol}/xgb_prediction.json` 与 `{STOCK_MODELS_DIR}/{symbol}/` 下的 `prediction.json`、`model.json`、`features.json`；`generate_xgb_report()` 可生成 `xgb-report.md`。
  - **文字关系**: `features` → 本模块 → 磁盘 JSON/模型 + 可选 Markdown 报告。

---

## 2. 金融理论基础

- **三分类与短线收益**: 标签在 `features._add_target` 中由 **前向 N 日收益** 相对 **阈值** 切分为涨、平、跌，符合技术分析中“方向 + 动量/盘整”的简化表述，便于与均线、动量、波动等特征联合建模。
- **投资视角**: 方向预测用于 **预期管理** 与 **多因子/多模型信息融合**；XGBoost 能捕捉非线性与特征交互，适合 A 股 **噪声高、非平稳** 的日频序列，但须通过 **时序外推验证** 缓解过拟合。
- **实践背景**: 分类概率可对应 **软概率** 或 **信息系数** 的粗粒度形式；学术上类似 **多类股价方向预测** 与 **机器学习因子** 文献中的设定。
- **A 股适用性**:
  - 涨跌停、T+1 不直接建入本分类器，但 **标签与特征均基于可成交日 OHLCV**；高波动、极端行情日会使“平/涨/跌”边界更模糊。
  - 板块与政策冲击会造成 **结构突变**，Walk-Forward 能部分反映 **近期机制**，但无法保证样本外表现。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **输入 `feature_df`**: 由 `features` 提供，需含无 NaN 的 `target` 行；`target` 为整数 **-1 / 0 / 1**（与 `features` 文档一致：超额涨跌阈值外为 ±1，中间为 0）。
- **内部有效集**: `_prepare_data` 去掉 `target` 为 NaN 的行；`X` 为 `feature_cols` 子集，`y` 为 int 数组；`X` 中 `±inf` 替换为 `NaN` 并在各 fold 中填充。
- **输出 `dict` 关键字段**: `prediction`、`prediction_code`、`confidence`、`probabilities`（键为「涨」「平」「跌」）、`feature_importance`、`walk_forward`（`overall_accuracy`、各轮 `details`）、`model_info`、`latest_date`。
- **持久化**: `LabelEncoder` 在内存中对 **{-1,0,1}** 编解码；保存的 `model.json` 为 XGBoost 原生格式。

### 3.2 关键函数/类

| 符号 | 作用 |
|------|------|
| `_prepare_data` | 去掉无标签行，分离 X、y，处理 inf。 |
| `_impute_fold` | **仅使用训练折中位数** 填充该折内训练/测试的缺失值，**避免用未来数据填过去**。 |
| `train_and_predict` | 主入口：Walk-Forward 多轮训练、汇总准确率、在 **最新时间窗口** 上重训最终模型并对 **最后一行** 出预测；失败时返回 `error`。 |
| `_save_result` | 写 `prediction.json`、`model.json`、`features.json` 及 `data/.../xgb_prediction.json`。 |
| `load_prediction` | 从 `xgb_prediction.json` 读回。 |
| `generate_xgb_report` | 组装中文 Markdown 报告并写入 `xgb-report.md`。 |

- **`train_and_predict(symbol, feature_df=None, feature_cols=None)`**  
  - 若 `feature_df` 为 `None`，内部调用 `build_features` 与 `get_feature_names`。  
  - 若有效样本不足（如 `train_size < 60`）或全程无法训练，返回 `error`。  
  - **类不平衡**: 对少数类使用 **与类别频次成反比** 的 `sample_weight`（`bincount` 推导）。  
  - **每轮**若训练集 `unique` 类数 < 2，**跳过**该轮。  
  - **最终模型**: 在 `[final_train_start, n)` 上重训；若 `last_model` 有 `best_iteration` 且 >0，则把 `n_estimators` 设为 `best_iteration + 1`（去掉 `early_stopping_rounds`），再 fit。

### 3.3 算法与计算逻辑

- **XGBoost 配置要点**: `objective=multi:softprob`，`num_class=3`，`max_depth=3`，`n_estimators=200`（早停/最终可能被缩短），`learning_rate=0.05`，`min_child_weight=8`，`subsample=0.7`，`colsample_bytree=0.6`，`reg_alpha=0.5`，`reg_lambda=2.0`，`early_stopping_rounds=15`（在 Walk-Forward 的验证折上使用）。
- **Walk-Forward 几何**:
  - `train_size = min(500, n - 5 - 1)`，**测试窗宽度** `_TEST_WINDOW = 5` 日。
  - 轮次 `rnd`: `test_end = n - rnd*5`，`test_start = test_end - 5`，训练区间为 `[test_start - train_size, test_start)`，从 **最近** 的测试块向 **过去** 滑动，最多 `_N_ROUNDS=15` 轮（受数据长度截断）。
  - 每轮在 **测试集** 上算准确率，汇总为 `walk_forward.overall_accuracy`（正确数/总测试样本数，跨轮合计）。
- **最终预测**: 对 **全表最后一行** 特征，用 **最终训练窗口** 的中位数填充后，取 `argmax(softmax prob)` 对应原始标签，置信度为该类概率。
- **防过拟合**:
  - 训练/验证严格 **时间序**；缺失值 **按折** 中位数填充；  
  - 正则有 `reg_alpha`/`reg_lambda`、子采样、列采样、浅树、早停；  
  - 类别重加权缓解 **三分类样本不均衡**。

---

## 4. 外部依赖与数据源

- **第三方**: `numpy`、`pandas`、`sklearn.preprocessing.LabelEncoder`、`xgboost`（延迟 `import`）。
- **项目内**: `config.STOCK_DATA_DIR`、`STOCK_MODELS_DIR`；`features` 模块；默认数据根为环境变量可覆盖的 `C:/reports/stock` 系列路径。
- **缓存**: 无独立缓存模块；结果以 **JSON + 模型文件** 形式落盘。

---

## 5. 配置项与可调参数

| 常量/参数 | 默认值 | 含义与调优建议 |
|-----------|--------|----------------|
| `_TRAIN_WINDOW` | 500 | 单折最大训练长度；数据较短时会自动缩短。 |
| `_TEST_WINDOW` | 5 | 每轮 OOS 长度；增大则更稳但更慢。 |
| `_MIN_DATA_ROWS` | 300 | 仅用于日志警告，真正硬门槛为 **train_size≥60** 等。 |
| `_N_ROUNDS` | 15 | Walk-Forward 轮数上限。 |
| `_EARLY_STOPPING_ROUNDS` | 15 | 每折 XGB 早停。 |
| `params` 内 | 见源码 | 树深度、学习率、`min_child_weight` 等可网格搜索，须 **嵌套** 在 Walk-Forward 内评估以防泄漏。 |

---

## 6. 使用示例与工作流

```python
from model_xgboost import train_and_predict, load_prediction, generate_xgb_report

r = train_and_predict("600519")
# 或先构造 feature_df 再 train_and_predict("600519", feature_df, feature_cols)
if "error" not in r:
    generate_xgb_report("600519", r)
```

- 与 **价格预测**、**择时** 可并行使用：本模块提供 **日频三分类方向**，`model_price_predictor` 提供 **价位**，`model_timing` 提供 **事件型买卖/风险** 标签。

---

## 7. 已知限制与改进方向

- 标签 **依赖 `features` 的 forward 天数与阈值**，文档需与 `features` 保持同步。  
- Walk-Forward 的「整体准确率」是 **多段小测试集** 的合并，**非严格单次连续样本外** 表述时需在对外沟通中说明。  
- 最后一行预测 **未** 使用单独 hold-out 只做展示；**金融成本与交易约束** 未在损失中显式编码。  
- 可探索：时序交叉验证的 **purging/embargo**、概率校准、与组合层约束联动。

---

**说明**: 报告文末免责声明（见 `generate_xgb_report`）提醒「仅供参考」——与合规表述一致。
