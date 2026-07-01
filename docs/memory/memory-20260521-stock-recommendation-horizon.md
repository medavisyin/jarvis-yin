# Memory: Stock Recommendation Time Horizons and Direct Theme Recommendations

**Generated**: 2026-05-21 10:15
**Last updated**: 2026-07-01 14:50
**Project**: c:\jarvis
**Focus**: Update short-term and long-term stock scanners to support user-preferred time horizons and include direct stock recommendations in investment themes. (2026-07-01 extend: fix short-term vs deep-analysis paradox + add right-side trading scanner.)

---

## Goal & Scope (required)

The user requested specific modifications to both short-term and long-term stock recommendation systems:
1. **Short-Term Recommendations**: Shift from generic timing to a specific holding window of **2 weeks to 2-3 months** with a **10%+ profit target**, adding deeper analysis (K-line volume-price correlation, fund divergence) when DeepSeek is enabled.
2. **Long-Term Recommendations**: Extend prediction horizon up to **6 months to 1 year** and add **direct stock recommendations** (대표개개/대표个股) underneath each long-term investment theme, which are especially enabled and high-quality when DeepSeek is enabled.

---

## Key Decisions (required)

1. **Prompt Alignment**: Instead of adding new fields to JSON outputs that could break frontend API parsing, we seamlessly integrated the target horizons (2 weeks to 2-3 months for short term; 6 months to 1 year for long term) and profit targets (10%+) directly into the LLM system prompts. This forces the model to factor these constraints into its scoring, reasoning, risks, and trading strategies.
2. **Theme Direct Stocks Matching**: In `long_term_scanner.py`, Step 3 (`_llm_theme_analysis`) now outputs a `recommended_stocks` list of objects. In Step 4, we extract these stocks first, clean/validate their symbols to make sure they are valid 6-digit A-share codes, and inject them as high-priority candidates to be assessed and filtered alongside sector-matched stocks. This resolves the limitation of relying purely on sector substring matching.
3. **Frontend Integration**: Modified `index.html`'s JS rendering loop for long-term themes to check for the presence of `recommended_stocks` and render them directly beneath each theme block in a stylized green/blue card layout.

