# 统一扫描编排器 (unified_scanner) — 详细功能文档

**文件路径**: `scripts/stock/unified_scanner.py`
**最后更新**: 2026-07-02

---

## 1. 模块概述

- **核心职责**: 把**左侧短期扫描**（`scanner`）与**右侧交易扫描**（`right_side_scanner`）编排成**一次操作**——共享一次全市场行情抓取、共享 per-stock enrichment 缓存（资金流向 + OHLCV 每只只抓一次），分别用两套逻辑筛选与判断，输出**两份独立报告**。
- **设计动机**: 两套扫描原本各自独立抓行情、独立 enrich，存在大量重复网络开销。统一后：行情抓 1 次、每只股票的资金/K 线抓 1 次，两套策略复用，省时省钱，同时保持两份报告独立性。
- **系统角色**: Stock 子系统的**统一推荐入口**；不自己出报告，而是调用 `scanner` 与 `right_side_scanner` 各自出报告（各自目录、各自 RAG 索引）。前端 `unifiedModal` 双栏展示。

```
[一次共享行情抓取] ──┬──→ 左侧 scanner.start_scan   → 左侧短期报告
                      └──→ 右侧 right_side.start     → 右侧交易报告
   (scan_cache 共享 fund_flow + OHLCV，命中即复用)
```

---

## 2. 关键设计点

### 2.1 状态持久化到 `sys`（关键）

历史背景：`_with_stock_imports` 装饰器**曾经**在每次请求时 `sys.modules.pop` 并重新导入所有 stock 模块，模块级全局变量会被重置；若状态放在模块级，后台扫描线程跑在"孤儿"模块实例里更新自己的状态，而 status 接口读到新实例的初始 `idle` → 前端永远卡在"扫描进行中"。

**2026-07-02 起**，`_with_stock_imports` 改为**非破坏式**——只切换 `sys.modules['config']`，不再 pop stock 子模块（见 `api-routes-impl.md`）。但**扫描线程自身的 `_safe_import` / `_ensure_stock_config` 仍会在扫描过程中 pop 并重导入 `scanner`/`right_side_scanner` 等模块**，所以模块级全局依然不可靠。因此运行期可变状态**仍必须**挂 `sys`：

**解法**: 所有运行期可变状态挂 `sys`：
- `sys._unified_status`（dict）
- `sys._unified_thread`（Thread）
- `sys._unified_stop`（Event）
- `sys._unified_lock`（Lock）

模块级名字每次重导入只 re-bind 到同一 `sys` 对象（`_init_sys_state()`）。`right_side_scanner` 用同样手法（`sys._rs_*`）。`scanner` 则用进度文件落盘。

> **教训（通用规则）**：任何会被 `_safe_import` 重新导入的扫描器模块（扫描线程运行期间），运行期可变状态必须挂 `sys` 或落盘，不能放模块级全局。

### 2.2 后台线程内的 stock config 强制重载（关键）

统一扫描的后台线程在 `_with_stock_imports` 装饰器 `finally` 退出后才运行，此时 `sys.modules['config']` 已被恢复成 RAG config（无 `STOCK_DATA_DIR` 等）。若直接 `import right_side_scanner`，其顶层 `from config import STOCK_DATA_DIR` 会 `ImportError`。

> 注：2026-07-02 起 `_with_stock_imports` 不再清空 stock 模块缓存（只切 config），但 `finally` 仍会把 `sys.modules['config']` 改回 RAG，所以下方自修复机制依旧必要。

**解法**: `_ensure_stock_config()` 在线程内用 `importlib.util.spec_from_file_location` 强制加载 stock config 到 `sys.modules['config']`，并 pop 所有 stale stock 模块。在三个时机调用：
1. `_run_unified_inner` 线程开头
2. 启动左侧扫描前
3. **启动右侧扫描前**（关键：右侧子线程不自修复 config，且左阶段的状态轮询可能把 config 翻回 RAG）

`scanner._run_scan_inner` 自带同样机制；`right_side_scanner` 没有，故统一编排器必须替它保证 config 正确。

> **教训（通用规则）**：后台线程若 import 依赖 stock config 的模块，必须在线程内自行强制重载 stock config，不能依赖请求装饰器留下的 config 状态。

### 2.3 共享 enrichment 缓存

通过 `scan_cache` 模块（见 `scan_cache.md`）：左侧 Layer2 enrich 某只股票时把资金流向、OHLCV 写入缓存；右侧 Layer2 命中同一只股票时直接复用，未命中才抓。`_run_unified_inner` 开头 `scan_cache.reset()` 清空上次缓存。

### 2.4 共享行情 DataFrame 透传（2026-07-02 改）

统一编排器抓一次全市场行情 `df`，**直接作为参数**透传给两侧扫描器：`scanner.start_scan(use_deepseek, market_df=df)` 与 `right_side_scanner.start_right_side_scan(use_deepseek, market_df=df)`；两侧 Layer1 见到非空 `market_df` 即跳过自己的网络抓取直接用。

