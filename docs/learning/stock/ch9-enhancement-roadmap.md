# Jarvis 股票分析增强路线图 — 让预测更可靠、覆盖更多场景

> 前 8 章你已经学会了投资的 **思维框架（mental framework）**，也看到了 Jarvis 现有模型的 **真实边界（real boundaries）**。  
> 本章不再讨论"要不要做量化"，而是回答一个工程问题：  
> **如果我想让 Jarvis 的股票分析真正有用，下一步到底应该做什么？**

读完本章你会得到：

- 一份分阶段的 **工程路线图（phased engineering roadmap）**，每阶段都有明确的目标和验收标准
- 对每个改进项的 **预期收益、难度、所需资源** 的诚实评估
- 具体的 **代码修改方向（code-level directions）**，指向 `scripts/stock/` 中的模块
- **环境适应性（environment coverage）** 的系统方案：牛市、熊市、震荡、黑天鹅

---

## 0. 当前基线：我们在哪里？

在规划"去哪里"之前，先诚实画出 **起点（baseline）**：

| 维度 | 当前状态 | 主要短板 |
|------|---------|---------|
| **数据源** | 公开 OHLCV + 新闻标题 + 基本面快照 | 无 Level 2 盘口、无资金流、无社交舆情 |
| **特征** | ~40 个技术面 + 少量基本面 + 少量情绪 | 全部可公开获取、无独家信息优势 |
| **模型** | 单一 XGBoost（分类 + 回归） | 无集成、无深度学习、无在线学习 |
| **估值** | PE/PB/ROE 打分 | 无 DCF、无同业比较、无历史分位 |
| **风控** | 无 | 无仓位建议、无组合层面风险度量 |
| **环境适应** | 无 | 牛市/熊市/震荡用同一套参数 |
| **回测** | Walk-forward（正确方向） | 无完整策略回测、无成本模型 |
| **执行** | 无 | 无订单管理、无滑点模型 |

---

## Phase 1：数据层加固（Data Layer Hardening）

**目标**：拿到更好、更全、更干净的数据。  
**为什么排第一**：所有模型都是"垃圾进垃圾出（garbage in, garbage out）"。数据质量的改善比任何模型改进收益都大。

### 1.1 历史数据加深

| 改进 | 具体做法 | 影响的文件 |
|------|---------|-----------|
| 扩展历史到 3–5 年 | akshare 支持拉长周期；修改 `fetch_market_data.py` 的默认 `period` 参数 | `fetch_market_data.py` |
| 复权处理标准化 | 确保全部使用前复权（qfq），Sina 备用源的非复权数据需标记或排除 | `fetch_market_data.py`, `technical_analysis.py` |
| 数据完整性校验 | 加入缺失日期检测（停牌、节假日）、异常值检测（单日涨幅超限但非涨停） | 新模块 `data_quality.py` |

**验收标准**：每只标的至少 750+ 交易日无缺失数据，复权方式统一。

### 1.2 新增数据源

| 数据类型 | 来源 | 用途 | 难度 |
|----------|------|------|------|
| **资金流（Fund Flow）** | akshare `stock_individual_fund_flow` | 主力/散户买卖力量 | ★★☆ |
| **融资融券（Margin Trading）** | akshare `stock_margin_detail_szse/sse` | 杠杆情绪指标 | ★★☆ |
| **北向资金（Northbound Flow）** | akshare `stock_hsgt_north_net_flow` | 外资风向标 | ★☆☆ |
| **基金持仓（Fund Holdings）** | 季报披露，akshare 或巨潮 | 机构认可度 | ★★★ |
| **行业指数（Sector Indices）** | akshare 板块行情 | 板块轮动参考 | ★☆☆ |
| **宏观经济（Macro Indicators）** | CPI、PMI、社融、M2 — 国家统计局/央行 | 大周期背景 | ★★☆ |

**对应改动**：

- `fetch_market_data.py` → 新增 `_fetch_fund_flow()`, `_fetch_margin()`, `_fetch_northbound()` 等函数
- `features.py` → 新增 `_add_fund_flow_features()`, `_add_macro_features()` 等
- `config.py` → 新增缓存路径

