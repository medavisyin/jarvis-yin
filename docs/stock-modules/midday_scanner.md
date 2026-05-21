# 午盘极速隔夜套利扫描器 (midday_scanner) — 详细功能文档

**文件路径**: `scripts/stock/midday_scanner.py`  
**最后更新**: 2026-05-21

---

## 1. 模块概述

- **核心职责**: 针对**全市场 A 股**执行极速“三层漏斗”扫描与评估，旨在每日午间休市时（中午 12:30 左右），筛选出具备**高置信度尾盘突破、主力资金抢筹**特征的超短线套利标的。策略定位为**“今日尾盘（13:00 - 15:00）买入，明日早盘（9:30 - 10:00）冲高了结”的 T+1 极速隔夜套利**。
- **系统角色**: Stock 子系统的**超短线/高弹性博弈分支**，与短期全市场 `scanner.py`（周/月级持有）以及长线主题 `long_term_scanner.py`（半年/年级持有）互补。设计哲学：**极速分析（< 3分钟完成）、宁缺毋滥（每日推荐控制在最多 1-3 只）、严格止损与退场保障**。
- **上下游关系**
  - **上游**: AkShare/东财极速直连/新浪分页等多通道实时快照行情；`china_market_data.stock_fund_flow_signals` 主力资金流信号；`technical_analysis` 指标计算。
  - **本模块**: Layer 1 量价粗筛 $\rightarrow$ Layer 2 技术突破与资金流多因子并发评分（XGBoost不介入，纯规则极速并发）$\rightarrow$ Layer 3 呼叫 DeepSeek 进行并发隔夜胜率裁决与“冲高失败退场预案”制定 $\rightarrow$ Phase 4 自动生成 Markdown 极速内参报告，并写入本地历史 JSON 缓存与 RAG 索引。
  - **下游**: 前端 Web 弹窗轮询状态及加载内参 HTML，Telegram Bot (`bot_telegram.py`) 并发拉起、轮询，并将精选推荐直接推送到手机终端。

```text
       [全 A 股 5000+ 实时行情快照] 
                   │ (三级高可用备用路由: AkShare → 东财直连 → 新浪分页)
                   ▼
         Layer 1: 午盘量价快筛 (温和上涨+主力突破) -> 剩余最多 40 只
                   │
                   ▼ (ThreadPoolExecutor 8并发)
         Layer 2: 均线突破 + RSI + 主力资金吸筹评分 -> 排序 Top 10
                   │
                   ▼ (ThreadPoolExecutor 3并发 + DeepSeek reasoning="low" 极速判定)
         Layer 3: 胜率裁判 (verdict = "买入" or "观望") 
                   │ (早停机制: 刷满 3 只 "买入" 推荐即自动提前收尾)
                   ▼
       [报告生成与落盘] -> Markdown极速内参 / JSON缓存 / 索引至 RAG / 发送 Telegram 推送
```

---

## 2. 金融理论基础

- **隔夜套利与情绪溢价**: A 股实行 **T+1** 交易制度。普通投资者日内买入无法日内平仓，因而承受隔夜政策、外盘波动和次日早盘情绪的多重风险。午盘（12:30 左右）处于上午盘多空博弈尘埃落定、下午盘主力拉升建仓的前夕。在此时点买入，能最大限度降低日内“炸板闷杀”的时间风险，博取次日早盘集合竞价至开盘半小时（9:30 - 10:00）内主力惯性冲高、资金获利离场的“时间溢价”。
- **均线多头与技术突破垫**: 隔夜套利必须顺势而为。Layer 2 强调价格必须处于 **MA5** 与 **MA20** 均线之上，且 MA5 > MA20，确保个股处于短期多头共振通道。同时，结合 RSI（6日强弱指标）将区间锁定在 `[50, 75]` 的强势无超买区间，既保证了上涨动能，又避免了高位追涨停的泡沫风险（拒绝涨幅 > 7.5% 及 RSI > 75 标的）。
- **主力建仓特征 (聪明钱流向)**: 真正的隔夜爆发个股，其上午盘通常有主力资金（Smart Money）在休市前持续扫货。利用主力近 3 日、5 日净流入状态和“布局期/吸筹期”信号（`china_market_data.stock_fund_flow_signals`）对资金面予以 35% 的高权重考量，寻找量价配合的纯正“大单潜伏股”。
- **T+1 冲高失败的尾盘防御智慧**: 投机交易的核心在于非对称风险管理。本模块要求大模型必须为每只推荐股定制 **“冲高失败退场预案”**：如果明日高开低走或开盘半小时内（10:00前）放量冲高无力，超短线套利盘必须执行“一刀切离场、绝不将超短线做成中线套牢”的交易纪律，将最大单笔损失锁死在极小范围内。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **进度/状态寄存器** (`sys._midday_scan_status`):
  为了防范 Flask 路由中卸载模块导致内存变量丢失，该全局字典被**持久化存放在 `sys` 模块底层**：
  ```python
  sys._midday_scan_status = {
      "status": "idle",       # idle, running, completed, failed
      "progress": 0,          # 进度百分比 (0-100)
      "step": "",             # 当前执行步骤描述
      "started_at": "",       # 启动时间
      "elapsed_ms": 0,        # 耗时 (毫秒)
      "error": None,          # 异常报错信息
      "results_count": 0      # 选出的买入推荐股票数量
  }
  ```
