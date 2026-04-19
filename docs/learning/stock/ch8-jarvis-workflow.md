# 构建你的分析工作流 — 用 Jarvis 做聪明的投资者

> 如果你已经读完第 1–6 章，并理解了第 7 章关于 **机器学习（Machine Learning, ML）边界** 的冷静结论，那么本章目标只有一个：  
> **把知识落到流程（workflow）上** —— 让 Jarvis 成为你的 **研究助理（research assistant）**，而不是替你做决定的“黑箱老板”。

---

## 1. 先确立投资哲学（Your Investment Philosophy）

在使用 **任何工具（any tool）** 之前，请先回答下面四个问题。它们看起来“很虚”，但它们决定你会不会被短期噪声带偏。

### 1.1 你是哪一类投资者？（Which investor are you?）

回到第 6 章的策略谱系（strategy spectrum），你更靠近：

- **指数化长期（indexing / passive）**：把主要资金交给 **Beta（市场收益）**，追求简单与纪律。  
- **质量成长（quality growth）**：愿意为 **护城河（moat）** 与 **再投资回报率（reinvestment return）** 付合理溢价。  
- **价值回归（value / mean reversion）**：寻找 **安全边际（margin of safety）** 与 **错杀（mispricing）**。  
- **趋势/动量辅助（trend / momentum as overlay）**：用技术面管理节奏，但核心仍应落到基本面。

Jarvis 可以同时服务多种风格，但 **你必须选定主风格（primary style）**，否则你会在信号冲突时无所适从。

### 1.2 你的时间跨度（Time Horizon）是什么？

请用具体数字写出来：

- 你是按 **周（weeks）**、**月（months）** 还是 **年（years）** 来定义“持有期（holding period）”？  
- 你能接受多久 **浮亏（unrealized loss）** 而不推翻原计划？

**残酷事实（hard truth）**：时间跨度越短，**交易成本（transaction costs）** 与 **噪声（noise）** 越主导结果；Jarvis 的日频模型（daily models）也更难提供稳定优势。

### 1.3 你能承受多大风险（Risk Tolerance）？

不要只回答“我能承受波动”。请量化：

- 单只股票最大仓位（max position size）？  
- 组合最大回撤（max portfolio drawdown）触发什么动作（减仓、暂停、复盘）？

### 1.4 你每周能投入多少时间（Time Budget）？

诚实估算：

- **深度研究（deep dive）**：读财报、读公告、做竞争对比。  
- **维护监控（monitoring）**：看新闻、看模型健康度、看风险雷达。

如果时间很少，你的默认策略应更偏向 **低频、少交易（low turnover）**；否则你会被迫用“看盘面”替代“看公司”。

---

## 2. Jarvis 分析栈（The Jarvis Analysis Stack）

下面把 Jarvis 的核心脚本模块（位于 `scripts/stock/`）映射到你已学的章节概念。  
请记住第 7 章的底线：**模型输出是证据链的一环（one link in the chain of evidence）**，不是结论本身。

| Jarvis 模块（Module） | 它做什么（What it does） | 映射章节（Maps to） |
|------------------------|--------------------------|---------------------|
| `fetch_market_data.py` | 拉取 **OHLCV** 与新闻等市场数据（market data ingestion） | 第 1 章：市场与数据 |
| `fundamental_analysis.py` | ROE、PE、PB 等 **基本面评分（fundamental scoring）** | 第 2–3 章：财务与估值 |
| `technical_analysis.py` | MA、MACD、RSI 等 **技术信号（technical signals）** | 第 4 章：技术分析 |
| `sentiment.py` | 基于 **大语言模型（LLM）** 的新闻情绪（news sentiment） | 第 4 章：情绪层（sentiment layer） |
| `model_xgboost.py` | **5 日方向分类器（5-day direction classifier）**（涨/平/跌类） | 第 7 章：ML（谨慎使用） |
| `model_price_predictor.py` | **次日价格估计（next-day price estimate）**（回归，rough） | 第 7 章：ML（粗估） |
| `scanner.py` | 全市场 **AI 筛选（AI screening）** / 因子化初筛（factor-like screening） | 第 6 章：筛选与因子思维 |
| `llm_reasoning.py` | 把多源信息 **叙事整合（narrative synthesis）** 成可读报告 | 综合：把信号拼成故事，但仍需你验证 |

### 2.1 两个“容易被高估”的模块（Handle with Care）

- **`model_xgboost.py`**：把它当 **天气概率（weather probability）** 而不是“明天必下雨”。  
- **`model_price_predictor.py`**：把它当 **区间感（range intuition）** 而不是“目标价（price target）”。

### 2.2 两个“容易被低估”的模块（High ROI）

