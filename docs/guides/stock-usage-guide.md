# Jarvis 股票分析系统实用指南

面向已启动 Jarvis、希望用内置股票功能做分析与决策参考的用户。技术名词保留英文（括号）说明。

---

## 1. 快速开始（Quick Start）

### 前提条件

- **Jarvis 已运行**：RAG Agent（`agent.py`）Web 界面可访问。
- **Ollama 已启动**：本机 `http://localhost:11434` 可访问；情绪分析、技术/基本面报告中的 LLM 摘要、AI 综合预测均依赖 Ollama。
- **akshare 可用**：用于拉取 A 股行情与新闻等数据。

### 安装股票模块依赖

在已激活的 Python 环境中执行：

```bash
pip install akshare pandas-ta xgboost scikit-learn
```

### 验证安装

```bash
python -c "import akshare; print('OK')"
```

终端输出 `OK` 即表示 akshare 导入正常。

### 工作目录说明

下文命令默认在 **`c:\jarvis\scripts\stock`** 下执行（脚本使用 `from config import ...`，需在该目录运行或保证 `PYTHONPATH` 包含此目录）。PowerShell 示例：

```powershell
cd c:\jarvis\scripts\stock
```

---

## 2. 管理关注列表（Watchlist）

### 命令行

添加股票（代码、名称、行业均为可选参数，按顺序传入）：

```powershell
cd c:\jarvis\scripts\stock
python watchlist.py add 600519 贵州茅台 白酒
python watchlist.py add 300750 宁德时代 新能源
```

查看列表：

```bash
python watchlist.py list
```

示例输出（格式示意）：

```text
  600519  贵州茅台        白酒        (2026-04-01)
  300750  宁德时代        新能源      (2026-04-01)
```

删除：

```bash
python watchlist.py remove 600519
```

带本地缓存价格的列表（需已拉取过 `realtime.json`）：

```bash
python watchlist.py prices
```

示例：

```text
  600519  贵州茅台        价格: 1680.0  涨跌: 1.2%
```

### Web UI（agent.py）

在 Jarvis 网页侧栏展开 **Stock** 工具栏：

- 打开 **「股票分析」** 相关弹窗，可输入代码并触发分析。
- **关注列表**：通过界面添加/删除标的、刷新全表数据（底层调用 `/api/stock/watchlist` 等接口），与命令行共用同一份 `watchlist.json`。

💡 **提示**：关注列表文件路径由环境变量 `STOCK_REPORTS_ROOT` 决定，默认为 `C:/reports/stock/watchlist.json`（见第 14 节）。

---

## 3. 获取市场数据（Fetching Market Data）

### 单只股票一键更新

```bash
python fetch_market_data.py 600519
```

无参数时默认示例代码 `600519`。脚本会调用 `update_stock_data`：拉取日线、公司概况、新闻等，并在终端打印 JSON 摘要（含 `daily_rows`、`news_count`、`errors` 等）。

### 批量刷新关注列表

```bash
python watchlist.py refresh
```

对关注列表中每只股票依次更新数据。

### 数据存储位置

默认根目录：**`C:/reports/stock/`**（可用 `STOCK_REPORTS_ROOT` 修改）。

单标的目录：**`C:/reports/stock/data/{symbol}/`**

| 文件/目录 | 说明 |
|-----------|------|
| `daily.csv` | 日线 OHLCV（技术分析输入） |
| `realtime.json` | 最新价、涨跌幅、PE/PB、市值等快照 |
| `profile.json` | 公司简称、行业、上市时间等 |
| `news/` | 按日期保存的新闻 JSON，如 `news/2026-04-14.json` |
| `fundamentals.json` | 运行基本面拉取后的财务摘要（由 `fundamental_analysis` 写入） |

---

## 4. 技术分析（Technical Analysis）

### 命令

```bash
python technical_analysis.py 600519
```

输出为 **JSON**（含 `signals`、`indicators`、`patterns`、`support_resistance`、`overall`），并写入同目录下 `technical.json`。

生成中文 **Markdown** 报告并保存文件：

```bash
python report_technical.py 600519
```

报告路径：`data/{symbol}/technical-report.md`。

### 如何解读

