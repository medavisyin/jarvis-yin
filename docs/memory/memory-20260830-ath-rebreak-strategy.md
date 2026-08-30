# Memory: ATH 突破回踩再突破策略评估

**Generated**: 2026-08-30
**Last updated**: 2026-08-30 (design approved; writing-plans)
**Project**: c:\jarvis
**Focus**: 将「ATH 突破 → 回落 → 二次突破」策略评估并准备接入 AI 股票推荐与 A股分析

---

## Goal & Scope (required)

用户要把「价格超过曾经最高点（标杆）→ 回落 → 再次突破该最高点 = 买入点」加入 **AI 股票推荐** 与 **A股分析 & AI预测**。评估与设计已批准。v1 用近5年高代理。实现计划：`docs/plans/2026-08-30-ath-rebreak-scanner.md`。

---

## Key Decisions (required)

1. **本轮先评估、不改代码**：用户选 A（评估优劣与可行性；先不实现）。
2. **长期目标标杆 = 上市以来 ATH**；**v1 改用近5年高（前复权）并写明口径**（决策 8）。
3. **回踩规则先对比几种口径再决定**：跌回 ATH 下方再站上；3%–8% 回落后再突破；浅回踩不破太多再突破。
4. **覆盖两套分析**：AI 股票推荐（统一扫描左/右）+ A股分析单股深度报告。
5. **写入本 memory 文件**：用户确认。
6. **Trigger brainstorming**：用户确认进入方案设计。
7. **接入方式 A**：共享检测器 + 第三套独立扫描器 + A股分析共用；不改左右漏斗。
8. **v1 标杆 = 近5年高（前复权）**：报告禁止写「历史最高」；真上市以来 ATH 以后再补。
9. **独立第三栏推荐**：AI 推荐弹窗左 / 右 / 近5年高二次突破。
10. **信号规则**：第一次收盘站上近5年高只是标杆；至少整理 3 个交易日；回踩打 A/B/C 标签；二次突破看收盘；近 3 个交易日内才算当前买点；涨停标记不可买。
11. **写 memory + 写计划**：用户确认更新 memory，并选 writing-plans（同会话）。
12. **Rejected: 只做第三扫描不做 A股分析**：两套口径会再打架。
13. **Rejected: 把漏斗塞进 unified_scanner.py**：违反插件规范。
15. **计划审查补丁（2026-08-30）**：二次突破K线优先记为 rebreak、不可当成新的第一次突破而重置；`pct_3_8` 按相对峰值回撤；Layer1 成交额门槛 3000 万元。
16. **第二轮审查补丁**：合同正文规则 2/6 与补丁打架已改写；恢复过期信号测试；检测器要读 `pct_change`；Layer2 必须线程池拉日线。
17. **第三轮审查**：过期二次突破仍报 `stage=rebreak`；`analyze` 单测必须用英文字段，不能用未重命名的中文 `_ohlcv`。计划已可执行。

---

## Confirmed Assumptions (required)

- 第一次突破只是标杆，不是买点；回落后再次突破才是买点。
- v1 用现有 daily.csv（约 5 年、前复权）的最高价，文案写「近5年高」。
- 左右漏斗逻辑不改。
- 三种回踩都打标签，不在 v1 只留一种。
- 不构成投资建议。

---

## Constraints & Non-Goals

- 不构成投资建议；评估的是规则可实现性与策略结构风险。
- v1 不拉上市以来真 ATH；不做独立回测模块；不改左侧/右侧筛选条件。
- 实现须等计划批准并进入 `executing-plans`（或用户选直接执行）之后。

---

## Key Discoveries (required)

### 策略评估结论

- **方向对，但是右侧确认过滤器，不是单独圣杯。** 突破 ATH 意味着上方套牢盘较少；回踩后再突破过滤一部分假突破。这与现有右侧「确认后跟进」同族，与左侧「抄底/估值」相反。
- **不能当唯一买点。** A 股假突破、打板出货、T+1 买在涨停次日高开都很常见。二次突破经常发生在涨停日，买不到。
- **ATH 对老股往往是 2007/2015 泡沫高点**，信号极稀；对新股则几乎等于「上市以来新高」，偏频繁。5 年窗口的「ATH」其实是近 5 年高，不是真正上市以来最高。
- **前复权 vs 不复权会改写 ATH。** 现有日线默认 `qfq`。分红后前复权图上的「新高」可能与未复权历史高完全不是一回事。必须固定口径并在报告里写明。
- **三种回踩（v1 全部打标签，不单选默认）**：
  - A 跌破 ATH 再收盘站上：信号多、鞭梢多。
  - B 回落 3%–8% 再突破：更像旗形整理，假信号仍在。
  - C 浅回踩不破太多：强趋势延续或吹顶后的多头陷阱，需缩量回踩 + 二次放量。