4. **(2026-07-01) 短期推荐 vs 深度分析悖论修复 — 数据质量硬门控 + 排名融合资金面**: 在 `scanner.py` Layer 2/3 修复数据不对称：资金流向缺失（`data_days<3` 或 `ff_signals={}`）时重试一次，仍失败则标记 `data_quality:"fund_flow_missing"`，`ff_score` 设为 `None`（区分"真中性"与"未知"）；Layer 3 prompt 显式注入"资金数据缺失禁止仅凭估值/技术面/XGBoost 买入，默认不买入"；`verdict=="买入"` 且 fund_flow_missing 时强制降级为"不买入"；`final_score` 新增资金面否决项——`出货期`或大额净流出时压到 MIN_BUYABILITY_SCORE 以下，不让纯 XGBoost Alpha 决定排名。
5. **(2026-07-01) 新增独立右侧交易扫描器 `right_side_scanner.py`**: 镜像 `midday_scanner` 结构。Layer 1 预筛"资金面反转"候选（10日净流出但3日净流入转正且 main_pct_3d > 阈值，价格站上 MA5 逼近/突破 MA20）；Layer 2 突破确认+资金持续度+基本面底线；Layer 3 右侧专用 DeepSeek prompt（入场=资金由出转进+趋势确认，不要求低位，允许突破位追高但严格止损，2周~2-3个月/10%+目标，输出含 `entry_type:"右侧"`）。独立 Flask 路由 + 独立前端面板 + RAG 索引。
6. **Rejected: 复用 `llm_reasoning` 完整深度分析做 scanner Top5 复核**: 完整 8 段报告 max_tokens=8192/thinking-high，单只约 $0.0028，Top5 约 $0.014/次扫描——钱开销可忽略，但时间 +1-2 分钟。
7. **(2026-07-01) 采用轻量深度复核（用户选 B）**: 新增 `llm_reasoning.generate_prediction_verdict(symbol)`——复用深度分析的完整数据装配（`_load_or_compute`+`_build_deepseek_prompt`），但 system prompt 只要求结构化方向 JSON（direction/confidence/reason/veto_reason），`max_tokens=1500, reasoning_effort="medium"`，约 $0.003/次扫描、+20-40秒。scanner 新增 Phase 3.5 `_run_deepseek_recheck_for_picks`：对 Top5 并发复核（3 worker），direction=="看空" → 否决买入（降级观望+压分+标记 recheck_vetoed 并从 top_picks 移除）。仅在 `use_deepseek=True` 时运行。前端 pollScanStatus 新增 `layer3_recheck` 进度分支，renderScanResult 显示 🔄 深度复核方向标签。JSON 解析抗 think 标签噪声（优先匹配含 "direction" 的 JSON 对象）。
8. **Rejected: scanner 加 `mode=right_side` 参数**: 把"惩罚追高"与"右侧追高"两套冲突逻辑塞进一个模块，分支复杂难维护。改为独立模块。
9. **(2026-07-01) 合并左右扫描器为统一扫描（用户选 B/A/B）**: 新增 `unified_scanner.py` 编排器——Layer 1 共享一次全市场行情抓取，分别套用左侧(scanner buyability)与右侧(right_side 活跃度)筛选；Layer 2 对并集候选**共享 enrichment 缓存**（fund_flow + OHLCV 每只只抓一次，各自独立筛选条件但命中即复用）；Layer 3 双判断（左侧 DeepSeek+Phase3.5 复核 / 右侧 DeepSeek 右侧判断）；输出两份报告（左侧短期 + 右侧交易）+ 双 RAG 索引；统一 status。scanner.py 与 right_side_scanner.py 改为接受 `market_df` 与 `enrich_cache` 参数（向后兼容，可独立运行）。前端两按钮合并为一个"AI 股票推荐"，单弹窗一个进度条 + 两报告区块（左侧/右侧）。
10. **(2026-07-01) 前端轮询 bug 修复**: 原 startRightSideScan 在 fetch 返回后才启动 polling，首次冷启动 import 慢时 UI 卡在初始消息。统一弹窗改为点击即启动 polling。
11. **(2026-07-01) 统一扫描器实施完成**: 新增 `scripts/stock/scan_cache.py`（线程安全的 fund_flow + OHLCV per-scan 缓存，reset/get/set）。新增 `scripts/stock/unified_scanner.py` 编排器：共享 Layer1 行情抓取（akshare→东财直连→新浪三重兜底）→ 注入 `set_shared_market_df` 到 scanner 与 right_side_scanner → 顺序运行左侧(scanner.start_scan)→右侧(right_side.start_right_side_scan)，`_wait_for` 轮询子扫描器状态并映射到统一进度(市场5%/左12-57%/右58-98%/完成100%) → `get_latest_unified_result` 聚合当日左+右结果。scanner.py 与 right_side_scanner.py 改动：`_layer1_quick_filter`/`_run_scan_inner`/`_run_rs_scan_inner` 增加 `market_df` 参数；Layer2 的 `stock_fund_flow_signals` 与 `fetch_daily_ohlcv` 改为先查 `scan_cache` 命中即复用。stock.py 注册 `unified_scanner`+`scan_cache` 到 `_STOCK_MODULES`，新增 4 个 `/api/stock/unified_scan/*` 路由。index.html：两工具栏按钮合并为"🤖 AI 推荐"，新增 `unifiedModal` 双区块弹窗(左侧短期/右侧交易)，JS `startUnifiedScan` 点击即启动 polling（修复原卡住 bug），`_buildScanResultHtml`/`_buildRightSideHtml` 抽取为可复用 builder。烟雾测试通过：导入、启动、状态机、结果聚合均正常（行情抓取因本 shell 无外网而优雅降级为 error，Flask 环境正常）。
12. **(2026-07-01) 关键 bug 修复 — 统一扫描器状态被模块重导入重置**: 用户反馈 UI 卡在"扫描进行中"，后端 `/status` 实际返回 `idle`。根因：`_with_stock_imports` 装饰器每次请求 `sys.modules.pop` 并重新导入 `unified_scanner`，模块级 `_status`/`_scan_thread` 被重置 → 后台线程跑在孤儿模块实例里更新自己的 `_status`，而 status 接口读到新实例的初始 `idle` → 前端 `pollUnifiedStatus` 遇 idle 静默 return → UI 永远卡住。`right_side_scanner` 用 `sys._rs_*` 规避了此问题，unified_scanner 初版却用了普通模块全局变量。修复：(a) `_status`/`_scan_thread`/`_stop_event`/`_lock` 全部持久化到 `sys._unified_*`，每次重导入只 re-bind 同一对象；(b) `use_deepseek` 改为线程 args 传入而非读模块全局；(c) 前端 `pollUnifiedStatus` 在 idle 时同步 UI 为"未在运行"并重置按钮。**教训：任何被 `_with_stock_imports` 重新导入的扫描器模块，运行期可变状态必须挂在 `sys` 上，不能放模块级全局。** 需重启 Flask 服务加载修复。
13. **(2026-07-01) 关键 bug 修复 — 统一扫描线程 ImportError STOCK_DATA_DIR**: 用户重启后测试，后台报 `ImportError: cannot import name 'STOCK_DATA_DIR' from 'config' (C:\jarvis\scripts\rag\..\config.py)`。根因：统一扫描后台线程在 `_with_stock_imports` 装饰器 `finally` 退出后才运行，此时装饰器已把 `sys.modules['config']` 恢复成 RAG config（无 `STOCK_DATA_DIR`）并删除所有 stock 模块缓存；线程里 `import right_side_scanner` 触发其顶层 `from config import STOCK_DATA_DIR` 失败。`scanner._run_scan_inner` 在线程开头用 `importlib.util.spec_from_file_location` 强制重载 stock config 规避此问题，unified_scanner 漏了。修复：新增 `_ensure_stock_config()`（强制加载 stock config 到 `sys.modules['config']` + pop 所有 stale stock 模块），在 `_run_unified_inner` 开头、左侧扫描前、右侧扫描前各调用一次（右侧尤其需要，因为 right_side 子线程不自修复 config，且 left 阶段状态轮询可能把 config 翻回 RAG）。烟雾测试：在 `sys.modules['config']` 为 RAG 风格 config 时启动统一扫描，线程成功进入行情抓取阶段无 ImportError。**教训：后台线程若 import 依赖 stock config 的模块，必须在线程内自行强制重载 stock config，不能依赖请求装饰器留下的 config 状态。**
14. **(2026-07-01) bug 修复 — 右侧扫描总市值单位错误导致 0 候选**: 用户反馈右侧始终"暂无右侧推荐"（16:13 独立扫描与 18:08 统一扫描均 0 picks, all_candidates_count=0）。根因：right_side_scanner Layer1 过滤 `df["总市值"].between(2e9, 50e9)` 注释写"20亿~500亿"按【元】算，但 akshare `stock_zh_a_spot_em` 的 总市值 单位是【万元】（验证：scanner 进度文件精工钢构 market_cap=624899，实际 62.5亿=6.25e9 元，差 1e4 倍）。`2e9 万元 = 20万亿` → 全市场无股票达标 → Layer1 直接 0 候选。修复：过滤前归一化——`if _mcap.max() < 1e10: _mcap *= 1e4`（万元→元，1e10 可区分万元量级 max~2e8 与元量级 max~2e12），再 `between(2e9, 50e9)`。**教训：akshare 各列单位不统一，总市值/流通市值是万元，成交额/最新价是元；过滤阈值必须先归一化单位。**
15. **(2026-07-01) 加固 — scanner LLM JSON 解析 regex 兜底**: DeepSeek 偶尔在 JSON 字符串值里输出未转义双引号（如 `不符合"追高是最大敌人"`）导致 `json.loads` 报 `Expecting ',' delimiter`。给 `_parse_llm_score` 加 `_extract_llm_fields_fallback`：json.loads 失败时按字段名 regex 提取，字符串值用 lookahead `"(?=\s*,|\s*\})` 判断真正结束引号（内嵌引号后跟中文不误判）。3 个真实失败用例验证全部成功提取 verdict/score/reason/risk/buy_high。

