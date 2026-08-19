# Memory: Price Prediction Watchlist Sync

**Generated**: 2026-08-18 17:45 UTC+8
**Last updated**: 2026-08-18 18:20 UTC+8
**Project**: c:\jarvis
**Focus**: 明日价格预测的股票列表必须与自选股管理保持一致（先对齐现有结果，再改代码永久绑定）

---

## Goal & Scope (required)

「明日价格预测」弹窗里显示的股票必须来自「自选股管理」的当前自选股。先对现有 `train_progress.json` 做增删对齐，再改代码使以后打开/展示都只用当前自选股。

---

## Key Decisions (required)

1. **两者都要**：先对齐现有结果，再改代码以后永远跟自选股。Rejected: 只做一次数据对齐；只改代码不过滤存量。
2. **只对齐展示、现在不重训**：已不在自选的从结果里删掉；自选新增的先占位，等下次点「开始训练」才出预测。Rejected: 现在补训缺预测的股；整表重训。
3. **弹窗内所有带股票的区块都跟自选**：昨日验证、健康度、明日预测、逐股验证明细。不删各股历史预测日志文件。
4. **不改其他扫描器**（左右侧/优质低估等）。
5. **方案 A**：`/api/stock/train/status` 按当前自选投影；磁盘 `train_progress.json` 改写一次；缺预测/训练失败显示「待训练」。Rejected: 只改前端；只在自选增删时改 JSON。
6. **GET 不写文件**；投影纯函数；`aggregate_stats` 按当前自选现算。
7. **idle 且无 train_progress.json**：不编造表格。
8. **直接执行、不写正式计划**。

---

## Confirmed Assumptions (required)

- 训练入口 `api_stock_train_daily` 已经用 `watchlist.list_stocks()`；问题主要是上一轮 `train_progress.json` 残留已删除自选股，以及打开弹窗时未按当前自选过滤。
- 新增自选股在下次训练前可以占位（无预测数字）。
- 各股 `predictions_log.json` / `price_prediction.json` 保留，只从展示/status 里隐藏已移除的自选股。

---

## Constraints & Non-Goals (include when relevant)

- 现在不跑训练。
- 不删除各股历史预测日志。
- 不改左右侧/优质低估等其他扫描。

---

## Key Discoveries (required)

- 训练循环在 `scripts/rag/routes/stock.py` `api_stock_train_daily`：`list_stocks()` → 写入 `STOCK_REPORTS_ROOT/train_progress.json`。
- 前端 `pollTrainStatus` / `renderFullTrainReport` 直接渲染 status 的 `results`/`verifications`/`aggregate_stats`，没有再按当前 watchlist 过滤。
- 自选股文件：`{STOCK_REPORTS_ROOT}/watchlist.json`（默认 `C:/reports/stock/watchlist.json`）。
- 相关旧记忆：`memory-20260521-tomorrow-price-prediction-refactor.md`（模型/DeepSeek，不是本次名单对齐）。

---

## Current State (required)

- **Working**: 方案 A 已落地。`project_train_progress_to_watchlist` + status 投影 + 明日预测表「待训练」；`train_progress.json` 已从 39 只改为当前 7 只自选。pytest `tests/test_train_progress_watchlist.py` 7 passed。
- **Pending**: code review；用户下次点「开始训练」才会给 5 只新股和 588080 出预测。
- **Blocked**: 无

---

## Next Steps (required)

1. [x] Brainstorming：方案 A 已批准
2. [x] 对齐现有 `train_progress.json`（7 只：159570 有预测，588080 特征不足，5 只 pending）
3. [x] status API + 明日预测表永久按当前自选投影
4. [ ] 打开弹窗手验；需要数字时再点「开始训练」

---

## Notes for Next Session (include when relevant)

- 用户选了记忆 `memory-20260816-quality-undervalued-screener.md` 作为会话起点，但本任务与优质低估无关。
- 不要在未要求时 commit。

---

## References (required)

- `scripts/rag/routes/stock.py` — `/api/stock/train/daily`, `/api/stock/train/status`
- `scripts/rag/templates/index.html` — `renderFullTrainReport`, `pollTrainStatus`
- `scripts/stock/watchlist.py` — `list_stocks`
- `C:/reports/stock/watchlist.json` — 当前自选
- `C:/reports/stock/train_progress.json` — 上一轮预测结果

---

**Confirmed at**: 2026-08-18 17:45 UTC+8