- **扫描候选格式**:
  ```json
  {
    "symbol": "301322",
    "name": "绿通科技",
    "price": 42.15,
    "change_pct": 6.34,
    "turnover_rate": 23.43,
    "volume_ratio": 5.92,
    "amount": 120540000.0,
    "market_cap": 4200000000.0,
    "industry": "有色金属",
    "composite_score": 82.5
  }
  ```
- **大模型最终决策 JSON 格式**:
  ```json
  {
    "symbol": "000026",
    "name": "飞亚达",
    "verdict": "买入",       # 买入 / 观望
    "final_score": 88,
    "reasoning": "上午主力大单净流入0.8亿，技术形态放量突破120日线，板块共振走强",
    "risk": "明日大盘若低开，易受指数拖累",
    "limit_buy_price": 10.45,
    "take_profit_target": 11.10,
    "stop_loss_target": 10.15,
    "confidence_level": "高",
    "judged_by": "deepseek",
    "deepseek_reasoning": "<thinking>...</thinking>" # 深度推理内容
  }
  ```

### 3.2 关键函数接口

| 函数名 | 权限与范围 | 作用 |
|------|------|------|
| `start_midday_scan(use_deepseek=True)` | Public / 全局 | 启动守护线程，执行后台扫描 `_run_midday_scan_inner`。 |
| `stop_midday_scan()` | Public / 全局 | 置位 `sys._midday_stop_event` 优雅通知后台线程终止。 |
| `get_midday_scan_status()` | Public / 全局 | 线程安全地读取并富化当前扫描器的最新进度字典。 |
| `get_latest_midday_result()` | Public / 全局 | 加载最近一日完成生成的午盘扫描 JSON 数据。 |
| `_fetch_market_eastmoney_direct()` | Private / 内部 | **高可用容灾二线**：直接用 HTTP 请求抓取东财极速快照 API。 |
| `_fetch_market_sina_pagination()` | Private / 内部 | **高可用容灾三线**：循环分页抓取新浪行情接口，含频控避让指数重试。 |
| `_run_midday_scan_inner(use_deepseek)`| Private / 内部 | 后台线程主循环，执行 Layer 1 $\rightarrow$ 3 并落盘报告。 |

---

## 4. 外部依赖与数据源

### 4.1 数据通道与高可用容灾逻辑

模块的 Layer 1 行情快照具备**三通道极高可用性设计**：

1. **AkShare 通道**：
   * 默认调用 `ak.stock_zh_a_spot_em()`。
   * 特点：高集成度、返回全场 5000+ 数据，数据项完整。
2. **东财极速直连通道 fallback (`_fetch_market_eastmoney_direct`)**：
   * 当 AkShare 因接口下线、连接重置时触发。
   * 实现：直接向东方财富快照接口（`push2.eastmoney.com`）发送带有高伪装 Header 头的原生 HTTP Get 请求，单次拉回全市场 A 股所有核心实时量价字段。极速、延迟低。
