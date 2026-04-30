# Stock 模块详细文档索引

**生成日期**: 2026-04-27
**文档数量**: 21 个模块文档
**文档语言**: 中文
**目的**: 为每个 stock 功能模块提供详细的技术实现与金融理论文档，便于学习和后续调整

---

## 文档结构说明

每个模块文档包含以下统一章节：

1. **模块概述** — 核心职责、系统定位、依赖关系
2. **金融理论基础** — 涉及的金融/投资理论、A股特殊适用性
3. **技术实现详解** — 数据结构、函数接口、算法逻辑
4. **外部依赖与数据源** — 第三方库、API、缓存策略
5. **配置项与可调参数** — 参数说明、默认值、调优建议
6. **使用示例与工作流** — 调用方式、模块协作
7. **已知限制与改进方向** — 局限性、优化方向

---

## 模块分类索引

### 基础设施层

| 模块 | 文档 | 说明 |
|------|------|------|
| `config.py` | [config.md](./config.md) | 中央配置：路径、Ollama/DeepSeek模型设置、API密钥管理 |
| `watchlist.py` | [watchlist.md](./watchlist.md) | 自选股管理：CRUD操作、价格富化、搜索 |

### 数据采集层

| 模块 | 文档 | 说明 |
|------|------|------|
| `fetch_market_data.py` | [fetch_market_data.md](./fetch_market_data.md) | 行情数据获取：OHLCV、实时报价、公司资料、新闻（akshare+新浪+东财） |
| `china_market_data.py` | [china_market_data.md](./china_market_data.md) | A股特色数据：北向资金、资金流向、龙虎榜、两融、国家队ETF、涨跌停 |
| `hot_sectors.py` | [hot_sectors.md](./hot_sectors.md) | 热门概念板块获取与缓存 |

### 分析引擎层

| 模块 | 文档 | 说明 |
|------|------|------|
| `technical_analysis.py` | [technical_analysis.md](./technical_analysis.md) | 技术分析：指标计算（MA/MACD/RSI/KDJ/BB/OBV/ATR）、信号评估、形态识别、支撑阻力 |
| `fundamental_analysis.py` | [fundamental_analysis.md](./fundamental_analysis.md) | 基本面分析：财务数据获取、多维度评分、估值评级 |
| `sentiment.py` | [sentiment.md](./sentiment.md) | 新闻情感分析：基于Ollama LLM的逐条新闻情感评分 |
| `market_sentiment.py` | [market_sentiment.md](./market_sentiment.md) | 市场情绪指标：Fear & Greed Index、VIX恐慌指数 |
| `black_swan_detector.py` | [black_swan_detector.md](./black_swan_detector.md) | 黑天鹅探测器：世界新闻风险扫描、尾部风险预警 |

### ML 模型层

| 模块 | 文档 | 说明 |
|------|------|------|
| `features.py` | [features.md](./features.md) | 特征工程：55+维特征矩阵（收益/动量/波动/均线/量/形态/基本面/日历/A股特色） |
| `model_xgboost.py` | [model_xgboost.md](./model_xgboost.md) | XGBoost三分类模型：涨/平/跌方向预测，Walk-Forward验证 |
| `model_price_predictor.py` | [model_price_predictor.md](./model_price_predictor.md) | 价格回归模型：次日收盘/最高/最低价预测，涨跌停限幅 |
| `model_timing.py` | [model_timing.md](./model_timing.md) | 择时模型：双分类器（买入信号/退出信号），T+1适配 |
| `prediction_tracker.py` | [prediction_tracker.md](./prediction_tracker.md) | 预测追踪器：预测日志、回填验证、MAPE统计、模型健康度 |
| `backtest_engine.py` | [backtest_engine.md](./backtest_engine.md) | 回测引擎：A股T+1、佣金印花税滑点、涨跌停处理 |

### 扫描与综合层

| 模块 | 文档 | 说明 |
|------|------|------|
| `scanner.py` | [scanner.md](./scanner.md) | 三层AI选股扫描器：快筛→深度分析→LLM评分（Ollama+DeepSeek） |
| `long_term_scanner.py` | [long_term_scanner.md](./long_term_scanner.md) | 长线主题扫描器：新闻主题提取、贵金属分析、上涨空间评估 |
| `llm_reasoning.py` | [llm_reasoning.md](./llm_reasoning.md) | LLM综合推理：多源融合（TA+FA+情绪+A股数据+ML）生成分析报告 |

### 输出与报告层

| 模块 | 文档 | 说明 |
|------|------|------|
| `report_technical.py` | [report_technical.md](./report_technical.md) | 技术分析中文报告生成 |
| `stock_pdf.py` | [stock_pdf.md](./stock_pdf.md) | PDF报告生成：6种报告类型，ReportLab渲染 |

---

## 模块依赖关系总览

```
config.py ─────────────────────────────────────────────── 所有模块的基础
  │
  ├── fetch_market_data.py ──── watchlist.py
  │
  ├── technical_analysis.py ─── report_technical.py
  │     │                       features.py ─── model_xgboost.py
  │     │                         │             model_price_predictor.py
  │     │                         │             model_timing.py ── backtest_engine.py
  │     │                         │
  │     ├── fundamental_analysis.py
  │     │
  │     └── llm_reasoning.py ─── sentiment.py
  │                               market_sentiment.py
  │                               china_market_data.py
  │
  ├── hot_sectors.py
  │
  ├── black_swan_detector.py
  │
  ├── prediction_tracker.py
  │
  ├── scanner.py ──── (聚合: TA + FA + 资金流 + 热门板块 + ML + LLM)
  │
  ├── long_term_scanner.py ──── (聚合: 新闻信号 + 贵金属 + 主题 + 黑天鹅)
  │
  └── stock_pdf.py ──── (输出: 将扫描/分析结果渲染为PDF)
```