- **综合判断（overall）**：由脚本对多条子信号统计偏多/偏空后得到，如 `看涨`、`看跌`、`偏多`、`偏空`、`中性`。
- **各指标信号（signals）**：例如 **均线趋势**、**MACD**（金叉/死叉/多头/空头）、**RSI**（超买/超卖）、**KDJ**、**布林带**、**成交量** 等；表中会标注看涨/看跌/中性类描述。
- **K线形态（patterns）**：如锤子线、射击之星、吞没、早晨之星、MA 金叉/死叉、放量突破等；每项含 `direction`（看涨/看跌/待确认）、`strength`、`desc`。
- **支撑/阻力（support_resistance）**：枢轴点、支撑 1/2、阻力 1/2，以及回看窗口内 **近期高/低点**。实盘可将止损设在支撑下方、目标参考阻力区域，并结合量能与其他维度验证。

### 示例：贵州茅台（600519）报告阅读思路（演示性）

假设报告中：**综合判断** 为「偏多」，**RSI** 为「中性」，**MACD** 为「多头」，形态未出现强烈反转信号，**阻力1** 高于现价、**支撑1** 低于现价：

- 短线思路：偏多但非极端超买时，可侧重观察能否放量突破阻力1；若缩量回踩支撑1 企稳，技术派常作为博弈反弹的结构位。
- 若 **综合判断** 与 **形态** 方向冲突，宜降低单维度的权重，等待信号收敛。

⚠️ **注意**：技术分析反映的是历史价量规律，不保证未来走势。

---

## 5. 基本面分析（Fundamental Analysis）

### 命令

```bash
python fundamental_analysis.py 600519
```

会拉取或复用缓存财务数据，在终端打印 Markdown 报告，并写入 **`fundamental-report.md`** 与 **`fundamentals.json`**。

### 综合评分档位（解读用）

| 总分区间 | 含义（解读参考） |
|----------|------------------|
| **80+** | 优秀公司 |
| **65–80** | 良好 |
| **50–65** | 一般 |
| **&lt;50** | 较弱 |

报告中还会显示星级文案（如「偏弱」「较差」等细分档），可与上表对照理解。

### 各维度与权重（与代码一致）

| 维度 | 权重 | 关注点 |
|------|------|--------|
| **盈利能力** | 25% | ROE、净利率等 |
| **成长性** | 25% | 营收/利润同比 |
| **估值水平** | 20% | PE、PB 等 |
| **财务健康** | 15% | 资产负债率等 |
| **综合因素** | 15% | 市值规模等 |

### 何时最有用

- 中长线配置、筛选护城河与盈利质量时。
- 与技术信号冲突时：高估值+技术超买，或低估值+技术超卖，可辅助判断是「趋势延续」还是「均值回归」风险。

---

## 6. 新闻情绪分析（News Sentiment）

### 数据从哪来

`fetch_market_data.py` / `watchlist.py refresh` 会尝试拉取新闻并写入 `news/`。

### 命令

```bash
python sentiment.py 600519
```

依赖 Ollama：对新闻条目调用 LLM，输出 **-1.0～+1.0** 的单条得分，汇总为 **`daily_score`**（约最近若干天、最多分析 20 条），结果写入 `sentiment.json`，并在终端打印 Markdown 摘要。

### 解读情绪得分

- **接近 +1.0**：整体偏利好叙事。
- **接近 -1.0**：偏利空。
- **0 附近**：中性或利好利空对冲。

### 正面/负面新闻的影响

- **短期**：情绪可放大波动，尤其与题材、政策关键词相关时。
- **长期**：需区分「一次性消息」与「基本面变化」；可对照 `top_positive` / `top_negative` 标题快速抓住极端条目。

---

## 7. 机器学习预测（ML / XGBoost）

### 命令

```bash
python model_xgboost.py 600519
```

训练/预测结果写入 **`xgb_prediction.json`**，模型在 **`C:/reports/stock/models/{symbol}/`**，并生成 **`xgb-report.md`**。

### 如何解读

- **预测方向**：三分类 **涨 / 平 / 跌**（约等于未来若干交易日方向，具体以特征与标签定义为准）。
- **置信度（confidence）**  
  - **≥70%**：高  
  - **50%–70%**：中  
  - **&lt;50%**：低  
