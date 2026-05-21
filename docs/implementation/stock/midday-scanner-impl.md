# 午盘极速隔夜套利扫描器实现设计 (midday-scanner-impl)

**文件路径**: `docs/implementation/stock/midday-scanner-impl.md`  
**最后更新**: 2026-05-21

---

## 1. 核心设计背景

用户提出了对 A 股市场的**超短线套利（T+1 隔夜）**需求，即“今天尾盘买入，明天早盘冲高卖出”。
该策略需要用户在中午 **12:30 的休市决策窗口**内完成全市场扫描，且用户**仅有 15 分钟左右的决策时间**。这为扫描系统的性能、数据链路的可用性以及大模型的响应速度提出了极高要求。

本文档详细阐述午盘极速隔夜套利扫描器的多线程池并发、三通道高可用以及内存持久化设计，指导系统的长期维护。

---

## 2. 总体架构与数据流

午盘扫描器属于轻量级、实时响应型服务。总体流程划分如下：

```text
  ┌────────────────────────────────────────────────────────┐
  │         HTTP POST /api/stock/midday/start             │
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │           sys._midday_scan_thread.start()              │
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │  Layer 1 行情获取与首层过滤 (10% 进度)                  │
  │  三层通道: AkShare → 东财直连 → 新浪分页 + 指数避让重试   │
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │  Layer 2 技术突破 + 主力资金面并发打分 (30% 进度)       │
  │  ThreadPoolExecutor (8个workers) 并发度量，单股超时15s │
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │  Layer 3 大模型并发评判与胜率裁决 (60% 进度)            │
  │  · 裁切至前 6 名最强龙头股                             │
  │  · ThreadPoolExecutor (3个workers) 并发调用 DeepSeek   │
  │  · low reasoning_effort + 单次 35s 强超时保护           │
  │  · 核心早停机制：满 3 只 "买入" 推荐立刻提前收尾退出      │
  └──────────────────────────┬─────────────────────────────┘
                             ▼
  ┌────────────────────────────────────────────────────────┐
  │  Phase 4 结果合并、落盘与热重载同步 (90% 进度)          │
  │  保存 JSON, Markdown内参并索引至 RAG                      │
  └────────────────────────────────────────────────────────┘
```

---

## 3. 关键架构技术设计

### 3.1 基于 `sys` 模块的状态持久化

在 Python Flask 的某些多模块系统中，热重载或动态路由重载装饰器（如 `@_with_stock_imports`）会在每次请求完成后，从 `sys.modules` 中彻底卸载（Delete）子模块，以防止变量命名空间污染。这会导致传统模块级全局变量（如 `_scan_status`）在请求轮询间隔内**被瞬间清除，回退到初始化 `'idle'` 状态**，进而导致前端进度条卡死。

为了在无数据库、无外部 Redis 的原生环境下，实现完美的“进程级状态持久化”，系统将状态寄存器挂载到 `sys` 模块底层。
在 `midday_scanner.py` 初始化时，执行属性动态绑定：

```python
import sys
import threading

if not hasattr(sys, "_midday_scan_lock"):
    sys._midday_scan_lock = threading.Lock()
if not hasattr(sys, "_midday_stop_event"):
    sys._midday_stop_event = threading.Event()
if not hasattr(sys, "_midday_scan_status"):
    sys._midday_scan_status = {
        "status": "idle",
        "progress": 0,
        "step": "",
        "started_at": "",
        "elapsed_ms": 0,
        "error": None,
        "results_count": 0
    }
if not hasattr(sys, "_midday_scan_thread"):
    sys._midday_scan_thread = None

# 内存指针引用对齐
_scan_lock = sys._midday_scan_lock
_stop_event = sys._midday_stop_event
_scan_status = sys._midday_scan_status
```
* **效果**：无论装饰器如何清理、重载或刷新 `midday_scanner` 模块命名空间，新加载的模块仍会读取相同的 `sys` 底层物理地址属性。接口能始终获取实时更新、线程安全的后台扫描进度。