### 1.3 新闻与舆情增强

| 改进 | 具体做法 |
|------|---------|
| 情绪评分分层 | 当前 `sentiment.py` 对所有新闻等权平均；改为按 **时效性（recency）** 加权 + 按 **影响力（impact level）** 分级 |
| 新增舆情源 | 爬取雪球（xueqiu）讨论区热度、同花顺问财数据 |
| NLP 改进 | 用更大的 LLM（如 qwen3.5:8b）替代 1.7b 做情绪评分，或加入 **FinBERT** 专用金融情感模型 |

**验收标准**：情绪评分与次日涨跌方向的 **相关系数（correlation）** 从当前约 0.05 提升到 > 0.10。

---

## Phase 2：估值体系重建（Valuation System Rebuild）

**目标**：从"打分制"升级到"定价制"。  
**为什么重要**：当前 `fundamental_analysis.py` 能告诉你一家公司"基本面不错"，但不能告诉你"这个价格是否值得买"。这是最大的缺口。

### 2.1 同业比较（Peer Comparison）

```
[新模块] valuation.py

功能：
1. 按行业分组（industry grouping）
2. 计算同行业 PE/PB/PS 的 中位数（median）、25th/75th 分位
3. 当前标的在同行业中的 分位排名（percentile rank）
4. 输出：溢价率 = (标的PE - 行业中位PE) / 行业中位PE
```

**数据来源**：akshare `stock_info_a_code_name()`获取行业分类 + 已有 `realtime.json` 中的 PE/PB。

### 2.2 历史估值分位（Historical Valuation Percentile）

```
[新增到 valuation.py]

功能：
1. 加载 3-5 年的 PE/PB 历史数据
2. 计算当前值在历史分布中的 百分位（percentile）
3. PE 处于历史 20% 以下 → 低估区域
4. PE 处于历史 80% 以上 → 高估区域
```

**这一项可能是最有投资价值的改进之一**：它直接回答"这只股票相对于自己的历史是贵还是便宜？"。

### 2.3 简化 DCF 模型（Simplified DCF）

```
[新增到 valuation.py]

输入：
- 近 3 年平均自由现金流（FCF）
- 预期增长率（默认 = 近 3 年营收复合增长率，上限 15%）
- 折现率（WACC，默认 10%，可按行业调整）
- 永续增长率（默认 3%）

输出：
- 内在价值估算（Intrinsic Value）
- 当前价 vs 内在价值的 溢价/折价率
- 安全边际（Margin of Safety）= (内在价值 - 当前价) / 内在价值
```

**限制声明**：DCF 对输入假设极其敏感。增长率变化 2% 可能导致估值变化 30%+。因此输出应展示 **三种情景（乐观/中性/悲观）**，而非单一数字。

### 2.4 综合估值评级

将以上三个维度合并成一个 **估值仪表盘（Valuation Dashboard）**：

| 指标 | 状态 | 含义 |
|------|------|------|
| 同业PE分位 | 低于25% | 相对同行便宜 |
| 历史PE分位 | 低于20% | 相对自身历史便宜 |
| DCF安全边际 | > 30% | 有足够的估值缓冲 |
| 综合 | 三项中至少两项达标 | "估值合理"信号 |

**影响的文件**：新建 `valuation.py`，`agent.py` 新增 API 路由，UI 新增估值卡片。

---

## Phase 3：模型升级（Model Enhancement）

**目标**：不追求"预测准确"，追求"信号有用"。

### 3.1 集成模型（Ensemble）

| 组件 | 用途 |
|------|------|
| XGBoost（现有） | 非线性特征交互 |
| LightGBM（新增） | 更快、支持类别特征 |
| Ridge/Lasso（新增） | 线性基线，防止树模型过度非线性 |
| **集成方式** | 加权平均或 Stacking（用一个简单的逻辑回归做元学习器） |
| **分歧度（Disagreement）** | 当三个模型方向不一致时，标记为"高不确定性（High Uncertainty）"，建议观望 |

**影响的文件**：修改 `model_price_predictor.py`，新增 `model_ensemble.py`。

**安装新依赖**：`pip install lightgbm`

