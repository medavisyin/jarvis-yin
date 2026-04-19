# 量化方法与机器学习的边界 — 模型能做什么、不能做什么

> **本章至关重要（CRITICAL）**：许多初学者把机器学习（Machine Learning, ML）当成“印钞机”。本章会尽量做到 **100% 诚实（brutally honest）**：既不贩卖焦虑，也不制造幻觉。  
> 读完你会更清楚：Jarvis 里的模型（models）适合扮演什么角色，以及 **绝对不该** 被怎样误用。

---

## 1. 什么是量化投资（Quantitative Investing）？

### 1.1 定义：用数学与数据做决策

**量化投资（quantitative investing）** 指的是：把投资问题尽量形式化为 **可计算的问题（computable problem）**，用 **统计模型（statistical models）**、**优化（optimization）**、**规则引擎（rule engines）** 或 **机器学习（ML）**，在历史数据（historical data）与未来不确定性（uncertainty）之间建立决策流程。

它不等同于“高频交易（high-frequency trading, HFT）”，也不等同于“深度学习（deep learning）”。量化是一个 **方法论谱系（spectrum）**：从简单的因子打分（factor scoring），到复杂的另类数据（alternative data）与执行算法（execution algorithms），都属于量化范畴。

### 1.2 历史与现实：那些“神话级”机构到底强在哪里？

当你听到 **Renaissance Technologies**（尤其是 **Medallion Fund**）、**Two Sigma**、**D. E. Shaw** 这类名字时，容易把“量化成功”简化成一句话：**“他们用 ML，所以他们赚钱。”**  
这句话 **最多只对一半**。

这些机构的成功通常来自 **复合优势（compound advantages）**，而不只是某个公开模型（public model）：

- **人才密度（talent density）**：大量 **PhD（博士）** 团队，横跨数学、统计、计算机、物理、信号处理等领域。  
- **数据壁垒（data moats）**：**专有数据（proprietary data）**、清洗管线（data pipelines）、标注体系（labeling）、对齐方式（alignment）往往比“模型名字”更关键。  
- **执行与基础设施（execution & infrastructure）**：微秒级（microsecond-level）或更低延迟的系统、托管（colocation）、风控（risk controls）、交易成本建模（transaction cost modeling）。  
- **资本与杠杆结构（capital & leverage structure）**：这会影响策略容量（capacity）、可承受回撤（drawdown tolerance）与融资约束（funding constraints）。  
- **研究流程（research process）**：严格的 **样本外测试（out-of-sample testing）**、防 **过拟合（overfitting）** 的文化、以及把“策略失效（strategy decay）”当作常态来管理。

### 1.3 你不是在跟他们竞争 —— 这没关系

作为个人投资者（retail investor）或小型团队，你 **通常不是在同一个竞技场里比赛**。  
这不意味着你“没机会”，而是意味着：**你的优势（edge）必须不同**：

- 你可以承受 **更长的时间跨度（longer time horizon）**，不被季度排名（quarterly performance pressure）绑架。  
- 你可以只做 **更少、更懂（fewer names, deeper understanding）** 的研究，而不需要把 alpha（超额收益）摊到几千只股票上。  
- 你可以把工具当作 **探索（exploration）与风控（risk management）** 的助手，而不是必须每天产出交易信号（trading signals）的机器。

**结论（takeaway）**：量化机构的成功，不能简单迁移为“我也训练一个 XGBoost 就能持续战胜市场”。你要学的是 **量化思维（quantitative thinking）**：假设、验证、成本控制、以及对自己未知的敬畏。

---

## 2. 机器学习（ML）在股票分析里 **能做什么**？

下面列的是 ML **相对擅长** 的方向。请注意：擅长 ≠ 能稳定赚钱（profitable）。

### 2.1 模式识别（Pattern Recognition）

市场数据里存在大量 **非线性关系（non-linear relationships）**。  
传统线性回归（linear regression）或肉眼扫图，很容易漏掉 **交互效应（interaction effects）** 与 **阈值效应（threshold effects）**。  
树模型（tree-based models，如 **XGBoost** / **LightGBM** / **Random Forest**）在捕捉这类结构时往往更顺手。