---

## Confirmed Assumptions (required)

- Standard 6-digit A-share symbols (e.g. `600519`) are expected and used throughout the system. Suffixes (e.g. `.SH`, `SZ`) are cleaned during mapping.
- DeepSeek's powerful reasoning capability (`deepseek-v4-pro`) is ideal for both deep short-term quantitative and long-term qualitative macro A-share analysis.

---

## Key Discoveries (required)

- The short-term scanner's local prompt previously didn't instruct on any specific holding period or profit target, leading to generic "now buy" judgments.
- The long-term scanner's mapping was strictly reliant on substring matching between hot sectors and theme industries, making it prone to missing prime industry leaders. Directly injecting the LLM's recommended theme stocks as candidates dramatically enhances the selection pool.
- (2026-07-01) 悖论根因：短期推荐(`scanner.py`)对精工钢构报告"缺少资金流向数据"——`stock_fund_flow_signals` 返回 `data_days<3` 时 `ff_signals={}`，scanner 用中性默认 ff_score=50 继续判断，未把缺数据当阻断项；而深度分析(`llm_reasoning.py`)拿到完整 10日资金面(净流出近1亿、3日净占比-15.79%)→ 看空。结论：深度分析更接近真相，短期推荐在缺关键数据下判断。
- (2026-07-01) XGBoost 排名误导：scanner 把 Alpha=1.5286 当强信号让出货股排名第一，但 XGBoost 给的实为"平"(34.1%, 置信度60%)，未量化主力大幅净流出卖压。纯 Alpha 排名需被资金面否决项约束。
- (2026-07-01) 当前 scanner 买入标准确认为左侧逻辑（吸筹期最佳买点、追高惩罚、低位抄底），无右侧交易推荐；追高惩罚等于封死右侧入场。用户理解正确。