- **概率分布（probabilities）**：三项概率之和为 1，可看「次优方向」是否接近主方向（胶着时实操宜保守）。
- **特征重要性（feature_importance）**：模型更依赖哪些因子（如 RSI、均线距离、波动率等）；**重要 ≠ 因果**，仅说明在该训练集上的贡献。
- **Walk-Forward 准确率**：滑动窗口下历史回测意义上的命中比例；**历史表现不代表未来**。

### ⚠️ 重要提醒（局限性）

- 市场结构突变、政策与极端行情会导致特征分布漂移，模型可能系统性失效。
- 标签与预测 horizon 由工程实现固定，**不等于**「稳赚策略」。
- 请仅将 ML 输出作为 **辅助信息**，结合风控与个人承受能力决策。

---

## 8. AI 综合预测（LLM Comprehensive Prediction）

### 命令

```bash
python llm_reasoning.py 600519
```

脚本会汇总技术面、基本面评分、情绪、（若存在）XGBoost 结果，构造提示词调用 Ollama，生成中文报告并保存 **`prediction-report.md`**。

### AI 如何整合信息

将结构化摘要注入 LLM，由模型输出连贯论述，通常覆盖：方向判断、信心水平、时间范围、理由、风险、操作建议、关键价位等（以系统提示为准）。

### 报告阅读与决策

- 把 AI 结论当作 **辩论稿**：核对是否与技术/基本面/情绪一致。
- **一致性强**：可提高你对计划执行的信心，但仍需自行设定止损与仓位。
- **明显分歧**：优先排查数据是否过期（是否未 refresh）、新闻是否突发、模型是否胡编（需对照原始 JSON/报告）。

💡 **提示**：聊天主 Agent 的模型可能由 `RAG_AGENT_MODEL` 控制；股票模块内 Ollama 地址与模型别名见 `scripts/stock/config.py`（第 14 节）。

---

## 9. 完整分析工作流（Daily Workflow）

### 推荐命令顺序（单标的）

1. **刷新数据**（若在关注列表中可批量）：  
   `python watchlist.py refresh`  
   或单只：`python fetch_market_data.py <symbol>`
2. **技术面**：`python report_technical.py <symbol>`
3. **基本面**：`python fundamental_analysis.py <symbol>`
4. **情绪**：`python sentiment.py <symbol>`
5. **ML**：`python model_xgboost.py <symbol>`
6. **AI 综合**：`python llm_reasoning.py <symbol>`

### Web UI 一键操作

在 **Stock** 工具栏中输入代码后，可使用 **全面分析**（一次触发技术、基本面、情绪、XGBoost，并生成 AI 综合预测）、或单独点击 **技术分析 / 基本面 / 情绪分析 / ML预测**。关注列表支持在界面内刷新全部标的。

📋 **检查清单（每日快速版）**

- [ ] 数据已更新（无大量 `errors`）
- [ ] 技术 `overall` 与关键支撑阻力已浏览
- [ ] 基本面总分与估值是否匹配你的投资周期
- [ ] 情绪是否极端（防追高风险）
- [ ] ML 置信度与 Walk-Forward 是否支持你的假设
- [ ] AI 报告是否与其他维度严重矛盾

---

## 10. AI 全市场扫描推荐（AI Stock Scanner）

### 功能概述

除了对单只股票进行深度分析外，Jarvis 还提供 **AI 全市场扫描推荐** 功能：自动扫描全 A 股市场（通常 5000+ 只），通过三层筛选流程，最终给出 **TOP 5 推荐股票**，并附带 AI 评分、推荐理由、风险提示和建议买入价位区间。

### 三层扫描流程

| 层级 | 名称 | 说明 |
|------|------|------|
| **Layer 1** | 全市场快速筛选 | 从 ~5000 只 A 股中按5个条件筛选：非ST、涨跌幅 -3%~+8%、换手率 ≥1%、成交额 ≥5000万、0 < 动态PE < 100。热门板块股票加分。取 **前100只** 候选。 |
| **Layer 2** | 详细批量分析 | 对100只候选逐一进行技术分析（指标计算、信号识别）和情绪分析，综合得分排名。取 **前20只**。 |
| **Layer 3** | LLM 综合评分 | 使用本地 LLM（Ollama）对20只候选进行综合评分，输出推荐理由、风险提示和建议买入价位。取 **TOP 5**。 |

### Layer 3 与 Ollama（thinking 模型说明）

**（LLM 调用修复）** 实现位于 **`scanner.py`** 的 **`_layer3_llm_rank()`**。

