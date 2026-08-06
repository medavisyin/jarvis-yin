# Memory: Stock Recommendation Style Alignment

**Generated**: 2026-07-30 ~12:15 UTC+8
**Last updated**: 2026-07-30 ~12:15 UTC+8
**Project**: c:\jarvis
**Focus**: AI 推荐买入区间难成交 + 与「A股分析」冲突；按用户风格收紧推荐

---

## Goal & Scope (required)

用户反馈：推荐买入点位经常够不到；同一批票拿去「A股分析 & AI预测」多数不建议买。希望解释两套差异，并收紧推荐侧；操作风格：短期 2周~2-3个月，可等可补仓，左侧弱化止损、右侧保留严止损，买入区间贴近扫描现价。

---

## Key Decisions (required)

1. **Approach 1（用户选 A）**：Prompt + 复核收紧；不做区间硬校验（暂不选 1+2）。
2. **买入区间**：左右均贴近扫描现价约 ±1%~2%，禁止远低于现价的理想抄底价作主区间。
3. **止损分侧**：左侧可等/补仓、弱化强制止损；右侧保留严格止损。
4. **深度复核**：看空否决；高置信中性（≥60）也否决；左右均启用（右侧新增）。
5. **不改**「A股分析」主报告门槛（保持偏保守作交叉验证）。
6. **文档**：更新 `stock-strategy-guide.md` §4/5/7/9 + 统一面板文案。

---

## Confirmed Assumptions (required)

- 持有周期仍偏短期（2周~2-3个月），不做长期投资化。
- 深度分析与推荐目标不同：推荐=筛票，深度=单票深审。

---

## Key Discoveries (required)

- 左侧旧 prompt 示例把 buy 区间锚在约现价×0.95~现价 → 易「够不到」。
- 左侧 Phase 3.5 原先只否决「看空」，中性仍可能留在推荐里。
- 右侧原先无 `generate_prediction_verdict` 复核。

---

## Current State (required)

- **Working**: `recheck_policy.py` + scanner/right_side 接入；策略指南与 UI 说明已同步；单测 11 passed（含 Minor-1/2 补测）
- **Pending**: 用户重启 Jarvis 后实测扫描
- **Blocked**: 无

---

## Next Steps (required)

1. [ ] 重启 Jarvis，勾 DeepSeek 跑一次统一扫描，检查买入区间与复核否决
2. [ ] 完成/跳过 code review
3. [ ] 若区间仍飘，再考虑 Approach 2 硬校验兜底

---

## Notes for Next Session

- 共享否决逻辑：`scripts/stock/recheck_policy.py`（`NEUTRAL_VETO_MIN_CONFIDENCE=60`）
- 测试：`pytest tests/test_scan_recheck_veto.py -v`
- 需重启 Flask 加载 scanner / right_side_scanner / recheck_policy

---

## References (required)

- `scripts/stock/recheck_policy.py` — 复核否决策略
- `scripts/stock/scanner.py` — 左侧 prompt + Phase 3.5
- `scripts/stock/right_side_scanner.py` — 右侧 prompt + 新复核
- `docs/guides/stock-strategy-guide.md` — 策略小白版 + §9 summary
- `tests/test_scan_recheck_veto.py` — 否决策略单测

---

**Confirmed at**: 2026-07-30 (Approach 1 implemented; user requested review + memory)
