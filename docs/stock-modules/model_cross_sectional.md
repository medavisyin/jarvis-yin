# 截面 XGBoost 排序 — 详细功能文档

**文件路径**: `scripts/stock/model_cross_sectional.py`  
**最后更新**: 2026-05-01

---

## 1. 模块概述

- **核心职责**: 对 **Layer 1** 输出的候选股集合做 **截面相对强弱排序**：不预测单只股票绝对涨跌，而是用 **XGBoost `rank:pairwise`** 学习「同一交易日内谁相对更强」；标签为 **行业中性化后的超额收益（Alpha）** 离散成的相关度等级；预测后经 **行业中性化**（每行业取 Top N）输出最终名单。
- **系统角色**: 作为 stock 子系统中 **Scanner Layer 2** 的主排序引擎；失败或样本不足时由 `scanner.py` **回退到规则评分**（`_layer2_rule_scoring_all`）。
- **上下游关系**:
  - **上游**: `scanner` Layer 1 候选列表（每项含 `symbol`、`name`、`price`、`score_l1` 等）；`config.STOCK_DATA_DIR` 下各标的 `daily.csv`（新鲜缓存优先）；不足时经 **AKShare** 拉取日线；`config.STOCK_CACHE_DIR` 下行业映射缓存 `.industry_map.json`。
  - **下游**: 返回增强后的候选 `dict` 列表（`score_l2`、`xgb_rank`、`industry`、`xgb_alpha`、`model_ndcg`），供 **Layer 3**（如 `_layer3_llm_rank`）进一步处理；进度对象中记录 `layer2_mode` 为 `xgb_cross_sectional` 或回退为 `rule_fallback`。
  - **数据流**: Layer 1（~100 只）→ 批量历史行情 → 截面特征矩阵 → 当日训练/验证拆分下的排序模型 → 当日分数 + 行业内 Top N → Layer 2 输出。

---

## 2. 金融理论基础

- **截面排序 vs 绝对方向预测**: 绝对方向模型关注「这只股票明天涨还是跌」；本模块关注 **同一日历日、同一候选池内** 的 **相对排序**，更贴近 **组合构建中的横向比较**（哪只在当前横截面上更强），对单票噪声部分对冲。
- **`rank:pairwise` 目标**: XGBoost 在同组（此处为 **同一历史交易日 `qid`**）样本上优化 **成对排序**；标签为 **0–4 的 relevance 等级**，弱化为序关系学习，对收益分布厚尾更稳健于单点回归。
- **Alpha 与标签构造**: 在每个交易日截面上，**Alpha = 个股当日 `ret_1d` − 其所属行业的当日 `ret_1d` 均值**（申万一级行业由行业映射给出）；再将截面 Alpha 分位数映射为 relevance（极强/较强/中性/较弱/极弱五档）。经济含义：**剥离行业 β 后的相对强弱**，降低行业抱团在排序目标中的主导性。
- **行业中性化（输出层）**: 模型先对全日截面给出 **`xgb_score`**，再 **按行业分组**，每组取 **`top_n_per_industry` 分数最高** 的标的，最后按分数全局降序拼接。作用：避免 Layer 2 输出 **过度集中于单一行业**，与组合层行业约束的常见实践一致。
- **A 股适用性说明**: 标签与特征均基于 **可观测日频 OHLCV**；涨跌停、`T+1` 未显式写入损失函数。行业映射依赖数据源完整性与缓存时效，缺失时落入 **「其他」** 行业桶。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **输入 `candidates`**: `list[dict]`，至少含 `symbol`（及 Layer 1 已填充的展示/规则字段）；可选 `stop_event`（`threading.Event`）用于扫描中断。
- **`all_hist`**: `dict[str, pd.DataFrame]`，键为代码，值为标准化列名后的日线（`date/open/close/high/low/volume/...`）。
- **`hist_df` / `today_df`**: 历史截面样本表与 **最后一交易日** 截面表；列含 `date`、`symbol`、`industry`、`_FEATURE_COLS` 子集、**`alpha`**、**`relevance`**、训练用 **`qid`**（按历史日期编序号）。
- **输出列表项**: 在原候选 `dict` 上追加 `score_l2`（模型分四舍五入）、`xgb_rank`（1-based 全名次）、`industry`、`xgb_alpha`、`model_ndcg`；失败返回 `[]`。