早期 Layer 3 通过 Ollama **`/api/generate`** 调用 LLM。若选用 **带思考链（thinking chain）** 的模型（例如 **`qwen3.5:4b`**），模型可能把 **`num_predict`（如 500）** 的 token 预算全部消耗在 **`<think>`** 等思考块内，导致没有余量输出业务 JSON，从而触发 **「LLM输出解析失败, 基于数值分析」** 回退，表现为 **所有标的** 都无法得到真实的 **AI 推理（reasoning）** 与 **建议买入价（buy price / buy range）**。

当前实现已改为 **`/api/chat`**：使用 **`messages`**（含 **system** 角色约束「只输出 JSON」）并在请求 JSON 中设置 **`"think": false`**（关闭 thinking 模式），在支持的 Ollama 版本上让模型在有限 **`num_predict`** 内直接输出可解析的 JSON，从而 **LLM 评分（LLM scoring）** 真正生效。解析仍失败时仍会回退到数值评分（同一函数内处理）。

### 使用方式

**Web UI**：点击工具栏 **「🌟 AI推荐」** 按钮打开扫描面板，点击 **「开始扫描」** 启动后台扫描。进度条会实时更新各阶段状态。扫描完成后显示 TOP 5 推荐卡片，包含：

- 综合得分（0-100）
- 最新价、涨跌幅、PE、技术/情绪得分
- 建议买入区间（由 LLM 给出）
- 推荐理由和主要风险

**历史记录**：点击 **「📋 历史记录」** 按钮，通过**日期下拉框**选择历史扫描结果查看。每天的扫描结果独立保存，不会互相覆盖。

### 数据存储

扫描结果保存在 `C:/reports/stock/scans/` 目录下：

| 文件 | 说明 |
|------|------|
| `{YYYY-MM-DD}.json` | 当天扫描完整结果（meta、top_picks、candidates） |
| `{YYYY-MM-DD}-report.md` | 当天推荐 Markdown 报告 |
| `scan_progress.json` | 实时扫描进度状态 |
| `history.json` | 历史推荐汇总（含收益追踪） |

### 数据覆盖策略

- **同一天重复运行**：覆盖当天的扫描结果
- **不同天运行**：生成新文件，历史数据完整保留
- 个股数据（`data/{symbol}/daily.csv` 等）每次覆盖；新闻按日期保存，不同天独立

### 相关 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/stock/scan/start` | 启动后台扫描 |
| POST | `/api/stock/scan/stop` | 停止当前扫描 |
| GET | `/api/stock/scan/status` | 获取扫描进度和结果 |
| GET | `/api/stock/scan/dates` | 列出所有可用扫描日期 |
| GET | `/api/stock/scan/result/{date}` | 按日期获取历史扫描结果 |
| GET | `/api/stock/scan/history` | 获取历史推荐汇总 |

### 注意事项

- 全市场扫描需要网络连接（akshare 数据源），Layer 3 需要 Ollama 运行
- 完整扫描通常需要 10–20 分钟（取决于网络和 LLM 速度）
- 扫描中途可随时停止，下次可从断点继续
- 建议买入价位仅为 AI 参考，不构成投资建议

---

## 11. 明日价格预测 (Next-Day Price Prediction)

### 功能简介

**明日价格预测** 是独立于第 7 节「方向三分类」ML 的新能力：针对 **关注列表（watchlist）** 中的标的，用 **XGBoost 回归（XGBoost regression）** 估计 **下一交易日** 的 **收盘价（close）**、**最高价（high）**、**最低价（low）**。输出为连续价格数值，便于与当日行情对照；**不构成买卖建议**，仅作研究辅助。

### 如何使用

- **Web UI**：在 **Stock** 工具栏点击 **「🎯 价格预测」** 按钮，手动触发训练；系统对 **全部关注列表股票** 依次训练/更新模型并写入预测与追踪数据。
- 训练在后台进行，可通过 **GET `/api/stock/train/status`** 查看进度（见下文 API）。

### 每日训练工作流（Web UI 按钮）

点击 **「开始训练」**（或等价入口触发 **POST `/api/stock/train/daily`**）后，后台对关注列表中每只股票按顺序执行（与界面按钮的 **每日工作流（daily workflow）** 一致：**更新行情（update market data）→ 回填昨日实际（backfill actuals）→ 对照预测做验证（verify）→ 训练新模型（train）→ 记录新预测并汇总健康度（record + health）**）：

