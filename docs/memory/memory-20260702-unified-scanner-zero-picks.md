# Memory: 统一扫描器 0 推荐修复 (XGBoost 路径缺失富化)

- **日期**: 2026-07-02
- **关联**: `docs/memory/memory-20260702-stock-module-fixes.md`（同日早先的 config/sentiment/Ollama 修复）
- **症状**: "AI 股票推荐（左侧+右侧 · 共享数据）"左右侧都 0 推荐，连续 2 天（07-01、07-02）。

## 根因（修正后定论）

**不是"真的没好股票"，是 XGBoost Layer2 路径缺失 per-stock 富化。**

`scanner.py:_execute_layer2_and_3` 流程：
1. Layer2 走 `model_cross_sectional.cross_sectional_rank`（`layer2_mode=xgb_cross_sectional`）。
2. `cross_sectional_rank` **只给候选加** `score_l2 / xgb_rank / industry / xgb_alpha / model_ndcg`，**完全不取** 资金流向 / 基本面 / 技术面 / 信号。
3. 原规则路径 `_layer2_rule_scoring` 会顺带富化这些字段，但 XGBoost 路径取代它后**富化逻辑被整体跳过**。
4. Layer2→Layer3 之间**没有富化步骤** → Layer3 的 `_build_deepseek_scoring_prompt` 读 `ff_signals / fund_dimensions / signals` 全为空 → LLM reasoning 全是"数据缺失严重，无资金流向/基本面/技术面指标" → 30/32 观望、0 买入 → `top_picks=0`。

### 证据
- `C:\reports\stock\scans\2026-07-02.json`：`layer2_count=32`, `top_picks=0`，候选 `final_score` 有 65/65/60/60（≥`MIN_BUYABILITY_SCORE=60`）但 `verdict` 全是"观望"。
- `scan_progress.json` 的 `layer2_results`：32 只候选 **无** `ff_signals/ff_data_missing/fund_dimensions/signals` 字段，`ff_score/fund_score/tech_score` 全 `None`，`score_l2≈0.22`（XGBoost 分）。
- LLM reasoning（local + deepseek 两条）都说"数据缺失严重/缺乏关键数据"。

### 次要问题（真实但非主因）
东方财富资金流向接口在突发请求下断连：实测 `601016/300358` 报 `Connection aborted, RemoteDisconnected`，`000026/300573` 成功。原 `fetch_stock_fund_flow` 只重试 2 次、线性 1.5s，扫描突发下大面积失败。但这不是 0 推荐主因——XGBoost 路径压根没去取资金流向。

## 修复（2 文件）

### `scripts/stock/scanner.py`
1. **抽取 `_enrich_one(stock)`**：把 `_layer2_rule_scoring` 里的技术面/基本面/情绪/资金流向富化逻辑抽成独立函数，填 `signals/rsi/overbought/tech_score/fund_dimensions/fund_score/sentiment_score/ff_signals/ff_data_missing/ff_score`，**不算 `score_l2`**（由调用方决定：规则路径加权算总分，XGBoost 路径保留自己的 `score_l2`）。
2. `_layer2_rule_scoring` 改为调用 `_enrich_one(stock)` 后再加权算 `score_l2`（行为不变）。
3. **在 `_execute_layer2_and_3` 的 XGBoost 排序后、Layer3 前插入 Layer 2.5 富化步骤**：对每只候选调用 `_enrich_one`（带 stop 检查、`progress["status"]="layer2_enrich"`、`enriched_count` 进度持久化）。用 `any("ff_signals" not in s for s in all_l2)` 判断是否需要富化（规则回退路径已自带富化，不重复）。

### `scripts/stock/china_market_data.py`
- `fetch_stock_fund_flow` 重试从 2 次线性改为 **4 次指数退避+抖动**（`1.5*2^attempt + random(0,0.5)` → 1.5/3/6s），应对东方财富突发断连。缓存仍 8h 持久（`_CACHE_FUND_FLOW/{symbol}.csv`）。

## 验证
- 语法 OK、无 lint 错误。
- `_enrich_one` 实测：`000026` → `ff_signals.data_days=120, ff_data_missing=False, ff_score=90.4, fund_score=37.2, signals 5条`；`300573` → `data_days=120, ff_score=55, fund_score=78.5, signals 5条`。
- 富化后 `_build_deepseek_scoring_prompt` 输出含真实"资金流向详情/基本面详情/技术面信号"（修复前是"无信号数据/无基本面数据"）。
- **未跑完整扫描**：需重启 Jarvis 加载新代码后由用户跑一次验证非零推荐。

## 关键教训
- 当一条新路径（XGBoost）取代旧路径（rule）的某一步时，要检查旧路径里**附带的副作用**（如富化）是否需要在新路径后单独补一步。XGBoost 只排序不富化，是典型的"主功能迁移了、附带能力丢了"。
- LLM 批量判"观望/数据缺失"且 reasoning 高度同质化时，优先怀疑**输入数据为空**而非 LLM 本身保守。
