# Memory: DeepSeek Depth Analysis Empty Report

**Generated**: 2026-08-05 ~12:50 UTC+8
**Last updated**: 2026-08-05 ~13:45 UTC+8
**Project**: c:\jarvis
**Focus**: DeepSeek 深度分析只有推理过程、报告正文为空

---

## Goal & Scope (required)

修复 A股分析 & AI预测 中 DeepSeek 深度分析：推理过程正常，报告正文为空（仅剩标题/生成时间）。本地/Ollama 报告正常，不在范围内。

---

## Key Decisions (required)

1. **范围 A**：只修 DeepSeek 深度分析路径；本地报告不动。
2. **理解已确认**（2026-08-05）：症状为 reasoning 有内容、`report`/`content` 为空。
3. **根因**：thinking tokens 与 final answer 共享 `max_tokens`；耗尽时 `finish_reason=length`、`content=""`、HTTP 200。
4. **方案 B 已批准并实现**：`call_deepseek` 暴露 `finish_reason`/`reasoning_tokens`；`deepseek_report_call` 空/截断时 retry；仍空则 error。
5. **Rejected: A 只加 max_tokens / C 关 thinking（首呼）**：A 仍可能耗尽；C 削弱首呼分析。
6. **Code review triage**：ACCEPTED Important-1/2 + Minor-1/4 已修；REJECTED Minor-2（verdict）本轮不做；Minor-3 截断后已修。
7. **2026-08-06**：发现 DeepSeek 将 `medium` 映射为 `high`，原 retry 无效；改为 retry **thinking=disabled**，并保留首呼 CoT 给 UI。

---

## Confirmed Assumptions (required)

- 复现例：588080，模型 `deepseek-v4-flash`，生成时间约 2026-08-05 11:27。
- 报告头仍写出（`generate_prediction_deepseek` 的 header + 空 content）。
- UI 能显示 reasoning（`deepseek_reasoning`），说明 API 调用大体成功。

---

## Constraints & Non-Goals (include when relevant)

- 不改本地 Ollama 预测报告路径。
- 尽量保持 thinking / `reasoning_effort` 行为；小范围修复。
- `generate_prediction_verdict` 空 content 风险本轮不修（Minor-2 deferred）。

---

## Key Discoveries (required)

- `call_deepseek` 返回 `content`（报告）与 `reasoning_content`（思维链）；`generate_prediction_deepseek` 用 `header + content` 写报告。
- 现场探针：`max_tokens=512` → `finish_reason=length`，`reasoning_tokens=512`，`content_len=0`。
- 磁盘：`588080`/`600988` 仅 126 字节 header；更早报告约 8–12KB。
- Review Important-1：retry `ok=False` 时原先丢弃首呼 diagnostics；已改为合并保留。

---

## Runtime Evidence (include when relevant)

- pytest `tests/test_deepseek_empty_report.py`: **6 passed**
- Live API probe confirmed length/empty-content pattern

---

## Current State (required)

- **Working**: Design B + review fixes（Important-1/2, Minor-1/4）；单测 6 passed
- **Pending**: 重启后手动重跑 588080；可选 follow-up review / commit
- **Blocked**: 无
- **Deferred**: Minor-2 (verdict path)
- **Fixed later**: Minor-3 — truncated non-empty (`finish_reason=length` / content `<500`) now retries then errors (000815 repro)

---

## Next Steps (required)

1. [x] systematic-debugging 确认根因
2. [x] Design B 批准 + TDD 实现
3. [x] Code review + ACCEPTED 修复
4. [ ] 手动重跑 588080 验收报告正文
5. [ ] 用户要求时再 commit / follow-up review

---

## References (required)

- `scripts/stock/config.py` — `call_deepseek` (+ finish_reason / reasoning_tokens)
- `scripts/stock/llm_reasoning.py` — `deepseek_report_call` / `generate_prediction_deepseek`
- `tests/test_deepseek_empty_report.py` — unit tests (6)
- `scripts/rag/templates/index.html` — error path shows reasoning
- `docs/stock-modules/llm_reasoning.md` — docs updated for helper

---

**Confirmed at**: 2026-08-05