1. **更新市场数据（update market data）**：拉取/刷新该标的日线等数据。  
2. **回填昨日实际价（backfill actuals）**：将上一期预测对应交易日的真实 **OHLC** 写入 **`predictions_log.json`**，并计算 **`error_pct_close` / `error_pct_high` / `error_pct_low`**。  
3. **对照预测做验证（verify against predictions）**：调用 **`get_latest_verification(symbol)`**，取刚回填后的 **最近一条带实际值的记录**，汇总进本次训练的 **`verifications`**，供界面 **「昨日预测 vs 实际」** 展示。  
4. **训练新模型（train new models）**：重新训练/更新三个价位回归模型并生成 **明日预测（next-day predictions）**。  
5. **记录新预测并汇总健康度（record prediction + health）**：调用 **`record_prediction`** 把本轮预测写入 **`predictions_log.json`**；再经 **`get_accuracy_stats`**（内部使用 **`_calc_model_health(filled)`**）生成 **健康等级（health grade）**、**文案（message）** 与 **趋势（trend）**，一并写入本次 **`results`**，供 **模型健康度** 与 **明日价格预测** 表格中的 **健康** 列展示。

### 训练流程

- **特征（features）**：基于历史 **OHLCV** 与 **`features.py`** 中工程化后的 **技术指标（technical indicators）** 列，与日线数据对齐后作为模型输入。
- **模型（models）**：每个标的训练 **三个回归模型**：`close`、`high`、`low`，分别预测下一交易日对应价位。
- **验证（validation）**：采用 **Walk-Forward（滚动前推）** 方式划分训练/验证，报告 **MAE（平均绝对误差）**、**MAPE（平均绝对百分比误差）** 等指标，用于衡量历史拟合与样本外表现；**历史指标不保证未来**。

### 训练完成后的界面区块

当 **GET `/api/stock/train/status`** 返回 **`status: "done"`** 时，前端会渲染完整报告，通常包含四块（无数据时相应区块可能不显示）：

1. **昨日预测验证**：展示 **`verifications`** 中每条记录的 **预测收盘/最高/最低 vs 实际收盘/最高/最低**，并附 **方向（direction）** 是否命中。回填时在 **`prediction_tracker.py`** 中除 **`error_pct_close`** 外，同时计算 **`error_pct_high`、`error_pct_low`**（三根价位的 **绝对百分比误差（absolute percentage error）**）。界面表格以 **「误差」列** 突出展示 **收盘误差 %**（**`error_pct_close`**）；**最高/最低** 以 **价格对照** 为主，**`error_pct_high` / `error_pct_low`** 已写入每条验证记录，并与 **GET `/api/stock/predict/{symbol}`** 返回的 **high/low MAPE** 类汇总一致。  
2. **模型健康度**：每张关注标的的 **健康等级卡片（health grade）**，含 **MAPE**、样本量及 **趋势箭头（trend）**（改善/持平/变差）。  
3. **明日价格预测**：新预测表格，含 **当前价（current price）** 与 **健康等级列**。  
4. **训练失败**：列出本轮 **`results`** 中带 **`error`** 的标的及原因（若有）。

### 预测追踪系统

模块 **`prediction_tracker.py`** 实现 **预测追踪（prediction tracking）**：