但要记住：识别到模式，只说明“历史里像过”，不保证“未来还会像”。

### 2.2 回测自动化（Backtesting Automation）

当你有一个假设（hypothesis），ML 与脚本化流程可以帮助你在 **横截面（cross-section）** 或 **时间序列（time series）** 上快速做 **实验矩阵（experiment matrix）**：换因子、换窗口、换标的池（universe）。

价值在于 **加速科学方法（scientific method）**，而不是自动产生圣杯（holy grail）。

### 2.3 风险信号检测（Risk Signal Detection）

ML 在“找异常（anomaly）”上常常比“预测涨跌（direction forecasting）”更靠谱：  
例如成交量突增（volume spikes）、相关性断裂（correlation breaks）、波动率结构变化（volatility regime shifts）。

这类任务更接近 **监测（monitoring）** 与 **预警（early warning）**，而不是“告诉你明天必涨”。

### 2.4 特征重要性（Feature Importance）——但要读对含义

**特征重要性（feature importance）** 能回答的通常是：在该模型、该数据切片（slice）与训练设定下，哪些输入对拟合贡献更大。  

它 **不自动等价于**：

- **可交易因子（tradable factor）**  
- **因果机制（causation）**  
- **未来仍有效（future persistence）**

换句话说：它更像“模型内部的归因（attribution）”，而不是“市场真理排名”。

### 2.5 分类（Classification）：市场状态（market regime）

把市场切成 **牛市 / 熊市 / 震荡（bull / bear / sideways）** 这类 **状态（regime）**，有时比预测单只股票收益更容易产生 **可解释（interpretable）** 的框架。  
但 regime labeling 本身也充满 **主观阈值（subjective thresholds）** 与 **滞后（lag）** 问题。

### 2.6 异常检测（Anomaly Detection）

对价格—成交量（price/volume）联合分布做异常点识别，适合用于：

- **风控（risk control）**  
- **舆情/新闻异常放大（narrative amplification）** 的二次确认  
- **数据质量检查（data quality checks）**（很多“神奇 alpha”最后发现是数据错了）

---

## 3. 机器学习（ML）在股票分析里 **不能做什么**？

这一节是“打破幻想”的核心。请逐条对照你对 Jarvis 的期待。

### 3.1 不能“确定性地预测未来”（No Certain Future）

金融市场是 **随机过程（stochastic process）** 主导的系统，受信息流（information flow）、参与者行为（participant behavior）与制度变化（institutional changes）影响。  
**确定性（determinism）** 在哲学上不成立，在统计上也不成立：你只能讨论 **概率（probability）**、**期望（expectation）**、**分布尾部（tail risk）**。

任何把点预测（point forecast）当成“命运”的行为，都是在踩雷。

### 3.2 不能假设“稳定战胜市场”（No Consistent Market-Beating）

如果“用一个简单 **XGBoost** + 公开 **OHLCV** 特征”就能稳定打败市场，那么 **套利（arbitrage）** 与竞争会快速让边缘消失。  
现实更常见的是：**alpha 衰减（alpha decay）**、**拥挤交易（crowded trades）**、以及 **结构性变化（structural breaks）**。

### 3.3 很难处理 **制度切换（Regime Change）**

在牛市（bull market）训练出来的规律，可能在熊市（bear market）全面失效。  
这不是“模型不够大”，而是 **数据生成机制（data generating process）** 变了。  
术语上叫 **非平稳（non-stationarity）** 与 **分布漂移（distribution shift）**。

### 3.4 不理解因果（No Causation），只有相关（Correlation）

ML 默认找到的是 **相关性（correlation）**。金融市场里 **虚假相关（spurious correlation）** 非常多：  
两个序列碰巧同步、共同受第三个变量驱动、或仅仅是 **多重检验（multiple testing）** 下的幸存者。

把相关当因果，会让你在叙事上“自洽”，在账户上“失血”。

### 3.5 不能替代人类判断（No Replacement for Judgment）

例如：“监管（regulation）会不会突变？”“行业政策（industrial policy）往哪走？”“管理层是否诚信？”  
这些问题涉及 **制度分析（institutional analysis）**、**公司治理（corporate governance）** 与 **博弈（game theory）**，不是仅靠时间序列特征就能回答的。

