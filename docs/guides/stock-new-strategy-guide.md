# 新增股票策略指南 — 插件接口规范与模板

**用途**: 指导未来新增股票推荐策略（如"事件驱动""打板""定投择时"等），并把它接入统一扫描器 `unified_scanner`，与左侧/右侧并存输出独立报告。
**最后更新**: 2026-07-01

> 本文是**接口规范 + 模板**，不要求重构现有代码。现有 `scanner.py` / `right_side_scanner.py` 已自然遵循本规范，可直接作为参考实现。

---

## 1. 设计原则

1. **每套策略 = 一个独立模块**：`scripts/stock/<strategy>_scanner.py`，自带三层漏斗、自带状态、自带报告落盘。
2. **统一对外契约**：所有策略模块暴露同一组函数签名（见 §2），让 `unified_scanner` 能用同一套代码编排任意策略。
3. **共享不耦合**：策略可复用 `scan_cache`（enrichment 缓存）与共享行情 DataFrame，但筛选逻辑、判断逻辑、报告格式各自独立。
4. **状态挂 `sys`**：受 `_with_stock_imports` 装饰器影响的模块，运行期状态必须挂 `sys` 或落盘，不能放模块级全局（详见 `unified_scanner.md` §2.1）。
5. **后台线程内自管 config**：线程内 `import` 依赖 stock config 的模块前，必须自行 `_ensure_stock_config()`（详见 `unified_scanner.md` §2.2）。

---

## 2. 策略模块对外契约（必须实现）

每个策略模块 `<name>_scanner.py` 必须提供以下函数（签名固定）：

```python
# 1. 启动扫描（后台守护线程）
def start_<name>_scan(use_deepseek: bool = True) -> dict:
    """启动后台扫描线程；返回 {ok, message}。已运行则返回占用错误。"""

# 2. 停止扫描
def stop_<name>_scan() -> dict:
    """请求优雅停止；返回 {ok, message}。"""

# 3. 查询状态（前端轮询）
def get_<name>_scan_status() -> dict:
    """返回 {status, progress, step, started_at, elapsed_ms, error, results_count, ...}。
       status ∈ {idle, running, completed, failed, stopped}。"""

# 4. 取最新结果
def get_latest_<name>_result() -> dict | None: ...
def get_<name>_result_by_date(date: str) -> dict | None: ...
def list_<name>_scan_dates() -> list[str]: ...

# 5. 统一扫描器注入共享行情（可选但推荐）
def set_shared_market_df(df) -> None: ...   # 注入共享全市场 DataFrame
def clear_shared_market_df() -> None: ...    # 扫描结束清理
```

> 命名规则：把 `<name>` 换成策略名，如 `event_scanner` → `start_event_scan` / `get_event_scan_status`。统一扫描器通过名字约定调用。

### 2.1 状态字段最小集

`get_<name>_scan_status()` 返回的 dict 至少包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | str | `idle`/`running`/`completed`/`failed`/`stopped` |
| `progress` | int | 0~100 |
| `step` | str | 当前步骤中文描述（前端进度条下方显示） |
| `started_at` | str | ISO 时间戳 |
| `error` | str | 错误信息（无则空） |

### 2.2 结果 JSON 结构（建议）

```json
{
  "scan_type": "<name>",
  "date": "2026-07-01",
  "started_at": "...",
  "ended_at": "...",
  "picks": [ { /* 策略自定义字段 */ } ],
  "all_candidates_count": 123,
  "message": "..."
}
```

---

## 3. 模板骨架（复制即用）

新建 `scripts/stock/<name>_scanner.py`，按以下骨架填写。带 `# TODO` 的地方按策略填。

```python
"""<策略名>扫描器 — <一句话说明策略理念>"""
import sys, threading, time, json, importlib.util, os
from datetime import datetime

# --- sys 状态持久化（绕过 _with_stock_imports 重导入） ---
def _init_sys_state():
    if not hasattr(sys, "_<name>_status"):
        sys._<name>_status = {"status": "idle", "progress": 0, "step": "",
                              "started_at": "", "error": "", "results_count": 0}
    if not hasattr(sys, "_<name>_thread"):
        sys._<name>_thread = None
    if not hasattr(sys, "_<name>_stop"):
        sys._<name>_stop = threading.Event()
    if not hasattr(sys, "_<name>_lock"):
        sys._<name>_lock = threading.Lock()
_init_sys_state()

_SHARED_MARKET_DF = None

# --- 后台线程内强制重载 stock config（关键，勿删） ---
def _ensure_stock_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "config.py")
    spec = importlib.util.spec_from_file_location("config", cfg_path)
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    sys.modules["config"] = cfg
    for m in ["china_market_data", "fetch_market_data", "technical_analysis",
              "scan_cache", "scanner", "right_side_scanner"]:
        sys.modules.pop(m, None)

# --- 公共 API ---
def start_<name>_scan(use_deepseek: bool = True) -> dict:
    with sys._<name>_lock:
        if sys._<name>_thread and sys._<name>_thread.is_alive():
            return {"ok": False, "message": "已有扫描在运行"}
        sys._<name>_stop.clear()
        sys._<name>_status.update({"status": "running", "progress": 0,
                                   "step": "初始化", "started_at": datetime.now().isoformat(),
                                   "error": "", "results_count": 0})
        t = threading.Thread(target=_run_thread, args=(use_deepseek,), daemon=True)
        sys._<name>_thread = t
        t.start()
    return {"ok": True, "message": "扫描已启动"}

def stop_<name>_scan() -> dict:
    sys._<name>_stop.set()
    return {"ok": True, "message": "已请求停止"}

def get_<name>_scan_status() -> dict:
    running = sys._<name>_thread and sys._<name>_thread.is_alive()
    s = dict(sys._<name>_status)
    s["running"] = bool(running)
    return s

def set_shared_market_df(df): 
    global _SHARED_MARKET_DF; _SHARED_MARKET_DF = df
def clear_shared_market_df(): 
    global _SHARED_MARKET_DF; _SHARED_MARKET_DF = None

# --- 主逻辑 ---
def _run_thread(use_deepseek):
    try:
        _ensure_stock_config()
        # TODO: Layer1 / Layer2 / Layer3
        #   - Layer1 可用 _SHARED_MARKET_DF 跳过网络抓取
        #   - Layer2 enrich 命中 scan_cache 即复用（见 scan_cache.md）
        #   - 进度更新: sys._<name>_status.update({"progress": x, "step": "..."})
        #   - 停止检查: if sys._<name>_stop.is_set(): break
        picks = []
        _save_results(picks, ...)
        sys._<name>_status.update({"status": "completed", "progress": 100, "step": "完成"})
    except Exception as e:
        sys._<name>_status.update({"status": "failed", "error": str(e), "step": "错误"})

def _save_results(picks, ...): 
    # TODO: 写 JSON + Markdown 报告 + 可选 RAG 索引
    ...

def get_latest_<name>_result(): ...   # TODO
def get_<name>_result_by_date(date): ...  # TODO
def list_<name>_scan_dates(): ...  # TODO
```