> **为什么不用模块级全局注入**：旧实现用 `set_shared_market_df(df)` 写模块级全局，但 `_safe_import` 在右扫启动前会重新 pop+导入 `right_side_scanner`，模块级 `_shared_market_df` 被重置回 `None`，导致右扫线程读到 `None` 又去跑一次没有 timeout 的 `ak.stock_zh_a_spot_em()`，表现为"卡在 右侧 Layer 1"。改成参数透传后，`df` 由编排线程的局部变量持有，重导入冲不掉。`set_shared_market_df`/`clear_shared_market_df` 函数仍保留供独立启动场景兜底，但统一扫描路径不再依赖它们，也不再需要结束时的 `_cleanup_shared_df()`。

---

## 3. 核心数据结构与函数

### 3.1 统一状态 (`sys._unified_status`)

| 字段 | 说明 |
|------|------|
| `status` | `idle`/`running`/`done`/`error`/`stopped` |
| `phase` | `none`/`market`/`left`/`right`/`done`/`error` |
| `step` | 当前子扫描器返回的步骤描述 |
| `progress` | 0~100 统一进度 |
| `use_deepseek` | 是否启用 DeepSeek |
| `left` | 左侧子扫描器状态快照 |
| `right` | 右侧子扫描器状态快照 |
| `started_at` | ISO 时间戳 |
| `error` | 错误信息 |

### 3.2 关键函数

| 函数 | 作用 |
|------|------|
| `start_unified_scan(use_deepseek)` | 启动编排线程，状态挂 `sys`。 |
| `get_unified_scan_status()` | 返回 `sys._unified_status` 副本 + `running` 标记。 |
| `stop_unified_scan()` | 置停止事件 + 调用两侧 `stop_*`。 |
| `get_latest_unified_result()` | 聚合当日左侧 + 右侧结果 JSON。 |
| `_run_unified_inner(use_deepseek)` | 后台编排主逻辑。 |
| `_ensure_stock_config()` | 强制重载 stock config + 清 stale 模块。 |
| `_fetch_shared_market_df()` | 共享行情抓取（akshare → 东财直连 → 新浪三重兜底）。 |
| `_wait_for(status_fn, done_keys, phase_label, base, span)` | 轮询子扫描器状态，映射到统一进度区间。 |

### 3.3 进度映射

| 阶段 | 进度区间 |
|------|---------|
| 共享行情抓取 | 5~12% |
| 左侧扫描 | 12~57% |
| 右侧扫描 | 58~98% |
| 完成 | 100% |

---

## 4. API 路由（`scripts/rag/routes/stock.py`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/stock/unified_scan/start` | 启动统一扫描，body `{use_deepseek}` |
| GET | `/api/stock/unified_scan/status` | 统一进度（phase + 子状态） |
| POST | `/api/stock/unified_scan/stop` | 停止 |
| GET | `/api/stock/unified_scan/result` | 当日左+右结果聚合 |

`unified_scanner` 与 `scan_cache` 仍在 `_STOCK_MODULES` 列表中，但自 2026-07-02 起 `_with_stock_imports` **只切换 `sys.modules['config']`，不再 pop/重导入这些 stock 子模块**（避免与扫描线程的 `_safe_import` 在 `sys.modules` 上竞争，导致 status 接口在扫描期间长时间挂起）。

---

## 5. 使用示例

```python
from unified_scanner import start_unified_scan, get_unified_scan_status
start_unified_scan(use_deepseek=True)
# 轮询 get_unified_scan_status() 至 status == "done"
# get_latest_unified_result() 取 {"date", "left": {...}, "right": {...}}
```

前端 `unifiedModal`：一个开始/停止 + 一个进度条 + 左右两栏结果区。`startUnifiedScan` 点击即启动轮询（避免冷启动 import 慢时 UI 卡住）。

---

## 6. 已知限制与改进方向

- 两侧**顺序执行**（左完再右），未并发——避免 sys.modules config 竞争与重复 DeepSeek 并发。可探索并发执行以进一步提速。
- 共享行情抓取失败时整体失败（两侧都不跑）；可降级为各自独立抓取。
- 改进: 统一进度估算可基于子扫描器真实候选数加权。

---

## 7. 变更记录

- **2026-07-02**：
  - 共享行情改为参数透传 `start_scan(market_df=df)` / `start_right_side_scan(market_df=df)`，替代模块级全局注入（修"右扫卡在 Layer 1"——`_safe_import` 重导入会清掉模块级 `_shared_market_df`）。移除 `_cleanup_shared_df()`。
  - `_with_stock_imports` 改为非破坏式（只切 config，不再 pop stock 子模块），消除扫描期间 status 接口与扫描线程在 `sys.modules` 上的竞争/挂起。