### 3.6 无法为“前所未有事件”提供训练样本（No Training Data for Unprecedented Events）

新冠疫情（COVID）、战争（war）、银行体系危机（banking crises）这类 **尾部事件（tail events）** 的关键问题是：**历史样本极少**，且每次机制不同。  
模型最多给你“压力情景（stress scenario）下的脆弱性提示”，不能给你“预言书”。

---

## 4. 对 Jarvis 现有模型的 **冷静体检（Critical Evaluation）**

下面评价针对仓库中常见脚本（位于 `scripts/stock/`）。数字会随市场阶段、标的、特征版本而变化；这里给的是 **量级上的诚实区间（honest ranges）** 与 **解释框架（interpretation frame）**。

### 4.1 方向分类器（Direction Classifier）：`model_xgboost.py`

#### 它到底在做什么？

这是一个典型的 **多分类（multi-class classification）** 任务：把未来约 **5 个交易日（5-day horizon）** 的价格方向切成类似 **涨 / 平 / 跌（up / flat / down）** 的类别（具体阈值以实现为准）。  
输入通常是 **公开技术面因子（technical indicators）** 与 **历史行情特征（historical market features）** 的组合。

#### Walk-forward validation（滚动前推验证）下常见表现

在严谨 **walk-forward**（避免用未来训练过去）的设置里，**方向准确率（direction accuracy）** 往往落在 **45%–55%** 这种区间并不稀奇。

#### 诚实评估：它可能“略好于随机”，但不等于可交易

对“涨/跌”二分类而言，随机基线（random baseline）大约是 **50%**。  
三分类（加入“平”）会让指标读起来更复杂：**准确率（accuracy）** 也可能被“预测很多横盘类”这种策略人为抬高或扭曲。

因此，更该问的问题是：

- 在 **不同市场状态（regimes）** 下是否稳定？  
- 预测概率的 **校准（calibration）** 如何？  
- 错误类型是否对称？（错在“小跌当大涨”比错在“小波动”更致命）

#### 为什么噪声这么大？

**日频收益（daily returns）** 的信噪比（signal-to-noise ratio）极低：  
大量波动来自 **微观结构噪声（microstructure noise）**、风险偏好（risk appetite）变化、以及不可观测冲击（unobserved shocks）。

#### 你应该怎么用它？

把它当作 **众多输入之一（one input among many）**：用于提示“短期动能/结构是否与你的基本面结论冲突”，而不是当作 **交易触发器（trade trigger）**。

---

### 4.2 价格回归器（Price Regressor）：`model_price_predictor.py`

#### 它到底在做什么？

它通常输出 **下一日（next-day）** 的 close/high/low 的相对变化（常见形式是 **百分比收益 percentage returns** 或类似尺度，以实现为准）。  
本质是 **回归（regression）**：拟合一个条件期望（conditional expectation）。

#### Walk-forward 下常见误差量级

**平均绝对误差（MAE, mean absolute error）** 常见可能落在 **1.5–2.5 个百分点（percentage points）** 的量级（随标的波动率而变）。

#### 诚实评估：误差可能与“日常波动噪声”同阶

如果一只股票日常日波动（daily volatility）常在 **±3%** 附近，那么 **±2%** 的误差并不意味着“看得很准”，而更像：模型抓到了一点 **条件均值（conditional mean）** 的倾向，但仍被噪声淹没。

#### 关于价格限制（price limits）与“不可能预测值”

A 股存在 **涨跌停（price limit）** 等交易制度约束。若模型在训练分布之外产生极端输出，就可能出现 **不现实的收益率（implausible returns）**（例如你提到的 **-25%** 这类离谱值）。  
因此加入 **clamp（夹紧/限制）** 是对 **模型外推（extrapolation）** 的现实修正，但这不等于“模型变准了”，只是“输出变合理了”。

#### 你应该怎么用它？

把它当作 **粗糙方向提示（rough directional hint）**，而不是 **价格目标（price target）**。  
任何下单（order placement）都必须回到：估值区间（valuation band）、催化剂（catalyst）、风险回报（risk/reward）与仓位规则（position sizing）。

---