### 3.2 关键函数/类

| 符号 | 作用 |
|------|------|
| `cross_sectional_rank` | **主入口**：行业映射 → 批量历史 → 特征 → 训练 → 预测与行业中性化 → 合并回候选。 |
| `_should_stop` | 检查 `stop_event` 是否置位。 |
| `_fetch_industry_map` | 申万一级行业映射；优先读 **24 小时内** 的 JSON 缓存，否则 AKShare 拉板块成分并写缓存；失败或缓存失效走 `_fetch_industry_fallback`。 |
| `_fetch_industry_fallback` | 对至多前 50 只代码用 `stock_individual_info_em` 解析「行业」字段。 |
| `_fetch_batch_history` | 逐票读取 `daily.csv`（**12h 内**视为新鲜）或 `ak.stock_zh_a_hist`（前复权）；请求间 `_BATCH_DELAY` 睡眠。 |
| `_normalize_columns` | 将 AKShare/CSV 中文列名转为英文小写并列类型规整。 |
| `_compute_single_stock_features` | 单票时序特征：**多周期收益、RSI、MACD 柱、ATR%、波动率、均线距离、量比、K 线形态、换手率** 等（不含截面秩）。 |
| `_build_cross_sectional_features` | 按日横截拼接 → `_add_cross_sectional_features` / `_add_alpha_target` → 最后一日为 `today_df`，其余为训练验证池。 |
| `_add_cross_sectional_features` | 当日截面 **`ret_1d` / `volume` / `turnover_rate`** 的 **分位秩**（`cs_*_rank`）。 |
| `_add_alpha_target` | 行业组内减均值得 `alpha`，再映射 **`relevance` 0–4**。 |
| `_train_ranker` | `xgb.train`，`rank:pairwise`，`DMatrix.set_group`；时间序划分训练/验证，指标 **NDCG@10**，早停 20 轮。 |
| `_qid_to_groups` | 将有序 `qid` 数组转为 XGBoost 所需的 **group sizes**。 |
| `_predict_and_neutralize` | `model.predict` 得 `xgb_score`，按行业 `nlargest` 取 Top N，再全局按分排序。 |

### 3.3 算法与计算逻辑

- **有效样本门槛**: 历史长度 ≥ `_MIN_HISTORY` 的代码参与；**有效代码数 < 10** 时直接放弃截面排序；训练侧要求 **交易日数量 ≥ `_TRAIN_DAYS + 5`**，且 train/val 行数满足 `_train_ranker` 内检查。
- **特征缺失**: 训练/验证用 **训练集列中位数** 填充；预测当日缺失填 **0**。
- **时间序列用法**: `qid` 按日期分组，**不打乱日期**；验证块为时间轴 **尾部 `_VAL_DAYS` 个交易日**（与 `_TRAIN_DAYS`、总长度共同决定切分）。
- **早停与评估**: `eval_metric=ndcg@10`，`early_stopping_rounds=20`；最佳验证 NDCG 记入日志并写入输出的 `model_ndcg`。

---

## 4. 外部依赖与数据源

- **第三方**: `numpy`、`pandas`；**`xgboost`**（`_train_ranker`、`_predict_and_neutralize` 内延迟导入）；**`akshare`**（行业板块、个股信息、日线历史）。
- **项目内**: `config.STOCK_DATA_DIR`（`{symbol}/daily.csv`）、`config.STOCK_CACHE_DIR`（`.industry_map.json`）。
- **缓存策略**:
  - 日线：优先本地 CSV，**修改时间 12 小时内** 且行数足够则截尾使用；否则请求 AKShare。
  - 行业：**.industry_map.json** 在 **24 小时内** 且对当前 symbols **命中率 > 50%** 则整表补齐缺失为「其他」后返回。