### 3.2 市场状态检测（Regime Detection）

这是 **环境适应性（environment coverage）** 的核心。

```
[新模块] regime_detector.py

方法：
1. 用 MA20 vs MA60 的关系 + 波动率（ATR 百分比）构建简单 regime 标签：
   - 牛市（Uptrend）：MA20 > MA60 且 ATR% < 3%
   - 强牛（Strong Bull）：MA20 > MA60 且连续 N 天新高
   - 熊市（Downtrend）：MA20 < MA60 且 ATR% > 3%
   - 震荡（Sideways）：MA20 ≈ MA60（差距 < 1%）
   - 高波动（High Volatility）：ATR% > 5%（黑天鹅/恐慌期）

2. 对每个 regime 使用不同的模型参数或阈值：
   - 牛市：动量因子权重↑、均值回归因子权重↓
   - 熊市：做空信号解禁（如果策略允许）、止损收紧
   - 震荡：降低交易频率、增大网格间距
   - 高波动：全面减仓、只保留核心持仓

3. 标的级别 + 大盘级别双层检测
```

**影响的文件**：新建 `regime_detector.py`，`model_price_predictor.py` 和 `model_xgboost.py` 根据 regime 调整参数。

### 3.3 横截面相对强弱（Cross-sectional Relative Strength）

当前模型只对单只股票做时间序列预测。加入 **横截面排序（cross-sectional ranking）**：

```
在 N 只关注列表/板块标的中：
1. 对每只标的计算 近 20 日收益率、动量得分、情绪得分
2. 按综合得分排序
3. 输出"相对强度排名（Relative Strength Rank）"
4. 建议：在排名前 20% 中选标的，而非绝对预测"涨跌"
```

**为什么有用**：相对排名（谁比谁强）比绝对预测（明天涨几个点）更稳定、更可验证。

### 3.4 不确定性量化（Uncertainty Quantification）

当前模型只输出一个点预测（point estimate）。加入 **置信区间（confidence interval）**：

```
方法 1（简单）：用 Walk-forward 各轮的预测值计算 标准差
方法 2（进阶）：Quantile Regression — 直接预测 10th/50th/90th 分位数

输出变化：
旧：预测收盘价 ¥445.02 (+0.18%)
新：预测收盘价 ¥445.02 (+0.18%)
    80% 置信区间：¥435 ~ ¥455
    模型不确定性：中等
```

**为什么重要**：一个"预测 +2% 但不确定性 ±5%"的信号和"预测 +2% 但不确定性 ±0.5%"的信号，决策含义完全不同。

---

## Phase 4：风控与组合层（Risk Management & Portfolio Layer）

**目标**：从"分析单只股票"到"管理一个组合"。

### 4.1 仓位建议引擎（Position Sizing Engine）

```
[新模块] position_sizer.py

输入：
- 总投资金额
- 当前持仓
- 各标的的模型不确定性
- 各标的的估值评级

输出：
- 建议仓位比例（如：茅台 15%、宁德 10%、ETF 40%、现金 35%）
- 约束：单标的不超过 20%、同行业不超过 30%
- 根据 regime 调整：高波动期自动降低总仓位建议
```

### 4.2 相关性监控（Correlation Monitor）

```
[新增到 position_sizer.py 或独立模块]

功能：
1. 计算关注列表内所有标的的 60 日滚动相关系数矩阵
2. 标记高相关组合（> 0.8）：警告"你以为分散了但其实没有"
3. 建议替换标的以降低组合相关性
```

### 4.3 回撤监控与预警（Drawdown Monitor）

```
[新增功能到 prediction_tracker.py]

功能：
1. 跟踪每只持仓从建仓以来的最大回撤
2. 触发预警规则：
   - 单标的回撤 > 15% → 黄色警报
   - 单标的回撤 > 25% → 红色警报（建议评估是否止损）
   - 组合级回撤 > 10% → 建议减仓
3. 通过 Telegram Bot 发送预警
```

---

## Phase 5：完整回测框架（Full Backtesting Framework）

**目标**：在投入真金白银之前，在历史上验证策略。

### 5.1 回测引擎集成

