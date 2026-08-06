# Memory: DeepSeek Stock Strategy Docs

**Generated**: 2026-08-05 15:56
**Last updated**: 2026-08-05 18:20
**Project**: c:\jarvis
**Focus**: DeepSeek 策略文档 + 推荐/深度分析人设对齐

---

## Goal & Scope (required)

为 Jarvis 四个股票功能写面向非专家的 DeepSeek 策略说明；并解决「AI 推荐买入 vs A股深度分析偏谨慎」的口径冲突（方案 3：以深度分析为准统一提示词）。

---

## Key Decisions (required)

1. **四篇独立文档**在 `docs/stock-modules/`，统一模板。
2. **冲突修复方案 3 + 选项 B**：以单股深度分析为人设/周期基准；左侧 Layer3 + 轻量复核 + 右侧 Layer3 共用 `deepseek_shared_persona_rules`；右侧保留资金反转硬过滤。
3. **买入映射**：Layer3 仅当「空仓者现在适合建仓」才可判买入。
4. **主周期**：约 1～2 周情景；去掉「2～3 个月赚 10%+」作为 Layer3 主叙事。
5. **文档**：两篇策略文新增 §4.5 冲突说明。

---

## Confirmed Assumptions (required)

- 轻量复核仍只否决「看空」（本次不升级中性否决）。
- 午盘/长期提示词不在本轮范围。

---

## Key Discoveries (required)

- 冲突主因是尺子不同，不是单纯 UI 文案。
- 共享函数：`deepseek_shared_persona_rules` / `build_left_layer3_system_prompt` / `build_right_layer3_system_prompt` / `build_verdict_system_prompt` in `llm_reasoning.py`。

---

## Current State (required)

- **Working**: 策略四篇 + 人设对齐代码 + `tests/test_deepseek_shared_persona.py`；与 empty_report 一并 14 passed
- **Pending**: 可选 code-review / commit
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 用户确认是否 follow-up review / commit
2. [ ] （可选）实盘再跑一轮推荐+单股分析体感验证

---

## References (required)

- `scripts/stock/llm_reasoning.py`
- `scripts/stock/scanner.py`
- `scripts/stock/right_side_scanner.py`
- `tests/test_deepseek_shared_persona.py`
- `docs/stock-modules/strategy-ashare-analysis-deepseek.md` §4.5
- `docs/stock-modules/strategy-unified-left-right-deepseek.md` §4.5

---

**Confirmed at**: 2026-08-05 18:20