- **限流**: 批量历史中每 `_BATCH_DELAY` 秒一只；行业板块循环内有 `time.sleep(0.2)`，fallback 单票 `0.15s`。

---

## 5. 配置项与可调参数

| 常量/参数 | 默认值 | 含义与调优建议 |
|-----------|--------|----------------|
| `_LOOKBACK_DAYS` | 60 | 截面构建与拉取数据的大致回看窗口（拉取时会按 `lookback_days * 1.5` 扩 start_date）。 |
| `_TRAIN_DAYS` | 40 | 与总交易日数、`_VAL_DAYS` 共同决定训练/验证切分。 |
| `_VAL_DAYS` | 20 | 时序验证窗口长度；增大则更保守的样本外但更晚数据。 |
| `_MIN_HISTORY` | 30 | 参与截面的最短历史行数阈值。 |
| `_TOP_PER_INDUSTRY` | 3 | 行业中性化每层保留的最高分标的数；可按组合行业集中度调大/调小。 |
| `_FALLBACK_INDUSTRY` | `"其他"` | 无行业映射时的桶名。 |
| `_INDUSTRY_CACHE_HOURS` | 24 | 行业 JSON 缓存最长有效时间。 |
| `_BATCH_DELAY` | 0.3 | 批量拉行情间隔（秒），防接口限流。 |
| `_XGB_PARAMS` | 见下 | 与 `xgb.train` 内 **`eta`** 等映射一致；可调树深、采样、正则、`n_estimators`。 |
| `_FEATURE_COLS` | 见源码 | 训练/预测使用的列白名单；增删特征需同步此处与工程逻辑。 |
| `cross_sectional_rank(..., lookback_days, top_n_per_industry)` | 默认取上表常量 | 调用可调回看窗口与每行业 Top N。 |

**`_XGB_PARAMS` 键值摘要**: `objective=rank:pairwise`，`max_depth=4`，`learning_rate=0.05`，`min_child_weight=8`，`subsample=0.7`，`colsample_bytree=0.6`，`reg_alpha=0.5`，`reg_lambda=2.0`，`n_estimators=200`，`verbosity=0`。

---

## 6. 使用示例与工作流

```python
from model_cross_sectional import cross_sectional_rank

# candidates 通常来自 Scanner Layer 1，每项需含 symbol
ranked = cross_sectional_rank(
    candidates,
    lookback_days=60,
    top_n_per_industry=3,
    stop_event=None,  # 可选：与 scanner 共用 Event 以支持中断
)
if not ranked:
    # 调用方应回退到规则评分等策略（scanner 已封装）
    ...
```

- **与 `model_xgboost` 的分工**: `model_xgboost` 面向 **单票三分类方向** + Walk-Forward；本模块面向 **多票截面排序** + **行业约束输出**，二者可同时用于不同层或不同产品形态。

---

## 7. 已知限制与改进方向

- **在线训练**: 每次扫描在可用历史上 **重新训练**，无持久化排序模型；计算与 API 依赖随候选规模线性增长。
- **标签泄露表述**: 文档层面应知：**`relevance` 使用当日 `ret_1d` 与行业均值**，在严格因果表述下属于「当日收益已知后定义」的监督信号；实现意图是「用 T 日截面结果定义 T 日相对强弱标签」，特征来自 **T 日及以前可计算的指标**，但与未来持仓 PnL 仍需业务上区分展示。
- **行业数据**: 全市场拉板块成分可能 **慢且不稳定**；缓存部分命中时缺失码归为「其他」可能影响 Alpha 分解精度。
- **截面稀疏日**: 单日有效股票少于 5 则该日不进入样本；极端行情下有效日可能变少。
- **改进方向**: 模型落盘与增量训练；purging/embargo 式验证；行业映射多源校验；特征与 relevance 的 **超前一期** 对齐以匹配严格预测任务；与组合优化器约束直连。

---

**说明**: 本模块输出用于 **研究/扫描辅助**；实际投资需结合风控、合规与交易成本，与项目其他模型文档保持一致预期。
