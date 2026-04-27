# fetch_market_data — 详细功能文档

**文件路径**: `scripts/stock/fetch_market_data.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：基于 **akshare** 与**新浪财经 / 东方财富**等公开 HTTP 接口，拉取**A 股**日线 OHLCV、实时行情、公司概况、个股新闻；将结果**落盘**到以股票代码为子目录的本地文件中；提供**一键汇总更新**与本地**加载**接口。
- **系统角色**：股票流水线的**数据获取与持久化层**，为 `technical_analysis`（读 `daily.csv`）、`watchlist`（读/触发更新）、`fundamental_analysis`（间接依赖 profile/realtime）提供**原始与半原始数据**。
- **上下游关系**：

```
[akshare / 新浪 / 东方财富 API]
         │
         ▼
[fetch_market_data.py] ── 写入 STOCK_DATA_DIR/{symbol}/
    ├── daily.csv, realtime.json, profile.json, news/YYYY-MM-DD.json
         │
         ├── technical_analysis.load_ohlcv → daily.csv
         ├── watchlist (缓存名/行业、refresh_all_data)
         └── fundamental_analysis 读取 profile.json / realtime.json
```

---

## 2. 金融理论基础

- **有效市场与信息集合**：价格与成交量已反映**公开可得信息**；本模块拉取**行情、新闻、公司行业**，对应投资者用于**信息更新**与**新闻驱动事件研究**的输入。A 股市场存在涨跌停、T+1 等制度，**实时价与日线**是短线与波段策略的**共同基础**。
- **前复权/后复权/不复权**：`fetch_daily_ohlcv` 的 `adjust` 影响**历史价格可比性**——前复权（`qfq`）适合**技术分析序列连续性**；后复权（`hfq`）在部分回测中用于**真实涨跌幅**链；本模块主路径默认**前复权**（`qfq`），与均线、MACD 等**典型用法**一致。
- **公司概况与行业**：行业、市值等是**行业配置与比较估值**的维度；A 股行业分类有证监会/申万等多套口径，本模块以数据源返回字段为准（东财/akshare 文本）。
- **新闻数据**：用于事件研究与情绪分析上游；**不等同于**内幕信息或保证收益，需注意**滞后与噪声**。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`fetch_daily_ohlcv` 返回的 `pd.DataFrame`（akshare 主路径）**  
  列名以中文为主，文档字符串声明包含：`日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率`（实际列以 akshare 返回为准）。
- **新浪备用 `_fetch_ohlcv_sina` 构造的列**：同上中文列；`成交额/振幅/涨跌幅/涨跌额/换手率` 在原始 JSON 中缺省，代码将部分置 `0.0` 后，对`涨跌额/涨跌幅/振幅`用前收盘推算（见 3.3）。
- **`fetch_realtime_quote` 的 `dict`**：至少含 `代码、名称、今开、昨收、最新价、最高、最低、成交量、成交额、涨跌幅、涨跌额` 等；保存前会写入 `_fetched_at`（ISO 时间），并将 NaN 浮点转 `None`。
- **`update_stock_data` 的 `summary: dict`**：`symbol`, `errors: list`, `daily_rows`, `profile`/`news_count`/`realtime` 等键，`updated_at` 时间戳。

**磁盘布局**（每只股票）：

- `{STOCK_DATA_DIR}/{symbol}/daily.csv`
- `realtime.json`
- `profile.json`
- `news/{today}.json`（`today` 为 `YYYY-MM-DD`）

### 3.2 关键函数/类

| 函数 | 签名要点 | 返回值 | 核心逻辑 |
|------|-----------|--------|----------|
| `_symbol_dir(symbol)` | `str` | 路径 | `makedirs` 后返回 `{STOCK_DATA_DIR}/{symbol}` |
| `_sina_prefix(symbol)` | 沪市 `sh`，否则 `sz` | 与 A 股代码规则一致：`6/5/9` 开头为 `sh` |
| `_retry(fn, *args, **kwargs)` | 最多重试 | 成功返回值 | 指数退避 `sleep(_RETRY_DELAY * (attempt+1))` |
| `_fetch_ohlcv_sina(symbol, datalen=500)` | | `DataFrame` | GET 新浪 K 线 JSON，`scale=240`（日），**不复权**、无日期范围 |
| `fetch_daily_ohlcv(symbol, start_date=None, end_date=None, adjust="qfq")` | | `DataFrame` | 默认约 **2 年**起点、今天终点；在**子线程**中调 `ak.stock_zh_a_hist`，`join(20s)` 超时或异常则**新浪备用**；结果写 `daily.csv` |
| `_fetch_realtime_sina(symbol)` | | `dict` | 解析 `hq.sinajs.cn` 逗号字段，算涨跌幅 |
| `fetch_realtime_quote(symbol)` | | `dict` | 先新浪，失败则 `ak.stock_zh_a_spot_em` 全市场筛选代码 |
| `_fetch_profile_akshare` / `_fetch_profile_em_survey` | | `dict` | 东财 `stock_individual_info_em` 或 H10 `CompanySurveyAjax` 的 `jbzl` 行业等 |
| `fetch_company_profile` | | `dict` | 合并；写 `profile.json` |
| `fetch_stock_news(symbol, limit=20)` | | `list[dict]` | `stock_news_em`，取前 `limit` 条，按日落盘 |
| `load_daily_ohlcv` / `load_realtime` | | `DataFrame \| None` / `dict` | 只读本地 |
| `update_stock_data(symbol)` | | `summary` | 顺序：日线、公司、新闻、实时；**分项 try**，错误记入 `errors` |

**模块常量**：`_RETRY_DELAY=1`, `_MAX_RETRIES=2`, `_PROXIES` 在 `STOCK_PROXY` 非空时 `{"http":..., "https":...}`。

### 3.3 算法与计算逻辑

- **日线主路径**：`ak.stock_zh_a_hist(period="daily", start_date, end_date, adjust)` —— 与东财/新浪数据源实现相关。
- **线程与超时**：避免 akshare 卡死，**20 秒**内未完成则抛错并走新浪备用（牺牲复权与日期窗）。
- **新浪备用 K 线**：  
  - 涨跌幅：\(\text{涨跌幅} = \frac{C_t - C_{t-1}}{C_{t-1}} \times 100\)（%）  
  - 涨跌额：\(C_t - C_{t-1}\)  
  - 振幅：\(\frac{H_t - L_t}{C_{t-1}} \times 100\)（%）（代码实现为以**昨收**为分母之变形用法，与常见「(高-低)/昨收」一致）
- **新浪实时价**：`涨跌幅` 由昨收与最新价计算；成交量等字段自字符串解析为数值。

---

## 4. 外部依赖与数据源

- **第三方库**：`akshare`, `pandas`, `requests`。
- **本模块 `config` 依赖**：`STOCK_DATA_DIR`, `STOCK_CACHE_DIR`（`STOCK_CACHE_DIR` 在**本文件内未使用**，仅被 import，实际缓存为各文件直接落盘）。
- **网络端点**（随数据源变更可能变化）：新浪 `money.finance.sina.com.cn` K 线、新浪 `hq.sinajs.cn` 实时；东财 `emweb.securities.eastmoney.com/.../CompanySurveyAjax`。
- **缓存策略**：
  - 日线/实时/新闻**每次拉取后覆盖/追加写入**；新闻按**当日文件名** `news/{date}.json` 存储。
  - 无显式「过期时间」；新鲜度由用户重复调用 `update_stock_data` 或上层调度决定。

---

## 5. 配置项与可调参数

| 参数/常量 | 位置 | 默认值 | 选择理由/说明 |
|------------|------|--------|---------------|
| `STOCK_PROXY` | `config` | 空 | 统一代理给 `requests`（及间接影响网络稳定性） |
| `start_date` / `end_date` | `fetch_daily_ohlcv` | 约 730 天前 / 今天 | 平衡数据量与请求时间 |
| `adjust` | `fetch_daily_ohlcv` | `qfq` | 便于技术指标连续 |
| 线程超时 | `fetch_daily_ohlcv` 内 | `20` 秒 | 防止 akshare 挂死 |
| `_MAX_RETRIES` / `_RETRY_DELAY` | 模块级 | 2 / 1 秒 | 抑制瞬时网络失败 |
| `fetch_stock_news(..., limit=20)` | 函数参数 | 20 | 控制体积与反爬风险 |

**调优建议**：全市场实时（akshare 回退）较重，应**优先保证新浪单股**可用；生产环境可加大日线线程超时或增加重试次数（需改代码）。

---

## 6. 使用示例与工作流

```python
from fetch_market_data import fetch_daily_ohlcv, fetch_realtime_quote, update_stock_data

# 只更新一只股票的全部维度
summary = update_stock_data("600519")

# 仅拉日线（默认前复权、约两年）
df = fetch_daily_ohlcv("600519")

# 实时
rt = fetch_realtime_quote("600519")
```

与 **watchlist**：`refresh_all_data` 对列表内每支调用 `update_stock_data`。与 **technical_analysis**：需先有 `daily.csv`（本模块或手工放置）。

---

## 7. 已知限制与改进方向

- **新浪备用**不支持用户指定的 `start_date/end_date/复权`，与主路径不一致，回测需注意。
- `STOCK_CACHE_DIR` 被 import 但未使用，易造成读者误解；可后续统一**元数据/ETag 缓存**到该目录或移除 import。
- 实时行情在 akshare 回退时依赖**全市场** `stock_zh_a_spot_em()`，**慢且易被限流**。
- 新闻/财务接口依赖第三方稳定性，**无 SLA**；A 股节假日无成交但模块仍可能按「今天」写新闻文件名。

---