- **自动记录（auto-record）**：在训练/预测流程中写入当次预测结果。
- **实际价回填（backfill）**：在 **下一次训练运行** 时，用已发生的真实 OHLC 对尚未回填的预测进行 **实际价格（actuals）回填**。
- **误差百分比（error %）**：除 **收盘价（close）** 的 **`error_pct_close`** 外，回填后同时计算 **最高价（high）**、**最低价（low）** 的 **`error_pct_high`**、**error_pct_low**（相对实际价的绝对百分比误差），便于评估三根 K 线价位的预测质量。
- **准确度统计**：在回填基础上计算 **MAPE**、**MAE**、各价位的平均误差指标，以及 **方向准确度（direction accuracy）**（预测相对前一日收盘的涨跌方向是否与实际一致，定义以代码为准）。
- **最新一条验证（latest verification）**：函数 **`get_latest_verification(symbol)`** 返回该标的 **最近一条已回填实际数据** 的日志条目，供界面展示 **「昨日预测 vs 实际（predicted vs actual）」** 对照。
- **模型健康度（model health）**：函数 **`_calc_model_health(filled)`**（对 **`get_accuracy_stats`** 暴露为返回体中的 **`health`**）基于 **最近 5 次** 已验证样本的 **MAPE（收盘价百分比误差）** 与 **方向准确率** 给出等级与文案（样本总数不足 5 次时为 **`N/A`**）：
  - **Grade A**（绿色）：MAPE ≤ **1.5%** 且方向准确率 ≥ **70%** — 「模型表现优秀」
  - **Grade B**（蓝色）：MAPE ≤ **3%** 且方向准确率 ≥ **50%** — 「模型表现良好」
  - **Grade C**（黄色）：MAPE ≤ **5%** **或** 方向准确率 ≥ **40%** — 「模型表现一般，建议观察」
  - **Grade D**（红色）：更差 — 「模型表现差，建议考虑更换算法」
  - **趋势（trend）**：当累计已验证样本 **≥10** 条时，对比 **最近 5 条** 与 **其前 5 条** 的 MAPE，输出 **`improving` / `stable` / `degrading`**（改善 / 持平 / 变差）。

### 数据存储

默认根目录仍由 **`STOCK_REPORTS_ROOT`** 决定（默认 `C:/reports/stock/`）。与本功能相关路径示例：

