# Memory: Quality Undervalued Stock Screener

**Generated**: 2026-08-16 ~11:10 UTC+8
**Last updated**: 2026-08-16 ~13:30 UTC+8
**Project**: c:\jarvis
**Focus**: 新增独立「优质低估」选股扫描器（价值漏斗 + PB-ROE + DeepSeek 终审）

---

## Goal & Scope (required)

在 Jarvis 股票模块新增一套**独立**的优质低估选股：找出基本面优质但被市场低估的 A 股。持有口径为中长期价值（约 6 个月～2 年）。不改现有左侧/右侧/长期/午盘逻辑。

---

## Key Decisions (required)

1. **独立新入口**：工具栏新加「优质低估」按钮，像长期推荐/午盘一样单独扫描、出报告。Rejected: 加进 AI 推荐第三栏；折进长期推荐。
2. **第一版做完整规格**：四步漏斗 + PB-ROE 排序 + DeepSeek 终审（行业周期/价值陷阱），像 AI 推荐那样出报告。Rejected: 只做能量化部分、暂不接 DeepSeek。
3. **持有周期**：约 6 个月～2 年（中长期价值）。Rejected: 对齐长期推荐 3 个月～1 年；对齐左右侧 1～2 周。
4. **金融股单独规则**：银行/保险/金融负债率放宽或不考核；PB<1 作为低估信号；仍要求股息和 ROE。Rejected: 全市场同一负债率<60%（会踢掉银行）；默认排除金融。
5. **最终最多 5 只**，尽量行业分散，与其他扫描器一致。Rejected: 8–10 只组合；规则层留 30–50 只再终审 5 只。
6. **实现路径 A**：独立 `quality_value_scanner.py` + 批量漏斗（全市场同业粗筛 → 只对入围股拉财务/历史分位 → DeepSeek 终审）。Rejected: 逐只套用 valuation/fundamental（太慢）；把市场级筛选做进 valuation.py。
8. **计划评审补丁（2026-08-16）**：Layer1 硬上限 100 + 相对便宜排序；行业映射只读缓存；DeepSeek 一次批量终审；本地 percentile 不导入私有函数；商誉仅 DeepSeek 定性。
9. **Layer1 排除创业板**：300/301，复用 `board_filters.is_chinext`（不能交易）；科创板 688/689 保留。实现在功能分支 `feature/quality-value-screener`。执行方式：一次一个 Task。
10. **Task 9 之后先接财报**：用户跳过计划 Task 10 PDF，先实现 `fetch_fundamentals_for_value` 并接到 `_run_qv_scan` 的 Layer2（否则扫描只有估值粗筛、没有真实 ROE/CAGR）。Rejected: 先做 PDF / 文档 / 全量测试。

---

## Confirmed Assumptions (required)

- 这是价值投资漏斗，不是短线/趋势交易。
- 宁缺毋滥：允许 0 只推荐。
- 排除 ST / *ST / 退市整理、持续亏损、商誉暴雷。
- 粗筛股息率 ≥ 2.5%；核心指标里股息率 > 3%、近 3 年分红稳定（分红率不低于 30%）作为加严条件。
- PE/PB 必须同行业对比，不能跨行业直接比较。
- 筛选工具仅供参考，不构成投资建议。
- 复用现有 scanner 架构（后台线程、进度、Markdown 报告）。
- 尽量复用 `valuation.py`（同业、历史分位）和 `fundamental_analysis.py`；缺的数据（近 5 年 PE 分位、近 3 年分红稳定性、扣非占比）再新拉。
- 需要一篇与现有四篇同风格的 `strategy-*.md` 策略说明。

---

## Constraints & Non-Goals (include when relevant)

- 不改左右侧统一扫描逻辑。
- 不并进长期推荐。
- 不当成 1～2 周交易策略。
- 不替代单股深度分析。
- 金融股不套用资产负债率 <60% 的硬门槛。

---

## Key Discoveries (required)

