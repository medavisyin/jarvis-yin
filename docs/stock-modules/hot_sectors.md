# hot_sectors — 详细功能文档

**文件路径**: `scripts/stock/hot_sectors.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：从 A 股市场拉取「热门概念/板块」当日表现，并解析各板块成分股代码，供选股、打标或展示使用；结果按日 JSON 缓存，减少重复请求。
- **在系统中的角色**：位于数据获取层，与 `china_market_data.get_hot_sectors()`（按**行业/概念资金流排名**）数据来源与语义不同；本模块侧重**东方财富概念板块**涨跌幅排序 + 成分股列表。
- **上下游关系（文字描述）**：

```
  [akshare EM 概念 API]     [东方财富 push2 HTTP API]
           |                           |
           v                           v
    _fetch_sectors_akshare()    _fetch_sectors_eastmoney()
           \                         /
            v                       v
              fetch_hot_sectors()  ---->  hot_sectors_YYYY-MM-DD.json (STOCK_CACHE_DIR)
                     |
                     v
              get_hot_stock_set()  ---->  set(成分股代码 + 领涨股代码)
                     |
                     v
        下游: 扫描器/特征/报表（若项目中有引用）
```

- **依赖**：`akshare`、`requests`、`config`（`STOCK_CACHE_DIR`、`STOCK_PROXY`）。

---

## 2. 金融理论基础

- **板块轮动（Sector Rotation）**：经典资产配置思想认为，不同经济阶段资金会流向不同行业（如防御/周期/成长）。A 股因政策与主题炒作更突出，**概念板块**往往短期集中资金，涨跌幅榜可反映当下「资金在炒什么」。
- **投资分析意义**：识别热点板块有助于：主题跟踪、避免与大盘完全脱钩的选股噪音、理解领涨股与扩散范围（成分股列表）。
- **实践背景**：概念指数、行业涨幅排名是券商与行情软件常见功能；本模块将其实例化为可编程数据。
- **A 股特殊性**：涨跌停、T+1、题材驱动强，「概念」比部分成熟市场更常用；需注意热点切换快、同源数据延迟与幸存者偏差。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`fetch_hot_sectors() -> list[dict]`** 每个元素示例：
  - `name`：板块名称（字符串）
  - `change_pct`：涨跌幅（float，%）
  - `leader`：领涨股票名称
  - `leader_symbol`：领涨股票代码
  - `stocks`：成分股代码列表（akshare 路径下最多取 30 只；东财备用路径常为空列表）

### 3.2 关键函数

| 函数 | 说明 |
|------|------|
| `_cache_path()` | 当日缓存文件路径：`STOCK_CACHE_DIR/hot_sectors_YYYY-MM-DD.json` |
| `_retry(fn, *args, retries=2, **kwargs)` | 失败重试，间隔 `1*(attempt+1)` 秒 |
| `fetch_hot_sectors()` | 先读缓存；失败则 akshare → 东财；成功则写缓存 |
| `_fetch_sectors_akshare()` | `ak.stock_board_concept_name_em` 全表按「涨跌幅」降序，取前 20；对每板块 `ak.stock_board_concept_cons_em(symbol=name)` 取「代码」列前 30；板块间 `sleep(0.3)` |
| `_fetch_sectors_eastmoney()` | GET `push2.eastmoney.com/api/qt/clist/get`，`fs=m:90+t:3`（概念板块），解析 `f14/f3/f128/f140/f141` 等字段；**不拉成分股** |
| `get_hot_stock_set()` | 汇总所有 `stocks` 与 `leader_symbol` 为 `set` |

### 3.3 算法与计算逻辑

- 主策略：**涨幅 Top20 概念**（ak 路径下），非复杂打分模型。
- 东财 API 的 `po=1`、`fid=f3` 与字段映射依赖东方财富当前接口约定，变更可能导致解析失效。

---

## 4. 外部依赖与数据源

- **库**：`akshare`、`requests`。
- **网络**：东财 `Referer: https://data.eastmoney.com/`；可选 `STOCK_PROXY` 代理。
- **缓存策略**：**按日一个 JSON 文件**；命中则直接返回。无显式 `max_age` 小时数——同日多次运行复用同一份缓存。

---

## 5. 配置项与可调参数

| 参数/常量 | 位置 | 说明 |
|-----------|------|------|
| `STOCK_CACHE_DIR` | `config` | 缓存根目录 |
| `STOCK_PROXY` | `config` | 若设置，则 `requests` 使用 `http(s)` 代理 |
| Top 20 / sleep 0.3 | 代码内 | 可改排名数量与请求间隔（防反爬） |
| `_retry` retries=2 | `_retry` | 可调重试次数 |

---

## 6. 使用示例与工作流

```python
from hot_sectors import fetch_hot_sectors, get_hot_stock_set

sectors = fetch_hot_sectors()   # 列表 of dict
hot_syms = get_hot_stock_set()  # 今日热门相关代码集合
```

- 与 `china_market_data`：需要「行业资金流入 TopN 板块名」时用后者 `get_hot_sectors`；需要「概念板块 + 成分股」时用本模块。

---

## 7. 已知限制与改进方向

- 东财备用路径 **无成分股**（`stocks` 空），与主路径行为不一致。
- 缓存**跨日不自动刷新**需依赖新自然日新文件名；盘中更新需手动删缓存或改逻辑。
- 概念名称与行业分类口径与资金流板块可能不一致，合并分析时需对齐语义。