| 路径 | 说明 |
|------|------|
| `data/{symbol}/price_prediction.json` | 当前预测结果与展示用摘要 |
| `data/{symbol}/predictions_log.json` | 预测历史与追踪日志（含回填后的对照） |
| `models/{symbol}/price_close_model.json` | 收盘价回归模型 |
| `models/{symbol}/price_high_model.json` | 最高价回归模型 |
| `models/{symbol}/price_low_model.json` | 最低价回归模型 |

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/stock/train/daily` | **异步**启动对 **全部关注列表股票** 的每日训练；立即返回 **`{ ok, message }`**（或占用中错误）。**不包含**完整 **`results` / `verifications`**，须在结束后用下方 **GET status** 或读取 **`train_progress.json`**。 |
| GET | `/api/stock/train/status` | 查询训练进度；运行中返回 **`completed` / `total` / `current`** 等。完成（**`status: "done"`**）时，响应体与 **`train_progress.json`** 一致，包含 **`results`** 与 **`verifications`** 数组（每只股票一条 **`get_latest_verification()`** 快照，含 **`symbol` / `name`** 及 **`error_pct_*`** 等字段），供前端渲染 **昨日预测验证**、**模型健康度**、**明日价格预测**、**训练失败** 四块。 |
| GET | `/api/stock/predict/{symbol}` | 获取指定代码的 **预测值** 与 **准确度统计（accuracy stats）**（内含 **`health`**、**`stats`** 中的 **`avg_mape_high` / `avg_mape_low`** 等） |

⚠️ **注意**：价格预测依赖数据质量与市场平稳性；极端行情与分布漂移会导致误差放大。请与技术面、基本面等维度交叉阅读，勿单独作为交易依据。

---

## 12. 市场信号（Market Signals）

通过 UI 中的 **"市场信号"** 按钮或 API `/api/stock/signals` 获取全局市场情绪和风险警报。

### 12.1 恐慌与贪婪指数（Fear & Greed）

`market_sentiment.py` 从 CNN Fear & Greed Index 获取当前市场情绪值（0–100），并分为 5 级：

| 分数范围 | 情绪 | 含义 |
|----------|------|------|
| 0–24 | 极度恐惧 | 市场恐慌抛售，可能出现超跌反弹机会 |
| 25–44 | 恐惧 | 投资者信心不足 |
| 45–55 | 中性 | 情绪平稳 |
| 56–74 | 贪婪 | 市场偏乐观 |
| 75–100 | 极度贪婪 | 过热信号，警惕回调风险 |

### 12.2 VIX 波动率指数

同时获取 CBOE VIX 值。VIX > 30 一般视为市场高波动/恐慌期。

### 12.3 黑天鹅检测（Black Swan Detector）

`black_swan_detector.py` 读取 Daily Fetch 产生的 `world-news-data.json`，通过关键词匹配（如 war、sanctions、crash、pandemic 等 30+ 模式）扫描国际新闻。

- 若命中，返回 `severity`（low / medium / high / critical）和受影响行业。
- **high/critical** 级别的事件会在 UI 中以红色警报展示。
- 源数据来自 Daily Fetch 的世界新闻，因此需先运行 Daily Fetch 以获取最新数据。

### 12.4 API

```
GET /api/stock/signals
→ { "fear_greed": {...}, "vix": {...}, "black_swan": {...} }
```

---

## 13. 投资决策参考（非投顾建议）

本节为 **通用框架**，不构成任何证券投资建议。

- **多维度综合**：至少交叉验证趋势（技术）、质地（基本面）、叙事（情绪）、统计模型（ML）四者中的三项。
- **信号一致性**：多源同向时，计划可更清晰；分歧时缩小仓位或观望。
- **买入 / 持有 / 卖出参考**  
  - 长线质优：基本面高分 + 技术未严重破位，情绪/ML 仅作择时参考。  
  - 短线博弈：技术形态与量能优先，情绪为辅，基本面过滤「雷区」。  
- **仓位**：单标的不宜过重；首次建仓可分批，避免一次押注模型方向。
- **止损**：可结合技术支撑、ATR%、或固定比例止损；触发后执行纪律比「再等等」更重要。

⚠️ **合规提示**：股市有风险，过往分析与模型表现不预示未来结果。

---

## 14. 常见问题（FAQ）

**Q：akshare 获取数据失败怎么办？**  
检查网络、数据源是否限流；稍后重试。若配置了代理，设置 `STOCK_PROXY`（见第 14 节）。日线失败时模块可能尝试备用接口，仍失败则查看命令输出中的 `errors` 字段。

**Q：Ollama 太慢怎么办？**  
换更小模型（如将 `OLLAMA_MODEL_FAST` 设为更轻的已下载模型）、关闭其他占 GPU/CPU 的任务；情绪分析条数多时会串行调用，可先减少新闻量或仅跑必要步骤。

**Q：数据存在哪里？如何清理？**  
默认 `C:/reports/stock/`。删除 `data/{symbol}` 可清空该标的缓存；删除整个 `data` 需自行承担重建成本。模型在 `models/{symbol}`。

**Q：为什么预测不准？**  
市场非平稳、过拟合、特征滞后、标签定义与实盘不匹配等均会导致偏差。把预测当作概率与风险管理的输入，而非圣杯。

**Q：如何添加新的股票指标？**  
在 `technical_analysis.py` 的指标计算与 `evaluate_signals` 中扩展；若在 ML 中使用，需在 `features.py` 增加特征列并保持列名与训练一致。

---

## 15. 配置说明（Configuration）

环境与默认值以 **`c:\jarvis\scripts\stock\config.py`** 为准。AI 扫描相关常量（`LAYER2_CANDIDATE_CAP`、`LAYER3_CAP`、`TOP_N`）在 `scanner.py` 顶部定义。

| 变量 | 作用 |
|------|------|
| **`STOCK_REPORTS_ROOT`** | 股票根目录（默认 `C:/reports/stock`），其下含 `data`、`models`、`.cache`、`watchlist.json` |
| **`STOCK_PROXY`** | HTTP/SOCKS 代理，供外网请求使用（若需要） |
| **`OLLAMA_HOST`** | Ollama API 地址（默认 `http://localhost:11434`） |
| **`OLLAMA_MODEL_FAST`** / **`OLLAMA_MODEL_NORMAL`** / **`OLLAMA_MODEL_HEAVY`** | 不同任务选用的模型名（见 `MODEL_USAGE` 字典） |

**修改报告与数据路径**：设置 `STOCK_REPORTS_ROOT` 后重启相关进程。

**修改 Ollama 模型**：编辑上述环境变量或 `config.py` 中默认值；确保 `ollama pull` 已拉取对应模型。

**Jarvis 主聊天模型**：`agent.py` 中主对话模型常由 **`RAG_AGENT_MODEL`** 覆盖默认 `OLLAMA_MODEL`，与股票脚本的 `OLLAMA_MODEL_*` 可分别配置。

**代理**：企业网络或跨境访问数据源时，配置 `STOCK_PROXY`；Ollama 本地一般无需代理。

---

*文档对应 Jarvis `scripts/stock/` 模块与 `agent.py` 内 Stock API/Web UI；若代码变更，请以仓库内实现为准。*