---

## Runtime Evidence (include when relevant)

- Both modified Python scripts were compiled successfully using `py_compile` with zero syntax errors.
- Linter checks (`ReadLints`) returned clean.

---

## Current State (required)

- **Completed**: Short-term prompts (`scanner.py`) updated with 2 weeks to 2-3 months target horizon and 10%+ profit expectations, including deep-dive analysis guidelines. Completed code review fixes for conditional DeepSeek gating, type validation, and PDF formatting.
- **Completed**: Long-term scanner (`long_term_scanner.py`) updated to support up to 6 months to 1 year horizons, and direct stock recommendations under investment themes. Done code review fixes.
- **Completed**: Frontend `index.html` updated to render direct stock recommendations under each long-term theme block. Added XSS escaping.
- **Completed**: All changes verified, python compiled successfully, import tests passed. Code review loop closed and user accepted current state.
- **Design Approved (2026-07-01)**: 短期 vs 深度悖论修复方案 + 独立右侧交易扫描器设计已获用户批准，待实施。

---

## Next Steps (required)

1. **New Feature Initialization**: Define and design the "Mid-day/Overnight Speculative Stock Scanner" (超短线午盘/隔夜套利策略).
2. [ ] Research data availability during the A-share mid-day break (11:30 - 13:00) for morning-session momentum analysis.
3. [ ] Propose and brainstorm technical architecture and metrics for 12:30/午盘 scanning.
4. [ ] (2026-07-01) 实施 scanner.py 一致性修复：资金流向缺失硬门控 + Layer3 prompt 强化 + 缺数据降级 + final_score 资金面否决项。（已完成）
5. [ ] (2026-07-01) 新建 `right_side_scanner.py` 独立右侧交易扫描器（三层漏斗，资金反转入场确认）。（已完成）
6. [ ] (2026-07-01) `stock.py` 路由 + `index.html` 右侧推荐面板 + RAG 索引。（已完成）
7. [ ] (2026-07-01) 新增 `llm_reasoning.generate_prediction_verdict` 轻量深度复核 + scanner Phase 3.5 Top5 复核否决。（已完成）

---

## References (required)

- `scripts/stock/scanner.py` -- Short-term AI stock scanner
- `scripts/stock/long_term_scanner.py` -- Long-term AI stock scanner and trend analyzer
- `scripts/rag/templates/index.html` -- Frontend UI template with long-term rendering logic