- **`fetch_market_data.py`**：数据质量决定一切；Garbage in, garbage out（垃圾进，垃圾出）。  
- **`fundamental_analysis.py`**：慢，但更接近 **可解释投资（explainable investing）**。

### 2.3 辅助模块（Optional but Useful）

仓库中还可能包含例如 **黑天鹅检测（black swan detection）**、**市场情绪（market sentiment）**、**预测追踪（prediction tracking）** 等脚本。把它们当作 **风险雷达（risk radar）** 与 **模型健康度（model health）** 监测，而不是交易触发器。

---

## 3. 工作流 1：选股（Finding Stocks to Research）

目标：从全市场噪声里，得到 **5–10 个候选名单（shortlist）**，每个都值得花 1–2 小时做深度分析。

### 3.1 从扫描器或主题开始（Scanner or Themes）

- 用 `scanner.py` 做 **初筛（initial filter）**：把 universe 缩小到可研究范围。  
- 或者用你关心的 **行业主题（sector themes）**（政策周期、库存周期、渗透率变化）先定方向，再交给扫描器验证“名单是否够硬”。

### 3.2 基本面硬过滤（Fundamental Filter）

建议把“硬条件”写死，避免盘中情绪改规则：

- **ROE（净资产收益率）** 是否长期稳定在阈值之上（例如 >15% 只是例子，行业差异极大）？  
- **杠杆（leverage）** 是否过高？现金流（cash flow）是否匹配利润（earnings quality）？  
- **估值（valuation）**：PE/PB 相对历史与同业是否 **离谱（nonsense）**？

在 Jarvis 中，这一步对应阅读 `fundamental_analysis.py` 产出，而不是只看一个总分。

### 3.3 技术面“排除法”（Technical Exclusion）

技术面在这里更适合回答：**“现在是不是明显糟糕的时机？”** 而不是“现在必涨”。

- 是否处于 **自由落体（free fall）** 结构（均线空头排列、关键均线下方且无企稳）？  
- 是否出现 **异常波动（abnormal volatility）** 但你找不到基本面解释？

如果技术结构极差，把它放进 **观察池（watchlist）** 而不是立即买入池。

### 3.4 新闻与叙事（News & Narrative）

用 `sentiment.py` / 新闻摘要快速扫 **红旗（red flags）**：

- 监管立案、重大诉讼、核心客户流失、审计非标意见等。  
- 情绪很负面不一定不买，但你需要 **可计算的风险补偿（risk compensation）**。

### 3.5 输出：候选清单（Shortlist Output）

你的 shortlist 每条应包含三句话（强制格式，防止自己糊弄自己）：

1. **商业模式一句话（business one-liner）**  
2. **你为什么现在关注它（catalyst or valuation）**  
3. **你最担心的失败模式（failure mode）是什么**

---

## 4. 工作流 2：买入前的深度分析（Deep Analysis Before Buying）

下面按顺序做。顺序的目的：先建立 **不可逆的事实（facts）**，再讨论 **价格（price）**。

### 4.1 刷新数据（Refresh Data）

在仓库根目录或项目约定目录下运行（以你的环境为准）：

```bash
python scripts/stock/fetch_market_data.py {SYMBOL}
```

把 `{SYMBOL}` 换成你的标的代码。  
你要确认：数据是否覆盖足够窗口、是否有缺失交易日、是否有明显异常值（outliers）。

### 4.2 读基本面报告：这是不是一门好生意？（Is it a good business?）

回答这些问题（比 PE 更重要）：

- 它如何赚钱（unit economics）？  
- 竞争壁垒来自哪里：规模、网络效应、牌照、转换成本、品牌？  
- 资本回报（ROIC）是否长期成立？

### 4.3 估值：便宜还是贵？（Cheap or Expensive?）

做三层对比（three-layer comparison）：

1. **相对自身历史（vs own history）**：PE/PB band。  
2. **相对同业（vs peers）**：注意会计口径一致性（accounting consistency）。  
3. **相对无风险利率（vs risk-free rate）**：风险溢价（equity risk premium）是否合理。

### 4.4 技术位置：现在是不是“好切入点”？（Good Entry?）

用 `technical_analysis.py` 回答的是 **节奏（timing）** 问题：

- 你是否在 **趋势（trend）** 与 **均值回归（mean reversion）** 之间自相矛盾？（很多初学者会）  
- 你的计划里是否有 **加仓规则（scaling rules）** 与 **止损规则（stop rules）**？

### 4.5 情绪层：新闻环境是否友好？（Sentiment）

阅读 `sentiment.py` / LLM 摘要时，重点找 **可验证事实** 而不是形容词。

### 4.6 ML：只当一个数据点（ML as One Data Point）

依次查看：

- `model_xgboost.py` 的方向概率：是否与你基本面结论冲突？冲突时，默认 **基本面优先（fundamentals first）**，但要检查你是否忽略了 **制度风险（regulatory risk）**。  
- `model_price_predictor.py` 的区间：是否提示 **短期过热（short-term overheating）**？

