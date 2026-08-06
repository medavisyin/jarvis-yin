# Memory: Rec vs Deep Analysis Entry Alignment

**Generated**: 2026-07-31 ~20:08 UTC+8
**Last updated**: 2026-07-31 ~21:17 UTC+8
**Project**: c:\jarvis
**Focus**: 推荐与 A股分析在「空仓现价可买」上对齐（深度优先 · 左软右硬）

---

## Goal & Scope (required)

解决普遍冲突：左侧推荐写「现价分批买」，A股分析空仓写「别追、等回调」。根因是 Phase 3.5 复核只对齐方向，不对齐现价可买；再叠加「买入区间贴近现价」放大冲突。目标：深度分析优先；左侧等回调软降级，右侧硬否决。

---

## Key Decisions (required)

1. **Approach 1**：扩展 `generate_prediction_verdict` JSON（`empty_entry` / pullback / entry_note）+ `recheck_policy` 分侧；不二次 API、不改完整深度报告。
2. **深度优先**：空仓不建议现价买时，推荐必须让步（即使方向仍看多）。
3. **分侧**：左 `wait_pullback` → soft（保留、verdict=等回调、改写回调区间）；右 `wait_pullback|avoid` → 硬否决；`avoid` 两侧否决。
4. **缺字段默认 `now`**：避免解析抖动误杀；API 失败保留原推荐。
5. **执行路径**：用户选直接实现（无 formal plan）。
6. **Review 收工**：Important-1..3 已修且 follow-up 通过；用户接受现状，全部 Minor defer。

---

## Confirmed Assumptions (required)

- 「贴近现价」只适用于深度 `empty_entry=now` 的票。
- A股分析主报告口径不改，仍作权威源。
- 用户操作风格：短期、左可等补仓，右严止损。

---

## Key Discoveries (required)

- 旧复核：看多即可过关 → 601899 类「看多但空仓劝等」仍出现在现价买入推荐。
- 左 survivors 过滤只看 `recheck_vetoed`；soft 用 `recheck_wait_pullback`，不得设 veto 标记。
- 回调区间须整段 ≤ 现价；跨现价 straddling 不改写 buy range。
- `confidence: null` 曾使 `int()` 抛错并绕过 entry 门控；已用 `coerce_confidence`。

---

## Current State (required)

- **Working**: entry-alignment + Important-1..3；follow-up 确认本切片 production-ready；单测 **23 passed**
- **Pending**: 重启 Jarvis 实测；用户要求时 commit
- **Blocked**: 无
- **Deferred Minors**: UI/报告分组、FAQ 措辞、文件空行、parse-path 集成测、should_veto 统一 coerce

---

## Next Steps (required)

1. [ ] 重启 Jarvis，DeepSeek 统一扫描验证 601899 类票
2. [ ] 用户要求时再 commit
3. [ ] （可选）后续收 deferred Minors

---

## Notes for Next Session (include when relevant)

- 共享策略：`scripts/stock/recheck_policy.py`（`classify_recheck_action` / `apply_recheck_action` / `coerce_confidence`）
- 测试：`pytest tests/test_scan_recheck_veto.py -v`（`tests/` gitignored）
- 相关前序：`memory-20260730-stock-rec-style-alignment.md`

---

## References (required)

- `scripts/stock/recheck_policy.py` — 方向 + empty_entry 分侧
- `scripts/stock/llm_reasoning.py` — `generate_prediction_verdict` 扩展字段
- `scripts/stock/scanner.py` / `right_side_scanner.py` — Phase 3.5 接线
- `scripts/rag/templates/index.html` — 等回调 UI
- `docs/guides/stock-strategy-guide.md` — §4/5/7/9
- `tests/test_scan_recheck_veto.py` — 23 cases

---

**Confirmed at**: 2026-07-31