### 4.3 为什么这些限制 **必然存在**（不是“再调参就好”）

#### （1）特征几乎都是公开的（Public Features）

**OHLCV** 与常见技术指标（TA indicators）属于 **公共信息（public information）**。  
在有效市场假说（EMH）的强版本不成立的世界里，公共信息仍可能定价，但 **可重复套利（repeatable arbitrage）** 的空间往往很薄。

#### （2）训练窗口仍然有限（当前 500 个交易日）

一年左右的数据，对复杂非平稳过程来说 **样本量（sample size）** 往往不足。  
你会在“拟合历史”与“捕捉长期结构”之间左右为难。

#### （3）缺少另类数据（No Alternative Data）

没有卫星图（satellite imagery）、信用卡聚合数据（card spend aggregates）、高质量社交情绪（social sentiment）等，意味着你主要在 **红海信息域（red ocean information）** 竞争。

#### （4）单一模型结构（Single Model）

工业界常见的是 **集成（ensemble）**、多模型分歧（model disagreement）、以及分层决策（hierarchical decisions）。单一模型更容易 **过拟合（overfit）** 某个历史片段。

#### （5）没有执行层模型（No Execution Model）

从 **预测（prediction）** 到 **成交（fill）** 之间隔着：

- 手续费（commissions）  
- 滑点（slippage）  
- 冲击成本（market impact）  
- 订单类型（order types）与流动性（liquidity）

预测提升 1%，执行可能吃掉 2%。

#### （6）幸存者偏差（Survivorship Bias）

如果你只在“现在还活着的标的”上验证，历史里退市、合并、长期阴跌消失的股票可能系统性缺席，导致 **回测虚高（inflated backtest）**。

---

## 5. “变得更好”的路线图 —— **诚实分层（Honest Roadmap）**

### 5.1 Tier 1：合理、性价比高的改进（Reasonable Improvements）

- **集成方法（Ensemble methods）**：XGBoost + LightGBM + Random Forest，再看 **分歧度（disagreement）** 是否可作为“不确定性（uncertainty）”信号。  
- **特征工程（Feature engineering）**：加入更可执行的微观结构代理变量（microstructure proxies），例如买卖价差（bid-ask spread）相关指标（若数据可得）。  
- **横截面模型（Cross-sectional models）**：预测 **相对强弱（relative performance）**（A 相对 B）有时比预测绝对收益更稳。  
- **严肃回测框架（Proper backtesting）**：使用 `backtrader` 或 `zipline` 等框架，把 **成本（costs）** 与 **约束（constraints）** 写清楚。  
- **制度检测（Regime detection）**：对不同市场状态用不同模型或不同阈值，本质是承认 **非平稳（non-stationarity）**。

### 5.2 Tier 2：更复杂，但仍可能“有上限”（More Sophisticated）

- **另类数据（Alternative data）**：新闻情绪（news sentiment, NLP）、资金流（fund flows）、内部人交易披露（insider filings）——但要处理 **前视偏差（look-ahead bias）** 与 **数据窥探（data snooping）**。  
- **深度学习（Deep learning）**：LSTM / Transformer 等时序模型（time series models）——通常需要更多数据、更强工程、以及更谨慎的验证。  
- **因子模型（Factor models）**：Fama-French、Barra 风格多因子风险模型（multi-factor risk models）用于解释收益来源与风险暴露（risk exposures）。  
- **组合优化（Portfolio optimization）**：均值方差（mean-variance）、风险平价（risk parity）、Black-Litterman 等，把“预测”变成“配置”。

### 5.3 Tier 3：专业级资源门槛（Professional-Grade）

- **逐笔/盘口级数据（Tick-level / order book data）**：研究微观结构与执行 alpha。  
- **事件驱动（Event-driven）**：财报惊喜（earnings surprises）、政策冲击（policy shocks）、持仓披露（holdings disclosure）。  
- **多资产（Multi-asset）**：债券（bonds）、商品（commodities）、外汇（FX）对股票风险溢价的交叉影响。

---

## 6. 回测（Backtesting）：正确姿势是什么？

### 6.1 回测是什么？