### 现有系统缺口（可行性）

- **能实现，但现在算不出真 ATH。** `fetch_daily_ohlcv` 默认 `DEFAULT_HISTORY_DAYS = 1825`（约 5 年），不是上市首日至今。
- **技术面没有该形态。** `technical_analysis.calc_support_resistance` 只看近 60 日 `recent_high`；形态检测有「放量突破」（相对均量），没有 ATH 状态机。
- **A股分析 DeepSeek 看不到 ATH。** `llm_reasoning.py` 只注入近 20 日 OHLCV + 60 日近期高。模型无法从材料里认出「历史最高 → 回踩 → 二次突破」。
- **AI 推荐的「突破」不是前高。** 右侧 Layer2 用站上 MA5 / 逼近或突破 MA20；Layer1 涨幅上限约 +7%，当天大涨创 ATH 的票可能被挡掉。左侧是估值/抄底，与 ATH 突破哲学冲突。
- **有现成插件口。** `docs/guides/stock-new-strategy-guide.md` 允许第三套 `*_scanner.py` 挂进 `unified_scanner`。`backtest_engine.py` 已含 T+1 / 涨跌停约束，适合以后验证，但当前没有该策略实现。
- **数据可拉长。** `fetch_daily_ohlcv(start_date=...)` 已支持自定义起点；单股分析拉上市以来成本低。全市场 Layer1 对 5000 只拉全历史过重，ATH 应预计算或只在 Layer2 候选上算。

### 已批准设计（2026-08-30）

- 新模块 `scripts/stock/ath_rebreak.py`：纯函数检测器。
- 新扫描器 `scripts/stock/ath_rebreak_scanner.py`：插件契约，Layer1 强势+活跃约 80–100 只，Layer2 检测器，Layer3 DeepSeek。
- `unified_scanner` 左右之后跑第三扫；前端三栏。
- `technical_analysis.analyze` + `llm_reasoning` DeepSeek 材料写入同一检测结果。
- 涨停可检出但 `tradeable=False`。

---

## Current State (required)

- **Working**: 近5年高二次突破已接入：检测器、第三扫描器、统一三栏、A股分析 DeepSeek 材料。计划验证集 21 passed。
- **Pending**: 用户实机点一次「AI 推荐」看第三栏；可选 code review / commit。
- **Blocked**: 无。

---

## Next Steps (required)

1. [x] Brainstorming 设计已批准。
2. [x] writing-plans 计划文件。
3. [x] 执行计划（检测器 → 扫描器 → 统一编排/UI → A股分析材料）。
4. [ ] 用户实机验证统一扫描第三栏。
5. [ ] 如需提交：commit（须用户明确要求）。

---

## Notes for Next Session

- 用户原话：标杆是曾经最高点，回落后再次突破才是买点。
- 不要把该策略塞进左侧抄底扫描。
- 当前 daily.csv 的 max(high) ≠ 真 ATH。

---

## References (required)

- `scripts/stock/fetch_market_data.py` — `DEFAULT_HISTORY_DAYS = 1825`，可传 `start_date`
- `scripts/stock/technical_analysis.py` — 60 日 `recent_high`，无 ATH 形态
- `scripts/stock/llm_reasoning.py` — DeepSeek 近 20 日 OHLCV
- `scripts/stock/right_side_scanner.py` — MA20「突破确认」，涨幅 ≤ +7%
- `scripts/stock/scanner.py` — 左侧可买性，与 ATH 动量相反
- `docs/guides/stock-new-strategy-guide.md` — 第三策略插件契约
- `docs/stock-modules/strategy-unified-left-right-deepseek.md` — 左右哲学
- `docs/stock-modules/strategy-ashare-analysis-deepseek.md` — 单股分析材料流水线
- `scripts/stock/backtest_engine.py` — T+1 / 涨跌停回测约束（v1 不接）
- `docs/plans/2026-08-30-ath-rebreak-scanner.md` — 实现计划

---

**Confirmed at**: 2026-08-30
