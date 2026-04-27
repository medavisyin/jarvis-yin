# watchlist — 详细功能文档

**文件路径**: `scripts/stock/watchlist.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：维护用户**自选股/关注列表**的持久化（JSON 文件），支持**增删改查**、**按关键字搜索**全市场、**从本地缓存补全**名称与行业、**批量拉取**行情与基本面数据，并输出**带价列表**供日常浏览。
- **系统角色**：位于**投研工作流的人机边界**——将「关注集合」与 `fetch_market_data` 的**数据子目录**衔接；是**轻量投组/观察名单**的载体（本模块的 `PORTFOLIO_FILE` 在 `config` 中定义，**本文件不直接操作** `portfolio.json`）。
- **上下游关系**：

```
[config: WATCHLIST_FILE, STOCK_DATA_DIR]
         │
         ▼
[watchlist.py] 读写 watchlist.json
         │
    ┌────┴────┬──────────────────┐
    ▼         ▼                  ▼
[本地 realtime.json   [本地 profile.json   [fetch_market_data
 profile.json]         用于展示]            / akshare 搜索/补全]
    │
    └────► fetch_market_data.update_stock_data (refresh_all_data)
```

---

## 2. 金融理论基础

- **自选股/观察名单**：在行为金融学中，投资者会**有限关注**部分标的；自选股是**信息聚焦与再平衡**的界面。A 股标的众多，**名单管理**是后续技术分析、新闻与基本面批处理的**一阶输入**。
- **行业与名称补全**：用于**行业中性化**、板块对比与展示一致性；`sector` 字段依赖数据源，可能与申万/中信行业**不完全一致**。
- **带价列表**：`latest_price`、`change_pct` 等来自**本地最近一次拉取**，非交易所实时保证；适合**日频复盘**，不适合**高频交易**时延要求。

---

## 3. 技术实现详解

### 3.1 核心数据结构

**`watchlist.json`（逻辑结构，由代码保证键存在）**：

```json
{
  "stocks": [
    {
      "symbol": "600519",
      "name": "贵州茅台",
      "sector": "白酒",
      "added": "2026-04-27",
      "notes": ""
    }
  ],
  "sectors": [],
  "updated_at": "2026-04-27T12:00:00.000000"
}
```

- `sectors` 在代码中 **setdefault** 但**本模块未提供行业维度的增删 API**（预留给未来或外部编辑）。
- `stocks` 中每条**必须**含 `symbol`；`add_stock` 写入的字段为：`symbol, name, sector, added, notes`。

**`get_watchlist_with_prices` 在每条上扩展的键**（若本地文件存在且解析成功）：

- `latest_price`, `change_pct`, `market_cap`, `pe`, `pb`, `volume`, `fetched_at` —— 从 `STOCK_DATA_DIR/{symbol}/realtime.json` 读取
- 若 `sector`/`name` 仍空，会尝试用 `profile.json` 与再次读 `realtime` 补全

> **注意**：`fetch_market_data._fetch_realtime_sina` 产出的 `realtime` **未必包含** `总市值、市盈率-动态、市净率`（视字段与数据源路径）；`get_watchlist_with_prices` 仍会 `get` 这些键，可能为 `None`。**Akshare 全市场**路径返回时字段更全。属**数据源与路径差异**，非 watchlist 逻辑错误。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `_load_raw() -> dict` | 读 `WATCHLIST_FILE`；非 dict 或 JSON 错则回退 `_DEFAULT_WATCHLIST` |
| `_save(data)` | 写回文件前设置 `updated_at=now` |
| `list_stocks() -> list[dict]` | 返回 `stocks` 列表 |
| `add_stock(symbol, name="", sector="", notes="")` | 去重后追加；`name/sector` 空则 `_resolve_stock_info` |
| `_resolve_stock_info(symbol) -> (name, sector)` | 顺序：`realtime.json` 名称 → `profile.json` → `ak.stock_zh_a_spot_em` 取名称 → `fetch_company_profile` 取行业 |
| `remove_stock(symbol) -> bool` | 有删除则 `True` |
| `get_stock(symbol) -> dict \| None` | 线性查找 |
| `update_stock_notes(symbol, notes) -> bool` | 更新备注 |
| `get_watchlist_with_prices() -> list[dict]` | 见 3.1 |
| `refresh_all_data() -> list[dict]` | 对每支 `update_stock_data`，再 `_backfill_watchlist_info` |
| `_backfill_watchlist_info()` | 若 `name` 或 `sector` 缺失则 `_resolve_stock_info` 后写回 |
| `search_stock(keyword) -> list[dict]` | `ak.stock_zh_a_spot_em()`，代码/名称 `str.contains`，最多 20 条，返回 `symbol, name, price, change_pct, pe, market_cap` |

### 3.3 算法与计算逻辑

- **去重**：`add_stock` 用 `existing = {s["symbol"] for s in data["stocks"]}`。
- **搜索**：pandas 布尔 mask；无模糊大小写参数（依赖 pandas `contains` 默认行为）。
- **无独立评分或优化算法**；**刷新**是顺序循环调用 `update_stock_data`，**无并发**与**无速率限制**。

---

## 4. 外部依赖与数据源

- **标准库**：`json`, `os`, `logging`, `datetime`。
- **配置**：`WATCHLIST_FILE`, `STOCK_DATA_DIR`。
- **条件依赖**：`akshare`（搜索、补全名称）；`from fetch_market_data import update_stock_data, fetch_company_profile`（刷新与行业解析）。
- **缓存**：`watchlist.json` 为**真源**；价格与行业**以数据目录中的 JSON 为主**，不在 watchlist 内重复存行情。

---

## 5. 配置项与可调参数

- **`WATCHLIST_FILE`**：由 `config` 的 `STOCK_REPORTS_ROOT` 决定，默认在 `C:/reports/stock/watchlist.json`（可改环境变量）。
- **`search_stock` 的条数上限**：硬编码为 **20**。
- **CLI 子命令**（`__main__`）：`list` | `add` | `remove` | `refresh` | `prices` —— 无额外配置文件。

**调优建议**：全市场 `ak` 在冷启动时较慢，**搜索/补全**可改为本地股票列表缓存后检索（需额外开发）。

---

## 6. 使用示例与工作流

```python
from watchlist import add_stock, list_stocks, refresh_all_data, get_watchlist_with_prices

add_stock("600519", "贵州茅台", "白酒")
# 或只给代码，由缓存/网络补全
add_stock("000001")

for row in get_watchlist_with_prices():
    print(row["symbol"], row.get("latest_price"), row.get("change_pct"))

# 与 fetch 的协作：一键更新列表内所有标的
refresh_all_data()
```

---

## 7. 已知限制与改进方向

- **`sectors` 列表**在 schema 中预留但**无 API** 维护，易造成数据与 UI 期待不一致。
- `refresh_all_data` **串行**、无失败退避，列表过长时**总耗时长**。
- `get_watchlist_with_prices` 依赖 `realtime.json` 字段完整性，新浪单股简版实时可能缺 PE/PB/市值，展示上可能大量 `None`。
- 无多用户/权限/冲突合并；单文件**不适合团队并发编辑**。

---