**回测（backtesting）** 指在历史数据上 **模拟（simulate）** 策略从信号生成到成交持仓的完整路径，以估计 **期望收益（expected return）**、**波动（volatility）**、**最大回撤（max drawdown）** 与 **尾部风险（tail risk）**。

### 6.2 第一大杀手：前视偏差（Look-ahead Bias）

**前视偏差** 指不小心用了 **未来信息（future information）**：例如用全天最高最低价做盘中决策、或在财报发布后“假装提前知道”。  
这是初学者回测“神级曲线”的头号来源。

### 6.3 幸存者偏差（Survivorship Bias）

只测“今天还活着的公司”，会系统性低估历史风险。

### 6.4 过拟合（Overfitting）

你在历史噪声里找到了一条“刚好贴合”的曲线。它对未来最擅长的事通常是：**让你亏钱（lose money）**。

### 6.5 样本外测试（Out-of-sample Testing）必须有

永远预留模型 **从未见过（never seen）** 的数据做最终判决。  
Jarvis 若采用 walk-forward，是在做对的方向上努力；但你仍要警惕：特征工程反复试错过多次后，**样本外也会被“间接污染”（indirect leakage via researcher degrees of freedom）**。

### 6.6 交易成本（Transaction Costs）要写进去

A 股常见讨论会涉及佣金如 **万 2.5（0.025%）** 量级（以券商为准），但真实成本还包括 **滑点（slippage）** 与 **冲击（impact）**。  
高频换手策略对成本极其敏感。

### 6.7 纸上交易（Paper Trading）是必要桥梁

至少 **3 个月+** 的真实行情、假资金流程，用来检验：信号是否可执行、系统是否稳定、你是否能遵守纪律。

---

## 7. Alpha 衰减（Alpha Decay）：为什么“秘密策略”才是常态？

**Alpha** 可以理解为相对基准（benchmark）的超额收益来源。  
但 alpha 不是永久资产：一旦发现的人变多，交易变拥挤（crowded），边缘会被套利到变薄，甚至变成 **风险因子暴露（risk factor exposure）**。

这也是为什么顶级量化机构对策略细节高度保密：不是小气，是 **商业生存（survival）**。

### 7.1 对 Jarvis 使用者的直接含义

公开指标（MACD、RSI、均线 MA）不是“没用”，但它们更像 **市场语言（market language）**，而不是 **私有 alpha（proprietary alpha）**。  
你要学会：用它们沟通、定位、风控，而不是幻想“别人不懂只有我懂”。

---

## 8. 诚实的结论（The Honest Conclusion）

- **ML 用于股价预测** 更适合定位为 **探索工具（exploration tool）**，而不是 **自动执行系统（execution system）**。  
- 用它生成 **假设（hypotheses）**：例如“异常放量 + 基本面未恶化”是否值得深入读财报与公告，而不是生成“必买信号”。  
- 个人投资者的真正优势往往来自：**耐心（patience）**、**长期主义（long time horizon）**、以及不被短期排名逼迫的仓位节奏。  
- 长期来看，最稳健的“模型”常常仍是：**以合理价格买入优质企业（buy quality at reasonable prices）并长期持有（hold for years）**。  
- Jarvis 更适合帮助你 **筛选（screen）**、**监控（monitor）**、**结构化整理信息（structure information）**；最终投资决策必须回到 **你自己的原则（your principles）**。

---

## 9. 自测清单（别骗自己）

在把任何模型输出当真之前，问自己：

1. 我是否理解该模型的 **标签定义（label definition）** 与预测 horizon？  
2. 我是否检查过 **分 regime** 的表现，而不是只看全样本准确率？  
3. 我是否把 **成本与可执行性** 纳入决策？  
4. 我是否能用 **非模型证据**（商业模式、护城河 moat、财务质量）解释这笔投资？  
5. 如果模型明天删除，我还会买吗？

如果你在第 5 题犹豫，那你买的可能不是公司，而是 **安慰剂（placebo）**。

---

## 10. 最后一句话（把期待放到正确位置）

量化方法与 ML 会让你更像 **工程师型投资者（engineer-investor）**：用证据约束直觉。  
但它们不会把你变成 **印钞机（money printer）**。  
市场会奖励谦逊、纪律与持续学习 —— 这听起来不性感，但这是真的。
