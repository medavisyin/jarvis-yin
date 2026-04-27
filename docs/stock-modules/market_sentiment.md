# market_sentiment — 详细功能文档

**文件路径**: `scripts/stock/market_sentiment.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：拉取并汇总**海外市场情绪代理指标**——主要为 **VIX（CBOE 波动率指数）** 与 **恐惧与贪婪类指数**——合并为统一结构，供特征工程、UI 展示与极端情绪提示。
- **在系统中的角色**：提供全市场「情绪/风险」横截面信息；与 A 股本地数据解耦，偏**全球风险偏好**与**跨市场联动**参考。
- **上下游关系**：

```
  alternative.me API  ----->  fetch_fear_greed()
  CNN dataviz API     ----->  (备选)
  Yahoo Finance chart API ->  fetch_vix() / _parse_yahoo_vix()
            |
            v
     fetch_all_sentiment() --> _classify_mood() --> combined.json
            |
            v
     load_cached_sentiment() 读取 combined
```

- **依赖**：`requests`、`config`（`STOCK_DATA_DIR` 在模块中导入但本文件主要用 `STOCK_REPORTS_ROOT` 下子目录）。

---

## 2. 金融理论基础

- **VIX 与波动率风险溢价**：VIX 由标普 500 期权反推隐含波动率，常被称为「恐慌指数」。经验上 VIX 上升与风险资产承压、尾部风险上升相关；长期均值回复特性明显。
- **恐惧与贪婪指数（Fear & Greed）**：CNN 等机构将多因子（动量、期权、安全资产需求、垃圾债利差等）合成 0–100 分数；**极端读数**在行为金融学中与羊群效应、过度反应相联系。实践中用作**逆向指标**时需谨慎：趋势市中「贪婪」可长期持续。
- **为什么需要本模块**：量化模型中常加入「外部风险环境」以刻画 A 股与全球流动性的联动（外资、风险情绪溢出）。
- **A 股适用性**：A 股与美股节奏不同，VIX/加密情绪指数**非 A 股直接指标**，更宜作**辅助特征**；若用于交易决策应结合北向、汇率等本土因子。代码中已注明 alternative.me 为**加密市场衍生**的 Fear&Greed，与股市指数存在差异。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`fetch_fear_greed() -> dict`**  
  - `value`：0–100 整数或 `None`  
  - `label`：分类文字  
  - `timestamp`：源站时间或本地 ISO 时间  
  - `source`：`"alternative.me"` 或 `"CNN"`

- **`fetch_vix() -> dict`**  
  - `value`：VIX 水平（float）  
  - `change_pct`：相对前收盘变动（%）  
  - `timestamp`：ISO 字符串  
  - `source`：`"Yahoo Finance"`

- **`fetch_all_sentiment() -> dict`**  
  - `fear_greed`、`vix`、`fetched_at`  
  - `market_mood`：`_classify_mood` 结果

- **`_classify_mood` 返回**  
  - `risk_level`：`high_fear` / `fear` / `normal` / `greed` / `high_greed`  
  - `signals`：中文描述列表  
  - `recommendation`：固定短语建议（非真实投资建议，仅为模板输出）

### 3.2 关键函数

| 函数 | 作用 |
|------|------|
| `fetch_fear_greed` | 先请求 `https://api.alternative.me/fng/?limit=1&format=json`；失败再请求 CNN `production.dataviz.cnn.io/index/fearandgreed/graphdata` |
| `fetch_vix` | 依次尝试 Yahoo chart URL（query2 / query1），解析 `chart.result[0].meta` 的 `regularMarketPrice` 与 `previousClose` |
| `_parse_yahoo_vix` | 从 Yahoo JSON 提取现价、涨跌幅% |
| `fetch_all_sentiment` | 组合二者并写 `combined` 缓存 |
| `_classify_mood` | 基于 FG 分档 + VIX 分档（≥30 高波动，≥20 偏高）综合 `risk_level` |
| `_mood_recommendation` | 按 `risk_level` 映射中文短句 |
| `load_cached_sentiment` | 读 `market_sentiment/combined.json` |
| `_save_cache` | 写入 `STOCK_REPORTS_ROOT/market_sentiment/{name}.json` |

### 3.3 算法与计算逻辑

- **Fear & Greed 分档**（`fg_value`）：  
  - ≤20 → `high_fear`；≤40 → `fear`；≥80 → `high_greed`；≥60 → `greed`；否则中性。
- **VIX 调整**：若 VIX≥30 且当前风险为 normal/greed/high_greed，**上调为** `high_fear`（强调波动冲击）。
- **涨跌幅**：\((P_t - P_{prev}) / P_{prev} \times 100\%\)

---

## 4. 外部依赖与数据源

- **库**：`requests`。
- **API**：  
  - alternative.me FNG  
  - CNN fearandgreed JSON  
  - Yahoo Finance v8 chart（`^VIX`）
- **代理**：环境变量 `STOCK_PROXY`（与代码中 `STOCK_DATA_DIR` 同模块导入，VIX/FG 使用 `os.environ.get("STOCK_PROXY")`）。
- **缓存**：`{STOCK_REPORTS_ROOT}/market_sentiment/*.json`（`fear_greed.json`、`vix.json`、`combined.json`），**每次拉取会覆盖写入**（非按 TTL 仅读缓存逻辑；读缓存仅在 `load_cached_sentiment` 读 combined）。

---

## 5. 配置项与可调参数

- **超时**：HTTP `timeout=10`（Fear&Greed 与 VIX 请求）。
- **阈值**：VIX 20/30、FG 20/40/60/80 均硬编码在 `_classify_mood`；调整即改变风险标签分布。
- **目录**：`STOCK_REPORTS_ROOT` 决定缓存落盘位置。

---

## 6. 使用示例与工作流

```python
from market_sentiment import fetch_all_sentiment, load_cached_sentiment

full = fetch_all_sentiment()   # 联网拉取并写缓存
cached = load_cached_sentiment()  # 仅读本地 combined
```

- 与 `features.py` 的 `_add_market_mood_features`：后者实际使用**融资融券与北向**（`china_market_data`），**不直接**引用本文件；本模块为并行情绪信息源。

---

## 7. 已知限制与改进方向

- **Fear & Greed 源 1 为加密市场情绪**，与 A 股或美股的 CNN 指含义不同，跨表比较需注明。
- CNN 与 Yahoo 接口可能变更，需监控解析失败率。
- `recommendation` 为固定模板，**非动态风控模型输出**。
