# 股票投资学习路径 — Stock Investing Learning Track

> 面向 **完全零基础**、希望系统成长为 **合格 A 股投资者** 的学习序列。  
> 技术名词保留 **英文（括号）** 说明，风格与 Jarvis 其他学习文档及 [股票使用指南](../../guides/stock-usage-guide.md) 一致。

---

## 本路径教什么（Overview）

本路径帮助你建立 **可复用的投资认知框架**：从 **股票市场（stock market）** 与 **交易规则（trading rules）** 出发，学会阅读 **财务报表（financial statements）** 与核心 **财务比率（financial ratios）**，理解 **估值（valuation）**、**技术分析（technical analysis）** 的适用边界，掌握 **风险管理（risk management）** 与 **投资心理（investor psychology）**，并了解 **量化（quantitative）** 与 **机器学习（machine learning, ML）** 能做什么、不能做什么。最后一章把知识落到 **Jarvis 实战工作流（workflow）** 上，与项目内脚本一致。

**重要声明**：教育内容 **不构成** 任何 **投资建议（investment advice）**。A 股波动大、政策与流动性影响显著；历史表现不保证未来收益。请只用你能承受损失的资金学习与实践。

---

## 先修要求（Prerequisites）

| 项目 | 说明 |
|------|------|
| **数学** | 会四则运算、百分比、简单比例即可；不要求高等数学。 |
| **金融背景** | **不需要**。本路径从零解释术语。 |
| **软件** | 若跟做 Jarvis 实战章节，需能运行 Python、阅读 Markdown 报告（见 [股票使用指南](../../guides/stock-usage-guide.md)）。 |
| **心态** | 接受「多数散户长期跑输指数」的事实，愿意用 **模拟盘（paper trading）** 或小资金试错。 |

---

## 章节目录（10 章）

| # | 章节 | 文件 | 你将学到 |
|:-:|------|------|----------|
| 1 | **股票市场基础** — Stock Market Basics | [ch1-stock-market-basics.md](ch1-stock-market-basics.md) | 股票本质、一级/二级市场、A 股交易所与板块、涨跌停、T+1、交易时段与集合竞价、代码规则、ST、ETF、OHLCV、PE/PB/市值、主要指数、新手防亏原则 |
| 2 | **读懂财务报表** — Reading Financial Statements | [ch2-financial-statements.md](ch2-financial-statements.md) | 三大表逻辑、利润表/资产负债表/现金流量表、关键比率、质量公司与红旗信号、与 Jarvis `fundamental_analysis` 的对应关系 |
| 3 | **估值方法论** — Valuation Methods | [ch3-valuation-methods.md](ch3-valuation-methods.md) | 绝对估值与相对估值、DCF 直觉、PEG、行业比较、A 股常见估值陷阱 |
| 4 | **技术分析基础** — Technical Analysis Fundamentals | [ch4-technical-analysis.md](ch4-technical-analysis.md) | 趋势、支撑阻力、均线、MACD/RSI/KDJ/布林带的解读与局限 |
| 5 | **风险管理与投资心理** — Risk Management & Psychology | [ch5-risk-management.md](ch5-risk-management.md) | 仓位、止损、分散化、行为偏差、杠杆与衍生品风险 |
| 6 | **投资策略体系** — Investment Strategies | [ch6-investment-strategies.md](ch6-investment-strategies.md) | 价值投资、成长投资、指数化、行业轮动等框架与适用场景 |
| 7 | **量化方法与机器学习的边界** — Quantitative Methods & ML Limitations | [ch7-quantitative-methods.md](ch7-quantitative-methods.md) | 回测过拟合、特征漂移、标签定义；为何 ML 不是印钞机 |
| 8 | **构建你的分析工作流** — Building Your Analysis Workflow (Jarvis) | [ch8-jarvis-workflow.md](ch8-jarvis-workflow.md) | 数据刷新 → 技术 → 基本面 → 情绪 → ML → LLM 综合；检查清单 |
| 9 | **增强路线图** — Enhancement Roadmap | [ch9-enhancement-roadmap.md](ch9-enhancement-roadmap.md) | 6 阶段工程计划：估值重建、数据加固、Regime 检测、集成模型、风控组合、回测框架；环境适应矩阵；验收标准 |
| 10 | **A 股市场深度解析** — A-share Deep Dive | [ch10-astock-deep-dive.md](ch10-astock-deep-dive.md) | A 股 vs 全球市场差异、政策市、估值扭曲、受美股/全球影响的板块、不受影响的板块、A 股常见陷阱、Jarvis 扫描器为何"全部不宜买入" |

---

## 建议阅读顺序（Suggested Reading Order）

**推荐按章节 1 → 10 顺序通读。** 每一章在后文会用到前面的概念（例如不懂 **市盈率 PE（price-to-earnings ratio）** 就读估值章会很吃力）。Ch.9 是 Jarvis 工程路线图，Ch.10 是 A 股特色深度解析——前 8 章的知识储备是读懂它们的前提。

若时间极度有限，可使用下面的 **新手快车道**；完整学习仍建议日后补读未读章节。

---

## 新手快车道（Beginner Fast Track）

适合想 **尽快上手分析与风控**、再回头补细节的读者：

1. **[Ch.1 股票市场基础](ch1-stock-market-basics.md)** — 先搞懂规则与术语，避免「看不懂行情软件」。  
2. **[Ch.3 估值方法论](ch3-valuation-methods.md)** — 建立「贵不贵」的尺子。  
3. **[Ch.5 风险管理与投资心理](ch5-risk-management.md)** — 先学会不输大钱，再谈赚。  
4. **[Ch.8 构建分析工作流](ch8-jarvis-workflow.md)** — 把工具链跑通，形成习惯。  
5. **[Ch.9 增强路线图](ch9-enhancement-roadmap.md)** — 了解 Jarvis 下一步怎么升级。

> 快车道 **跳过** 财务报表精读（Ch.2）会削弱你判断公司质量的能力；建议 8 章全部补齐。

---

## 与其他学习路径的交叉引用（Cross-References）

| 你想深入的能力 | 建议同步学习 |
|----------------|--------------|
| **XGBoost**、特征、训练/验证拆分、过拟合 | [Machine Learning 学习路径](../machine-learning/) — 尤其 [XGBoost 深入](../machine-learning/xgboost-gradient-boosting.md) 与 [特征工程与技术分析](../machine-learning/feature-engineering-ta.md) |
| **RAG**、向量检索、如何把研报/笔记纳入分析上下文 | [RAG 学习路径](../rag/) — 从 [核心概念](../rag/ch1-rag-concepts.md) 到 [混合检索与重排](../rag/hybrid-search-reranking.md) |

Jarvis 股票模块中，**技术面** 与 **ML 预测** 依赖经典 ML；**Agent** 侧可用 RAG 检索你自己的知识库。投资结论仍须 **人工复核（human-in-the-loop）**。

---

## Jarvis 相关文档（Project Docs）

| 文档 | 用途 |
|------|------|
| [股票使用指南（中文）](../../guides/stock-usage-guide.md) | 命令行、Web UI、数据目录、完整日课工作流 |
| [股票模块实现说明](../../implementation/stock/README.md) | 脚本职责与架构索引 |

---

*属于 [Jarvis 学习系列](../README.md)。祝学习顺利 — 慢即是快。*