- 现有四套入口：单股深度分析、AI 推荐（左+右）、长期推荐、午盘 T+1。导览：`docs/guides/stock-strategy-guide.md`。
- `valuation.py` 已有同业比较、历史分位、简化 DCF。
- `fundamental_analysis.py` 有 PE/PB/ROE/负债率等，但财务摘要取最新一年；文档写明扣非可能缺失。
- 全市场快照已有「市盈率-动态」；左侧 Layer1 用 PE 区间打分，**不是**同业相对低估 + 股息 + PB-ROE。
- 用户打开过 `docs/stock-modules/strategy-unified-left-right-deepseek.md`，但明确要求独立入口而非第三栏。
- 计划评审：Layer1 若不封顶会把 Layer2 打爆；`_fetch_industry_map` 冷启动会拉全部板块；逐只 DeepSeek 太贵；`valuation._percentile_rank` 不宜作公开依赖；东财 `f133` 股息字段未证实。
- ChiNext 单测：科创 688 仍可能因相对 PE/PB 被踢；要给足够非创业板同行，才能断言 688 入围。
- Layer1 cap 单测：若 PB 全等于行业均值会被 `PB < mean` 全踢；用 `pb: None` 只测 PE 排序。
- 5y PE 窗口用 `df[col] > start`（不是 `>=`），否则年终边界会多算第 6 年。
- `_call_value_llm` 与 `_run_qv_scan` 必须是两个函数；`call_deepseek(system_prompt, user_prompt)` 不是 messages 列表。
- pandas DataFrame 里的 `None` 会变成 `nan`；`_num_val` 必须 `pd.isna`。
- 分红年度列若是整数 `2024`，`pd.to_datetime(2024)` 会当成纳秒 → 1970；`_year_from_cell` 对 1990–2100 整数直接当年度。
- `_col` 必须精确列名优先，否则 `扣非净利润` 会抢 `净利润`。
- 3 年净利润 CAGR：`(latest/oldest)**(1/2)-1`（3 个年报、2 个间隔年）。扣非：带 `%` 当比例；带亿/万当金额 / 净利润。
- 财报缓存：`STOCK_CACHE_DIR/.quality_value/{symbol}.json`，按 JSON `fetched_at` 判断 24h（不要用文件 mtime，测试会传入 `now`）。
- `tests/` 被 gitignore，本地仍跑 pytest，测试文件可能不会进仓库。

---

## Runtime Evidence (include when relevant)

- `python -m pytest tests/test_quality_value_funnel.py tests/test_quality_value_scanner_api.py tests/test_llm_reasoning_value_prompt.py tests/test_quality_value_routes.py tests/test_quality_value_ui.py -v` → **38 passed**（2026-08-16）。

---

## Open Risks (include when relevant)

- 真实行情扫描未手跑；0 只入围是合法结果（宁缺毋滥）。
- `stock_fhps_detail_em` 列名可能与测试用的「年度/现金分红」不同，实盘分红可能经常是 `unknown`。
- Layer2 对最多 100 只拉同花顺年报，首次扫描会慢；24h 缓存后会快很多。

---

## Current State (required)

- **Working**: 分支 `feature/quality-value-screener`；Task 1–9 + 财报接入完成。漏斗：Layer1（踢 ST/创业板/相对贵）→ `fetch_fundamentals_for_value` → Layer2 → Layer3 PB-ROE + 5y PE 分位 → DeepSeek 批量终审。工具栏「优质低估」按钮 + `#qualityValueModal`。Flask `/api/stock/quality-value/*`。38 pytest 通过。
- **Pending**: Task 10 PDF（`stock_pdf.py` type `quality_value`）；Task 11 文档；Task 12 全量测试 + 手动扫描。
- **Blocked**: 无

---

## Next Steps (required)

1. [x] 用户确认后触发 `brainstorming`
2. [x] 设计扫描器架构、数据源、漏斗与 UI（四段均批准）
3. [x] 写 `docs/plans/2026-08-16-quality-value-screener.md`
4. [x] Task 1–9 + 财报接入（Layer2 真正排雷）
5. [ ] Task 10：`stock_pdf.py` 增加 `quality_value` 报告类型
6. [ ] Task 11：策略/模块文档
7. [ ] Task 12：全量测试 + 手动扫描备注

---

## Notes for Next Session (include when relevant)

- 不要在 `main` 上改；未要求则不要 commit。
- 用户不能交易创业板，Layer1 **必须在算同业均值之前** 丢掉 300/301，避免扭曲同行均值。
- UI PDF 按钮计划接到 `exportStockPdf('quality_value','qv')`，Task 10 落地前可以先 hidden/no-op。
- 完整功能尚未做 code-reviewer；整套做完 Task 12 后再评 Rule 8。
- 相关但未加载：`memory-20260805-deepseek-stock-strategy-docs.md`

---

## References (required)

- `docs/plans/2026-08-16-quality-value-screener.md` — 实现计划
- `scripts/stock/quality_value_scanner.py` — 漏斗 + 扫描生命周期 + 财报抓取
- `scripts/stock/board_filters.py` — `is_chinext`（300/301）
- `scripts/stock/llm_reasoning.py` — `build_quality_value_system_prompt`（6个月～2年，禁止 1周/2周 原文）
- `scripts/stock/valuation.py` — `fetch_valuation_history`（5y PE 分位）
- `scripts/rag/routes/stock.py` — `/api/stock/quality-value/*`；`_STOCK_MODULES` 含 `quality_value_scanner`
- `scripts/rag/templates/index.html` — `openQualityValueModal`、`qvUseDeepseek`
- `tests/test_quality_value_funnel.py` 等 — 本地 pytest（可能 gitignore）

---

**Confirmed at**: 2026-08-16