---

## 如何使用这些文档

1. **学习系统架构**: 从 [config.md](./config.md) 开始了解基础配置，然后按层级阅读
2. **理解金融理论**: 每个文档的第2节包含该模块涉及的金融理论，适合投资知识学习
3. **调整参数**: 每个文档的第5节列出所有可调参数及其理论依据
4. **排查问题**: 第7节记录了已知限制，便于定位问题根因
5. **扩展开发**: 依赖关系图帮助理解模块间的数据流向

---

## 相关文档

- [`docs/implementation/stock/`](../implementation/stock/) — 按功能分组的实现文档（英文）
- [`docs/learning/stock/`](../learning/stock/) — 股票知识学习指南（中文）
- [`docs/plans/archive/2026-04-12-stock-prediction.md`](../plans/archive/2026-04-12-stock-prediction.md) — 原始实现计划（已完成）

---

## 三套文档导航地图 (Cross-Reference Doc Map)

三套 stock 文档服务不同用途，以下表格帮助定位：

| Python 模块 | 本目录 (CN 详解) | `implementation/stock/` (EN 架构) | `learning/stock/` (教程) |
|-------------|------------------|-----------------------------------|--------------------------|
| `config.py` | [config.md](./config.md) | [config-impl.md](../implementation/stock/config-impl.md) | — |
| `fetch_market_data.py` | [fetch_market_data.md](./fetch_market_data.md) | [data-layer-impl.md](../implementation/stock/data-layer-impl.md) | — |
| `china_market_data.py` | [china_market_data.md](./china_market_data.md) | [china-market-impl.md](../implementation/stock/china-market-impl.md) | [ch10](../learning/stock/ch10-astock-deep-dive.md) |
| `watchlist.py` | [watchlist.md](./watchlist.md) | [data-layer-impl.md](../implementation/stock/data-layer-impl.md) | [ch8](../learning/stock/ch8-jarvis-workflow.md) |
| `hot_sectors.py` | [hot_sectors.md](./hot_sectors.md) | [scanner-impl.md](../implementation/stock/scanner-impl.md) | — |
| `technical_analysis.py` | [technical_analysis.md](./technical_analysis.md) | [analysis-engines-impl.md](../implementation/stock/analysis-engines-impl.md) | [ch4](../learning/stock/ch4-technical-analysis.md) |
| `fundamental_analysis.py` | [fundamental_analysis.md](./fundamental_analysis.md) | [analysis-engines-impl.md](../implementation/stock/analysis-engines-impl.md) | [ch2](../learning/stock/ch2-financial-statements.md), [ch3](../learning/stock/ch3-valuation-methods.md) |
| `sentiment.py` | [sentiment.md](./sentiment.md) | [analysis-engines-impl.md](../implementation/stock/analysis-engines-impl.md) | — |
| `market_sentiment.py` | [market_sentiment.md](./market_sentiment.md) | [market-signals-impl.md](../implementation/stock/market-signals-impl.md) | — |
| `black_swan_detector.py` | [black_swan_detector.md](./black_swan_detector.md) | [market-signals-impl.md](../implementation/stock/market-signals-impl.md) | — |
| `features.py` | [features.md](./features.md) | [ml-pipeline-impl.md](../implementation/stock/ml-pipeline-impl.md) | [ch7](../learning/stock/ch7-quantitative-methods.md) |
| `model_xgboost.py` | [model_xgboost.md](./model_xgboost.md) | [ml-pipeline-impl.md](../implementation/stock/ml-pipeline-impl.md) | [ch7](../learning/stock/ch7-quantitative-methods.md) |
| `model_price_predictor.py` | [model_price_predictor.md](./model_price_predictor.md) | [ml-pipeline-impl.md](../implementation/stock/ml-pipeline-impl.md) | — |
| `model_timing.py` | [model_timing.md](./model_timing.md) | [china-market-impl.md](../implementation/stock/china-market-impl.md) | — |
| `prediction_tracker.py` | [prediction_tracker.md](./prediction_tracker.md) | [ml-pipeline-impl.md](../implementation/stock/ml-pipeline-impl.md) | — |
| `backtest_engine.py` | [backtest_engine.md](./backtest_engine.md) | [china-market-impl.md](../implementation/stock/china-market-impl.md) | — |
| `scanner.py` | [scanner.md](./scanner.md) | [scanner-impl.md](../implementation/stock/scanner-impl.md) | [ch8](../learning/stock/ch8-jarvis-workflow.md) |
| `long_term_scanner.py` | [long_term_scanner.md](./long_term_scanner.md) | [scanner-impl.md](../implementation/stock/scanner-impl.md) | — |
| `llm_reasoning.py` | [llm_reasoning.md](./llm_reasoning.md) | [llm-synthesis-impl.md](../implementation/stock/llm-synthesis-impl.md) | — |
| `report_technical.py` | [report_technical.md](./report_technical.md) | [analysis-engines-impl.md](../implementation/stock/analysis-engines-impl.md) | — |
| `stock_pdf.py` | [stock_pdf.md](./stock_pdf.md) | [scanner-impl.md](../implementation/stock/scanner-impl.md) | — |

**用途区分**:
- **本目录** (`stock-modules/`): 每模块深度解析 — 金融理论 + 技术实现 + 参数调优（中文）
- **`implementation/stock/`**: 按功能分组的架构文档 — 数据流、设计决策、API 接口（英文）
- **`learning/stock/`**: 教程 — 从零学投资知识，结合 Jarvis 实践（中文）