### 4.7 读 AI 综合报告：故事是否自洽？（Coherent Narrative?）

`llm_reasoning.py` 的价值是 **整合（integrate）**，但它可能 **幻觉（hallucinate）** 或 **过度总结（over-summarize）**。  
你必须做 **事实核对（fact check）**：关键数字回到原始数据与公告。

### 4.8 做出你的决定：对齐第 5 章的投资计划（Your Plan）

把决策写成一行 **投资命题（investment thesis）**：

- “我以 X 理由持有，触发 Y 条件则认错退出。”

没有 Y，你迟早会在震荡里被情绪接管。

---

## 5. 工作流 3：日常监控（Daily Monitoring）

### 5.1 通过 Telegram Bot 或 Web UI

具体命令以你的部署为准；常见思路是：

- `/train`：**日更模型（daily model refresh）**，并检查 **预测 vs 实际（predictions vs actuals）** 的偏差模式。  
- `/stock {symbol}`：对持仓做 **快速体检（quick health check）**。

### 5.2 模型健康度（Model Health Grades）

如果你看到类似 A/B/C/D 的分级，把它理解为 **“模型是否还在合理工作区间”**：

- **A/B**：可以继续当作辅助信号，但仍要 **交叉验证（cross-check）**。  
- **C/D**：把模型权重调低，偏向 **基本面与风控（fundamentals + risk）**。

模型变差有时不是“市场变了”，而是 **数据源变化（data drift）** 或 **标签噪声（label noise）** 变大。

### 5.3 市场层信号（Macro / Sentiment Gauges）

关注例如 **恐惧与贪婪指数（Fear & Greed）**、系统性风险提醒、黑天鹅雷达等。  
它们的价值是：**提醒你放慢（slow down）**，而不是告诉你“精确顶部底部”。

### 5.4 监控的节奏感（Cadence）

给个人投资者一个可执行节奏：

- **每天 10–15 分钟**：持仓新闻与风险雷达。  
- **每周 60–90 分钟**：shortlist 深度阅读与模型健康度复盘。  
- **每月一次**：交易日志回顾（见第 7 节）。

---

## 6. 工作流 4：卖出决策（When to Sell）

卖出比买入更难，因为它触发 **损失厌恶（loss aversion）** 与 **沉没成本（sunk cost）**。

### 6.1 三种“正确理由”（Three Good Reasons）

1. **投资逻辑被破坏（Thesis Broken）**  
   - 当初买入的核心假设被证伪：竞争格局、商业模式、政策环境、管理层可信度。  

2. **触发止损（Stop-loss Hit）**  
   - 止损应是 **事前规则（pre-defined rule）**，不是事后解释（post-hoc justification）。  

3. **到达目标价/估值目标（Target Reached）**  
   - 到达并不意味着“必须全卖”，但意味着你应重新计算 **风险回报（risk/reward）** 与 **再平衡（rebalance）**。

### 6.2 两个常见错误（Two Common Mistakes）

- **“跌了所以卖”（Sold because it went down）**：如果逻辑仍在，下跌可能是 **机会（opportunity）**；如果逻辑不在，下跌是 **信号（signal）**。关键是逻辑，不是价格本身。  
- **“总会回来的”（It will come back）**：如果基本面永久损伤，时间不是你的朋友，**机会成本（opportunity cost）** 才是。

### 6.3 一个实用原则（Practical Rule）

把卖出拆成两档：**减仓（trim）** 与 **清仓（exit）**。  
减仓用于“估值偏高但逻辑仍在”；清仓用于“逻辑破坏或风险不可接受”。

---

## 7. 交易日志（Trading Journal）：让你从赌徒进化成系统

### 7.1 为什么日志比“聪明”更重要？

因为市场会奖励 **可复盘性（reviewability）**。没有日志，你只会记住自己赚钱的案例（**幸存者偏差 survivorship bias** 的个人版）。

### 7.2 每笔交易模板（Template）

建议你复制下面模板到 Notion / Obsidian / Excel：

- **日期（Date）**  
- **标的（Symbol）**  
- **动作（Action）**：Buy / Sell / Trim / Add  
- **价格（Price）**、**股数（Shares）**、**总金额（Notional）**  
- **投资逻辑（Thesis）**：3–5 条要点  
- **反面证据（Disconfirming evidence）**：你必须写至少 1 条（强制）  
- **情绪状态（Emotional state）**：冷静 / 兴奋 / 恐惧 / 报复性交易冲动  
- **执行质量（Execution）**：是否追价、是否超出计划仓位  
- **结果（Result）**（事后填）：盈亏、持有期、最大回撤（during trade）  
- **教训（Lessons）**：一句话