3. **新浪分页容灾通道 fallback (`_fetch_market_sina_pagination`)**：
   * 当上述两个全量快照接口均因网络波动或反爬虫拒绝连接时触发。
   * 实现：循环分页请求新浪市场中心 API，每次拉取 80 只。
   * **智能退避重试 (Backoff Retry)**：当新浪返回 `456`、`403` 或 `503` 频控状态码时，分别采取 1.5s $\rightarrow$ 3.5s $\rightarrow$ 5.5s 的指数避让延迟，遇到单页重试多次失败时，主动放弃后续分页并对已有行数据进行合并，**严禁使线程彻底挂起或直接崩溃**。

### 4.2 资金与指标数据
* **技术指标**：由于 12:30 数据不含当天完整收盘价，系统通过 `fetch_daily_ohlcv` 和 `load_ohlcv` 获取历史 K 线（截至昨天），通过 `compute_indicators` 算得昨日收盘的 MA5、MA20 及 RSI 值，并使用**今日上午盘最新成交价**与之做动态比较。
* **主力资金流向**：通过 `china_market_data.stock_fund_flow_signals` 读入截至当天上午的 3D、5D 主力大单流入净额。

---

## 5. 配置项与可调参数

以下常量直接定义于模块文件头部，可根据行情特征和决策偏好进行调优：

| 参数 | 默认值 | 调整方向与金融建议 |
|------|------|------|
| `PRICE_MIN` / `PRICE_MAX` | `5.0` / `100.0` | 排除低于 5 元的垃圾股（含面值退市风险）和高于 100 元的高价机构抱团股。 |
| `CHG_MIN` / `CHG_MAX` | `2.5` / `7.5` | 排除上午下跌或横盘的弱势股；同时必须**排除涨幅 > 7.5% 的跟风股**以防尾盘炸板或明天开盘透支空间。 |
| `TURNOVER_MIN` | `2.0%` | 确保上午盘换手充足。若是下午需要更激进，可上调至 3.0%。 |
| `VOLUME_RATIO_MIN` | `1.5` | 强制量比放大，证明上午盘在主动放量建仓。 |
| `AMOUNT_MIN` | `50,000,000` | 上午盘成交额必须大于 5000 万，确保具备机构或大游资基础流动性。 |
| `CAP_MIN` / `CAP_MAX` | `3B` / `50B` | 市值锁定在 **30 亿至 500 亿**，这是有色、科技等 A 股短线弹性最佳的甜点市值区间。 |
| `max_workers` | `8` | 因子计算线程池并发大小。建议 8 - 12 之间，避免 CPU 飙升。 |
| `max_workers_l3` | `3` | DeepSeek 并发调用通道数。受限于 DeepSeek API 每分钟限制，建议设为 3。 |

---

## 6. 使用示例与工作流

### 6.1 外部 HTTP 工作流
在 Web 控制台点击按钮时，Flask 接口、前端 JavaScript 与后台扫描器的高层联动如下：

```javascript
// 1. 发送启动请求
fetch('/api/stock/midday/start', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({use_deepseek: true})
});

// 2. 轮询状态接口 (每3秒一次)
let timer = setInterval(async () => {
  let res = await fetch('/api/stock/midday/status');
  let data = await res.json();
  if (data.status === 'completed') {
    clearInterval(timer);
    // 3. 渲染结果
    let result = await (await fetch('/api/stock/midday/result')).json();
    renderHTML(result.picks);
  }
}, 3000);
```

### 6.2 命令行测试示例
直接执行该脚本，可以使用内置的 `__main__` 测试工作流（本地默认不使用 DeepSeek，仅调用本地 Qwen）：
```bash
cd c:\jarvis\scripts\stock
python midday_scanner.py
```

---

## 7. 已知限制与改进方向

1. **中午休市数据局限性**：
   * 12:30 的数据仅仅代表上午盘。若下午大盘突然跳水（如 2:30 发生黑天鹅），部分候选股下午可能出现“冲高回落、主力反手出货”的风险。
   * **改进方向**：在下午 14:40 - 14:50 左右，可加入轻量级“二次盘口追踪校准器”，如果原定 12:30 推荐的个股在下午盘口走坏（跌破 MA5 或主力流向大幅转负），在前端或 Telegram 发出**“红牌撤单警告”**。
2. **多源 API 反爬频控**：
   * A 股实时行情属于高频受保护数据，新浪与东财接口存在 IP 级拉黑风险。
   * **改进方向**：在本地 `config.py` 中，如果配置了 `STOCK_PROXY`，行情抓取应优先经过动态高匿代理池。