```
pip install backtrader

[新模块] backtest_engine.py

功能：
1. 定义策略：买入条件、卖出条件、仓位规则
2. 输入：历史 OHLCV + 模型信号
3. 包含成本模型：
   - 佣金：万 2.5（双向）
   - 印花税：千 0.5（卖出）
   - 滑点：0.1%（默认）
4. 输出：
   - 年化收益（Annualized Return）
   - 最大回撤（Max Drawdown）
   - 夏普比率（Sharpe Ratio）
   - 卡尔马比率（Calmar Ratio = Return / Max Drawdown）
   - 胜率（Win Rate）
   - 盈亏比（Profit/Loss Ratio）
5. 与基准比较：至少跑 沪深300 作为基准
```

### 5.2 策略模板

```
[内置策略] backtest_strategies.py

Strategy 1: ML 动量策略
- 买入：价格回归模型预测 > +1%，且 regime = Uptrend
- 卖出：预测 < -0.5%，或 stop-loss 触发
- 仓位：等权分配前 5 名

Strategy 2: 估值 + 动量混合策略
- 买入：估值处于历史低 30% 分位，且技术面非下跌趋势
- 卖出：估值回到历史高 70% 分位，或基本面恶化
- 仓位：按安全边际大小加权

Strategy 3: 纯指数定投基准
- 每月固定金额买入 沪深300 ETF
- 用于对比：你的策略必须跑赢这个才有意义
```

---

## Phase 6：Telegram 与 UI 集成（Integration）

**目标**：让以上所有改进都能通过 Telegram 和 Web UI 使用。

| 功能 | Telegram 命令 | Web UI |
|------|-------------|--------|
| 估值报告 | `/valuation 300750` | 股票分析页新增"估值"标签 |
| 市场状态 | `/regime` | 仪表盘新增 regime 指示器 |
| 仓位建议 | `/portfolio` | 组合管理页面 |
| 回撤预警 | 自动推送 | 预警通知弹窗 |
| 回测报告 | `/backtest momentum` | 回测结果页面（收益曲线图） |

---

## 实施优先级与时间线

| Phase | 名称 | 预计工作量 | 对分析质量的提升 | 建议顺序 |
|-------|------|-----------|----------------|---------|
| **Phase 2** | 估值体系 | 3–5 天 | ★★★★★ | **第 1 优先** |
| **Phase 1** | 数据层加固 | 2–3 天 | ★★★★☆ | 第 2 优先 |
| **Phase 3.2** | Regime 检测 | 1–2 天 | ★★★★☆ | 第 3 优先 |
| **Phase 3.1** | 集成模型 | 2–3 天 | ★★★☆☆ | 第 4 优先 |
| **Phase 3.4** | 不确定性量化 | 1 天 | ★★★☆☆ | 第 5 优先 |
| **Phase 4** | 风控与组合 | 3–4 天 | ★★★★☆ | 第 6 优先 |
| **Phase 5** | 回测框架 | 3–5 天 | ★★★★★ | 第 7 优先 |
| **Phase 6** | 集成到 UI/Telegram | 2–3 天 | ★★☆☆☆ | 最后 |

**为什么估值排第一？**  
因为即使模型预测不改进一分，一个好的估值框架也能让你避免"在泡沫价格买入好公司"这个最常见的亏损原因。一个会做 DCF 的投资者，比一个有"95%准确率"ML 模型但不懂估值的投机者，长期胜算高得多。

---

## 新增模块总览

| 新模块 | 功能 | 依赖 |
|--------|------|------|
| `valuation.py` | 同业比较、历史分位、简化 DCF、综合估值评级 | akshare, pandas |
| `regime_detector.py` | 大盘 + 个股 regime 检测 | pandas, technical_analysis |
| `model_ensemble.py` | XGBoost + LightGBM + Ridge 集成 | xgboost, lightgbm, sklearn |
| `position_sizer.py` | 仓位建议、相关性监控 | pandas, numpy |
| `backtest_engine.py` | 策略回测与绩效评估 | backtrader, pandas |
| `backtest_strategies.py` | 预置策略模板 | backtest_engine |
| `data_quality.py` | 数据完整性校验与清洗 | pandas |