---

## 4. 接入统一扫描器（`unified_scanner.py`）

新增策略后，在 `unified_scanner._run_unified_inner` 中按现有左右侧模式追加一段：

```python
# 1. ensure config
_ensure_stock_config()
import <name>_scanner as ns
ns.set_shared_market_df(shared_df)

# 2. 启动
ns.start_<name>_scan(use_deepseek=use_deepseek)

# 3. 轮询映射进度（复用 _wait_for）
_wait_for(ns.get_<name>_scan_status, ("completed","failed","stopped"),
          "<策略中文名>", base=<上阶段进度>, span=<区间>)

# 4. 取结果聚合
result = ns.get_latest_<name>_result()
sys._unified_status["<name>"] = result
```

并在 `sys._unified_status` 增加对应键、在 `_STOCK_MODULES`（`stock.py`）追加 `"<name>_scanner"`、在路由层可选新增独立 `/api/stock/<name>_scan/*` 接口（若想单独跑）。

---

## 5. 接入 API 路由（`scripts/rag/routes/stock.py`）

1. 把 `"<name>_scanner"` 加进 `_STOCK_MODULES` 列表（受 `_with_stock_imports` 管理）。
2. （可选）新增 4 个独立路由模仿 `unified_scan`：`/api/stock/<name>_scan/{start,status,stop,result}`。
3. 已有 `/api/stock/unified_scan/result` 会自动包含新策略（只要 `unified_scanner` 聚合时加了键）。

---

## 6. 接入前端（`index.html`）

- **统一入口**：`unifiedModal` 增加一栏结果区 `#uni<Name>Result`，`loadUnifiedResult` 调 `_build<Name>Html(picks)` 渲染。
- **独立入口（可选）**：工具栏加按钮 → 新 modal，复用 start/poll/stop/result 模式（参考左右侧实现）。

---

## 7. 添加策略检查清单

- [ ] 新建 `scripts/stock/<name>_scanner.py`，实现 §2 全部函数
- [ ] 状态挂 `sys`，线程内 `_ensure_stock_config()`
- [ ] Layer1 支持共享 `market_df` 注入；Layer2 用 `scan_cache` 复用
- [ ] 结果落盘到 `STOCK_REPORTS_ROOT/data/<name>_scan/` + 报告目录
- [ ] `unified_scanner._run_unified_inner` 追加编排段
- [ ] `stock.py` 的 `_STOCK_MODULES` 追加模块名
- [ ] （可选）新增独立 API 路由
- [ ] 前端 `unifiedModal` 加结果栏 + `_build<Name>Html`
- [ ] 新建 `docs/stock-modules/<name>_scanner.md`
- [ ] `py_compile` + 冒烟测试（启动→轮询→完成→取结果）
- [ ] 更新 `docs/guides/stock-strategy-guide.md`（小白向）与 `docs/guides/stock-usage-guide.md`

---

## 8. 策略命名与目录约定

| 项 | 约定 |
|----|------|
| 模块文件 | `scripts/stock/<name>_scanner.py` |
| 结果 JSON | `STOCK_REPORTS_ROOT/data/<name>_scan/<name>_scan_{date}.json` |
| 报告 MD | `STOCK_REPORTS_ROOT/<name>_scan_reports/<name>_scan_report_{date}.md` |
| sys 状态键 | `sys._<name>_status` / `sys._<name>_thread` / `sys._<name>_stop` / `sys._<name>_lock` |
| 统一结果键 | `sys._unified_status["<name>"]` |
| 文档 | `docs/stock-modules/<name>_scanner.md` |

`<name>` 用小写下划线英文，如 `event`、`breakout`、`dip_buy`。

---

## 9. 未来可选：正式策略注册表（重构方向）

当前是"约定式接口 + `unified_scanner` 显式编排"。若策略数量增多，可演进为**显式注册表**（零破坏重构方向，留作 roadmap）：

```python
# scripts/stock/strategy_registry.py（未来）
STRATEGIES = {}  # name -> StrategySpec
def register(name, start_fn, status_fn, stop_fn, result_fn, set_market_df_fn=None): ...
def all_strategies() -> list[StrategySpec]: ...
```

`unified_scanner` 改为遍历注册表自动编排，前端动态渲染每策略一栏。此重构不改变现有模块对外契约，可平滑过渡。**当前不需要做**，先按约定式接口跑。
