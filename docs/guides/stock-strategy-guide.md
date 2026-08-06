---
tags:
  - guide
  - stock
  - strategy
  - chinese
  - beginner
category: guide
status: current
last-updated: 2026-08-05
---

# Jarvis 股票策略导览（小白入口）

写给**完全不懂炒股**的你：先搞清 Jarvis 有哪几套股票功能、大概什么区别、从哪点进去。  
**详细金融策略与 DeepSeek 怎么判断**，请看下方四篇专文——本文只做导览，避免和专文说法重复打架。

> ⚠️ **合规提示**：本文只解释系统原理与入口，**不构成任何投资建议**。股市有风险，所有推荐都只是参考，买卖决策和盈亏由你自己负责。

---

## 0. 四套功能 → 详解文档（先收藏）

| 网页功能 | 一句话 | 详解（DeepSeek 策略 · 小白版） |
|---|---|---|
| **A股分析 & AI预测** | 你指定一只股票，做深度研判 | [strategy-ashare-analysis-deepseek.md](../stock-modules/strategy-ashare-analysis-deepseek.md) |
| **AI 推荐（左侧+右侧）** | 一次扫描，抄底与跟趋势两份报告 | [strategy-unified-left-right-deepseek.md](../stock-modules/strategy-unified-left-right-deepseek.md) |
| **AI 股票推荐(长期)** | 新闻主题 + 贵金属，约 3 个月～1 年布局 | [strategy-long-term-deepseek.md](../stock-modules/strategy-long-term-deepseek.md) |
| **午盘极速隔夜套利 (T+1)** | 午休决策，尾盘买、次日早盘卖 | [strategy-midday-t1-deepseek.md](../stock-modules/strategy-midday-t1-deepseek.md) |

技术实现细节仍在 `docs/stock-modules/` 各模块文档（如 `scanner.md`、`midday_scanner.md`）。

---

## 1. 先搞懂：左侧 vs 右侧（30 秒版）

| | 左侧交易 | 右侧交易 |
|---|---|---|
| **比喻** | 衣服还在降价，趁便宜买 | 衣服止跌回涨，确认后再买 |
| **信念** | 便宜 + 吸筹 = 安全边际 | 趋势确认后再跟 |
| **Jarvis** | AI 推荐左栏 | AI 推荐右栏 |

> 💡 **左侧 = 买跌（赌反弹），右侧 = 买涨（跟趋势）**。细节、漏斗、DeepSeek 终审与报告字段 → 见 [左右侧策略专文](../stock-modules/strategy-unified-left-right-deepseek.md)。

### 主力资金（更短版）

大资金买卖会留下「净流入/流出」痕迹。常见阶段：

| 阶段 | 大白话 |
|---|---|
| 布局期 | 钱在进、价还没大涨（左侧常关注） |
| 拉升期 | 钱在进、价已大涨（追高要谨慎） |
| 出货期 | 钱在出（两侧都该警惕/否决） |
| 观察期 | 信号不清，等待 |

完整阶段用法与左右差异 → 见专文第 2 章。

---

## 2. 统一推荐怎么用（操作入口）

1. 工具栏点 **「🤖 AI 推荐」**
2. **勾选 DeepSeek**（建议开；需在设置里配置 API Key）
3. 开始扫描：共享行情 → 左侧扫描 → 右侧扫描
4. 左栏 / 右栏分别读报告

```
一次共享行情
   ├─ 左侧：回调/估值/吸筹 → DeepSeek 终审（与单股深度分析同一人设；约1～2周）(+ Top5 深度复核)
   └─ 右侧：资金由出转进 + 趋势确认 → DeepSeek 终审（同一人设 + 右侧纪律）
→ 两份独立报告
```

> 2026-08 起：推荐 Layer3 与「A股分析 & AI预测」**共用决策尺子**；「买入」≈ 空仓者现在适合建仓。若仍觉得语气不同，先读专文 §4.5。

**报告字段、硬门控、止损纪律、左右如何配合、与单股分析的关系** → 全部以专文为准：  
[strategy-unified-left-right-deepseek.md](../stock-modules/strategy-unified-left-right-deepseek.md)

耗时粗估：左侧常需十几～几十分钟；右侧更快。看进度条文案确认是否在推进。

---

## 3. 另外三套怎么选（极简）

| 你的情况 | 去哪 |
|---|---|
| 已经有代码，想系统化深挖 | [单股分析](../stock-modules/strategy-ashare-analysis-deepseek.md) |
| 想找短中期交易机会 | [左右统一推荐](../stock-modules/strategy-unified-left-right-deepseek.md) |
| 想看未来约 3 个月～1 年主题 | [长期推荐](../stock-modules/strategy-long-term-deepseek.md) |
| 能盯盘、要玩隔夜超短 | [午盘 T+1](../stock-modules/strategy-midday-t1-deepseek.md) |

---

## 4. 小白 FAQ（仍通用）

**Q：推荐了一定会涨吗？**  
A：不会。任何策略都是概率。务必设止损、控仓位。

**Q：「暂无推荐」是系统坏了吗？**  
A：不是。Jarvis 宁可 0 推荐也不乱推；0 往往是负责任的结果。

**Q：DeepSeek 要勾吗？**  
A：强烈建议勾。判断质量通常明显更高。前提是设置里有 API Key。

**Q：推荐说买入，丢进「A股分析」却偏谨慎？**  
A：以前两套 DeepSeek 尺子不同，容易打架；现已对齐同一人设（约 1～2 周 + 空仓可建仓）。若扫描后过了一会儿再分析，盘口变了仍可能不一致——以深度报告的空仓建议 / 矛盾点为复检。详见[单股专文 §4.5](../stock-modules/strategy-ashare-analysis-deepseek.md) 与[推荐专文 §4.5](../stock-modules/strategy-unified-left-right-deepseek.md)。

**Q：我该信左侧还是右侧？**  
A：看行情与性格。更细的配合表见[左右侧专文 §5 / §8](../stock-modules/strategy-unified-left-right-deepseek.md)。新手若只能选一个，往往先学右侧纪律（信号清晰 + 强制止损），左侧小仓试。

**Q：想加自己的策略？**  
A：见 [stock-new-strategy-guide.md](./stock-new-strategy-guide.md)。

---

## 5. 风险提示（必读）

- 所有输出都是参考，不是投资建议。  
- 过往表现不预示未来。  
- 务必止损、控仓位；执行纪律比“预测准不准”更重要。  
- 超短、波段、主题仓位建议隔离，避免策略互相污染。

---

*导览对应 `scripts/stock/` 下多套扫描与 `llm_reasoning`。策略细节以 `docs/stock-modules/strategy-*-deepseek.md` 四篇为准；模块实现见同目录技术文档。*