### 7.3 月度复盘（Monthly Review）

每月只回答三个问题：

1. 我犯的最大错误属于哪一类：**估值（valuation）**、**质量（quality）**、**节奏（timing）** 还是 **仓位（sizing）**？  
2. 我是否违反了写下来的规则？违反几次？  
3. 下个月我只改一个行为，会是哪一个？

---

## 8. 下单前的风险清单（Risk Checklist）

在点击“买入（buy）”之前，逐项打勾。任何一项不通过，默认 **不买（no trade）**。

- [ ] 我能用一句话解释这家公司如何赚钱（business model）。  
- [ ] 我读过关键财务报表或至少关键比率（financials / key ratios）。  
- [ ] 我知道当前价格水平背后的主要驱动（drivers），不只是“它涨了”。  
- [ ] 我有明确的 **止损（stop-loss）** 或 **逻辑止损（thesis stop）** 规则。  
- [ ] 单笔仓位 ≤ 组合 **10%**（阈值可自定，但必须有硬上限）。  
- [ ] 我不是因为 **FOMO（错失恐惧）**、群聊喊单或短期热点而买。  
- [ ] 这笔钱亏掉也不会影响我的基本生活（afford to lose）。

---

## 9. 一年新手计划（The 1-Year Beginner Plan）

这不是“盈利承诺”，这是 **能力建构（skill building）** 计划。

### 9.1 第 1–3 个月：学习 + 纸上交易（Learn + Paper Trade）

- 读完本学习路径第 1–8 章。  
- 用 Jarvis 做分析，但 **不下真实单（no real money）**。  
- 目标：形成固定工作流（workflow），而不是追求预测准确率。

### 9.2 第 4–6 个月：小资金实盘（Small Real Money）

- 1–2 只股票，小仓位。  
- 目标：练习 **执行纪律（execution discipline）** 与 **日志（journal）**。  
- 接受你会犯错：犯错要便宜、要可复盘。

### 9.3 第 7–9 个月：扩展与精炼（Expand + Refine）

- 增加标的数量前先增加 **研究深度（depth）**。  
- 明确你的“能力圈（circle of competence）”边界。

### 9.4 第 10–12 个月：回顾与选择（Review + Choose）

回答终极问题：

- 我是否享受深度研究？我是否能承受波动？  
- 如果答案是否定的：**指数化（indexing）** 是非常体面的路，不是失败。

---

## 10. 推荐资源（Books & Websites）

### 10.1 书籍（Books）

- 《聪明的投资者》（**The Intelligent Investor**）— Benjamin Graham：投资世界的“操作系统”。  
- 《彼得·林奇的成功投资》（**One Up on Wall Street**）— Peter Lynch：把生活观察与基本面结合。  
- 《股票大作手回忆录》（**Reminiscences of a Stock Operator**）— Edwin Lefèvre：人性与投机（speculation）的镜子。  
- 《手把手教你读财报》— 唐朝：中文语境下读财报的入门佳作（尤其利于 A 股初学者）。  
- 《价值》— 张磊 / 高瓴：长期主义与产业视角的中文叙述。

### 10.2 网站（Websites）

- **巨潮资讯网**（`cninfo.com.cn`）：公告与披露（filings）权威入口。  
- **同花顺**（`10jqka.com.cn`）：数据与工具（注意广告与噪声）。  
- **雪球**（`xueqiu.com`）：社区观点多，必须 **交叉验证（cross-verify）**。  
- **东方财富**（`eastmoney.com`）：新闻与数据聚合。

---

## 11. 结语（Final Words）

投资是 **终身技能（lifelong skill）**，不是 **暴富捷径（get-rich-quick scheme）**。  
市场一定会用回撤与错误告诉你：**谦逊（humility）** 比聪明更重要。  
**耐心（patience）** 与 **纪律（discipline）** 往往比智商更决定长期结果。  
从你能理解的东西开始（start with what you understand），慢慢扩大能力圈。  
Jarvis 是你的 **研究助理（research assistant）**，但方向盘永远在你手里。

---

## 12. 附录：一页纸“Jarvis 日课”（One-page Daily Routine）

1. 更新数据（data refresh）  
2. 检查持仓新闻（news）  
3. 看模型健康度（model health）  
4. 只看候选池（shortlist）不扩大战场  
5. 记录情绪与决策（journal）

把复杂系统压缩成可重复的五步，你才能长期执行。

---

## 13. 附录：当你卡住时，回到这三个问题（Reset Questions）

1. 如果我不能交易它一年，我今天还愿意拥有它吗？  
2. 我愿意用多少仓位证明我的确信度（conviction）？  
3. 我是否愿意为错误付学费，并且把学费写下来？

能回答清楚，你就已经在用“专业流程”而不是“情绪反应”面对市场。