**新增 Python 依赖**：

```bash
pip install lightgbm backtrader
```

---

## 环境适应性矩阵（Environment Coverage Matrix）

改进后 Jarvis 应该如何应对不同的市场环境：

| 市场环境 | 当前 Jarvis | 改进后 Jarvis |
|----------|-----------|-------------|
| **牛市（Uptrend）** | 模型可能有效（顺趋势） | Regime 检测确认 → 动量策略激活、仓位建议偏高 |
| **熊市（Downtrend）** | 模型可能反复错误 | Regime 检测 → 自动降低仓位建议、止损收紧、不确定性标高 |
| **震荡（Sideways）** | 模型信号频繁翻转 | Regime 检测 → 降低交易频率、更依赖估值而非动量 |
| **黑天鹅（Black Swan）** | black_swan_detector 提供预警 | 高波动 regime → 全面减仓建议、关注避险资产（如国债 ETF）、Telegram 自动预警 |
| **板块轮动（Sector Rotation）** | scanner 能发现热点 | 行业指数数据 → 板块强弱排名 → 横截面选股 |
| **政策驱动（Policy-driven）** | LLM 新闻摘要 | 增强舆情源 → 政策关键词检测 → 受影响行业映射 |

---

## 验收标准（How to Know We're Improving）

不要用"感觉更好了"来衡量。用数据：

| 指标 | 当前基线 | Phase 2 后目标 | Phase 5 后目标 |
|------|---------|---------------|---------------|
| 价格 MAE（百分点） | 1.5–2.5 | 1.2–2.0 | 1.0–1.8 |
| 方向准确率 | 45–55% | 50–58% | 55–62% |
| 估值评级覆盖率 | 0%（无估值） | 100%（所有关注列表） | 100% |
| Regime 检测 | 无 | 有（大盘 + 个股） | 有 + 回测验证 |
| 回测夏普比率 | 未测 | 未测 | > 1.0（策略有意义） |
| 最大回撤控制 | 无 | 有预警 | < 15%（策略级） |

**诚实声明**：以上目标都是"努力方向"，不是"保证结果"。金融市场的非平稳性意味着在任何时间段，实际表现都可能不达标。关键不是追求完美数字，而是建立 **持续改进的流程（continuous improvement process）**。

---

## 与现有文档的关系

| 本章内容 | 相关文档 |
|----------|---------|
| 数据层改进 | [data-layer-impl.md](../../implementation/stock/data-layer-impl.md) |
| 模型升级 | [ml-pipeline-impl.md](../../implementation/stock/ml-pipeline-impl.md) |
| 估值体系 | [ch3-valuation-methods.md](ch3-valuation-methods.md) |
| 风控 | [ch5-risk-management.md](ch5-risk-management.md) |
| 模型局限性 | [ch7-quantitative-methods.md](ch7-quantitative-methods.md) |
| Jarvis 工作流 | [ch8-jarvis-workflow.md](ch8-jarvis-workflow.md) |
| 当前模型评估 | [stock-prediction-impl.md](../../implementation/stock/stock-prediction-impl.md) |
| Telegram 集成 | [telegram-bot-guide.md](../../guides/telegram-bot-guide.md) |

---

## 最后的话：路线图不是终点

这份路线图是"当前认知下的最佳计划"。实施过程中你会发现：

- 某些改进比预期难（特别是数据清洗——它永远比你想的脏）
- 某些改进比预期没用（模型集成可能只提升 1-2 个百分点）
- 某些你没想到的东西反而最有价值（也许只是"止损纪律"）

投资和工程一样：**迭代比完美重要（iteration over perfection）**。  
先做 Phase 2（估值），因为它不需要任何 ML 改进就能让你成为更好的投资者。  
然后一步步推进，每步都回测、验证、记录。

> 如果你只能从这份路线图中做一件事，就做 **历史 PE 分位数**。  
> 它只需要一个 `pandas.Series.rank(pct=True)`，却能让你避免在最贵的时候买入。

---

*本章为工程规划文档，所有目标数字均为估计值，不构成投资收益承诺。*