---

### 3.2 因子打分层（Layer 2）多线程池池化

为了在极短时间内完成数十只初筛股的 50+ 维因子和信号拉取，设计采用多线程池结构。
* **计算封装**：将单只股票的 MA 均线突破、RSI、主力 3D/5D 资金流向计算封装在自包含的 `analyze_single_stock(stock_dict)` 闭包中。
* **池化执行**：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

enriched_candidates = []
cand_lock = threading.Lock() # 线程安全写入

max_workers = min(8, len(candidates)) if candidates else 1
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(analyze_single_stock, stock): stock for stock in candidates}
    for future in as_completed(futures):
        if _stop_event.is_set():
            break
        try:
            future.result(timeout=15)  # 单股分析 15s 强超时保护
        except Exception as e:
            stock_info = futures[future]
            log.warning("Layer 2 对 %s 的分析异常: %s", stock_info.get("symbol"), e)
```
* **性能对比**：单线程处理 40 只股票需要约 20-30 秒，8 线程并发将耗时压低至 **3-5 秒**。

---

### 3.3 大模型决策层（Layer 3）并发调用与早停 (Early Exit)

大模型调用通常是整个 RAG Runtimes 中最大的延迟瓶颈。在 15 分钟超短买入决策时间内，串行呼叫 10 次大模型是不可接受的（约需要 60-100 秒）。为此，Layer 3 采用了**并发呼叫与早停机制**的联合优化。

#### 1. 龙头池截断与 3 通道并发
* 排序 Layer 2 评分，仅选择最强的 **Top 6** 龙头进行 Layer 3 大模型深度评判。
* 开启 **`max_workers_l3=3`** 的线程池，并发向 DeepSeek 发送决策请求。
* 使用 **`reasoning_effort="low"`**。对于高时效性、强定量输出（JSON verdicts）的超短线套利场景，低推理开销（`low`）不仅大幅降低了输出延迟（单次响应降至数秒），还能有效规避长时间思考导致的 API 超时。
* 单次大模型呼叫配备 **35秒硬性超时** (`timeout=35`)，防止异常 hang 死卡住进度。

#### 2. 大模型早停机制 (Early Exit)
* **业务背景**：隔夜套利属于“兵在精而不在多”的非对称博弈，扫描器最终推荐的精品股应严格控制在 1-3 只。如果已经并发出炉了 3 只被判定为 `verdict == "买入"` 的股票，继续评估剩余龙头纯属时间和 Token 资源的浪费。
* **机制实现**：

```python
final_picks = []
picks_lock = threading.Lock()

def evaluate_stock_l3(stock):
    if _stop_event.is_set():
        return
        
    # 核心早停校验：如果已刷满 3 只推荐，则线程快速空转退出
    with picks_lock:
        if len(final_picks) >= 3:
            return
            
    # ... 执行 call_deepseek ...
    if parsed.get("verdict") == "买入":
        with picks_lock:
            if len(final_picks) < 3:
                final_picks.append(parsed)
```
* **效果**：大模型层平均总耗时从 1.5 分钟骤降到 **20-40秒** 左右。

---

## 4. 路由注册与热重载规范

午盘扫描模块 `midday_scanner.py` 作为 Flask 服务（`scripts/rag/agent.py`）的子系统，其 HTTP Endpoint 必须纳入统一的动态热重载管理：

1. **注册至 `routes/stock.py` 刷新列表**：
   在 `_STOCK_MODULES` 全局列表中增加 `"midday_scanner"`：
   ```python
   _STOCK_MODULES = [
       "config", "fetch_market_data", ..., "midday_scanner"
   ]
   ```
2. **入参验证**：
   在 `/api/stock/midday/start` 接口中，对传入的 JSON 体做严格校验与类型强制反转：
   ```python
   body = request.get_json(silent=True) or {}
   use_ds = bool(body.get("use_deepseek", True)) # 强布尔转换
   ```
