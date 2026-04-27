# fundamental_analysis — 详细功能文档

**文件路径**: `scripts/stock/fundamental_analysis.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**：
  1. 汇总**本地** `profile.json`（公司信息）与 `realtime.json`（估值与价格）到结构化 `data` 字典；
  2. 通过 **akshare** `stock_financial_abstract_ths` 拉取**同花顺**财务摘要**年度**维度的最新报告期，解析中文「亿/万」与**百分比**字段；
  3. 将结果写入 `fundamentals.json`；
  4. 提供 **`score_fundamentals`** 五维加权 0–100 评分，以及生成 **`fundamental-report.md` 中文报告** 字符串。

- **系统角色**：**基本面分析/评分层**；**依赖** `fetch_market_data` 先落盘 profile 与 realtime（否则 `valuation` 与部分 `profile` 会偏空，评分仍用默认 50 分档）。

- **上下游**：

```
[profile.json + realtime.json] ─┐
                                 ├──► fetch_fundamentals ── fundamentals.json
[akshare 同花顺财务摘要 年度] ──┘
         │
         ▼
[score_fundamentals] / [generate_fundamental_report] ── fundamental-report.md
```

---

## 2. 金融理论基础

- **绝对估值与相对估值**：PE、PB 属**乘数法相对估值**；A 股行业差异大（**金融**常低 PB 高 P/E 特性与周期股不同），本模块的 PE/PB 打分**不区分行业**，**横截面**比较需谨慎。
- **盈利质量与股东回报**：**ROE**（杜邦分解的核心）是**长期复利**与竞争优势的**常用代理**；**净利率、毛利率**反映**商业模式与费用结构**；**杜邦/周转**在本模块**未**分解，仅用汇总财务比率。
- **成长性与周期**：**营收/利润同比**在 A 股易受**疫情、基数、非经常性损益**影响，单期同比应结合**多期**与**扣非**（本数据源若未取扣非，则**无法**在模型中体现扣非质量）。
- **资本结构与流动性**：**资产负债率**是**长期偿债压力**的粗指标；**流动比率**偏**短债**覆盖；A 股部分国企与地产链公司天然**高杠杆**行业，阈值应**分行业**解读。
- **规模因子**：`综合因素` 维用**市值**分档，对应实证资产定价中**规模溢价**的简化叙事（A 股曾长期存在**小盘风格**，不保证未来）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

**`fetch_fundamentals` 产出的 `data: dict` 结构**（键固定）：

```text
{
  "symbol", "fetched_at",
  "profile": { name, industry, listed_date, total_shares, float_shares, market_cap },
  "valuation": { pe_dynamic, pb, price, market_cap, float_cap },
  "financials": {
     report_date, revenue, net_profit, roe, gross_margin, net_margin, debt_ratio,
     revenue_yoy, profit_yoy, eps, bvps, current_ratio
  }
}
```

- **数值**经 `_safe_float` 或 `_*parse*` 后多为 **float** 或 `None`。
- **来源注意**：`profile` 来自**本地** `profile.json` 若存在；`valuation` 来自**本地** `realtime.json` 的**动态市盈率、市净率**等中文字段；**不保证**与交易日收盘后**一致**（取决于你上次 `fetch` 时间）。

**同花顺 DataFrame 处理**：`indicator="按年度"`，按 `报告期` **降序**取 **最新一行** 转 `latest` dict。

**解析函数**：

- `_parse_cn_number`：如 `"1862.22亿" → 186222000000.0`；`"万"` 乘 `1e4`；去 `%` 在 `_parse_pct` 前由调用方**按字段类型**使用。
- `_parse_pct`：如 `"52.19%"` → `52.19` 浮点。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `_safe_float(val, default=None)` | `None`/`pd.NaN` 或无法转换时 `default` |
| `fetch_fundamentals(symbol) -> dict` | 写 `fundamentals.json` 并返回 |
| `load_fundamentals(symbol) -> dict` | 只读 JSON |
| `score_fundamentals(data) -> dict` | 五维子分+权重+**加权总分**；返回 `total_score`, `dimensions`, `symbol`, `name` |
| `generate_fundamental_report(symbol) -> str` | 无缓存时先 `fetch_fundamentals`；`score` 后拼 Markdown 表格、进度条**字符块**、写 `fundamental-report.md` |

**`score_fundamentals` 各维度**（**代码真实阈值**）：

1. **盈利能力 (25%)**  
   - 基准分 50。若 `roe` 有值：>25 →95；>20→85；>15→75；>10→60；>5→40； else →20。  
   - 若 `net_margin>30`，在以上基础上**再 +10** 封顶 100。  
   - `detail` 字符串带 ROE 与净利率。

2. **成长性 (25%)**  
   - 基准 50。优先用 `profit_yoy` 分档：>50 →95；>30→85；>15→70；>0→55；>-10→35； else →15。  
   - 若 `rev_yoy>30` → **+10 封顶 100**；若 `rev_yoy<-10` → **-10 下限 0**。

3. **估值水平 (20%)**  
   - 基准 50。若 `pe` 有值且 >0：`<10`→90；`<15`→80；`<25`→65；`<40`→45；`<80`→25； else →10。  
   - 若 `pb<1`（且非 None/0 异常依赖下游数据），`value_score+15` 封顶 100。  
   - **问题**：`pe` 为 **0 或负**（亏损）时，代码走 `0 < pe < 10` 不成立，会落入 **elif 链的后续或最后 else**；`pe` 为 `None` 时**保持 50**。解读亏损股时需**理解这一行为**（偏机械）。

4. **财务健康 (15%)**（`debt_ratio` 资产负债率 %）  
   - <30 →90；<50→75；<65→55；<80→30； else →10；**None 则保持 50**。

5. **综合因素 (15%)**（**市值** `market_cap` 来自**估值**的 `市场_cap` 字段，单位在 akshare/本地通常为**元**；代码中 `cap_yi = cap/1e8`）  
   - `cap` 有值时：>1000 亿→70；>100 亿→60；>30 亿→50； else →40。  
   - 无 `cap` → 50 且 `detail` 为 `"N/A"`（注意 `f-string` 中若 `cap` 缺省会走 `if cap` 的否分支，**不会**除零）。  
   - 若 `cap=0` 在浮点，行为同 **falsy**，misc_score=50。

**`generate_fundamental_report` 的评级**（按 `total`）：≥80 优秀；≥65 良好；≥50 一般；≥35 偏弱；**else** 较差。

**报告中的财务表**：营业收入、净利润、ROE、毛利率、净利率、负债率、营收同比、利润同比、PE、PB、市值、行业。

### 3.3 算法与计算逻辑

- **总分**：`sum(score_i * weight_i)`，**权重和为 1.0**（0.25+0.25+0.20+0.15+0.15）。

- **报告格式化 `_fmt_money`**：绝对值 ≥1e8 用**亿**；≥1e4 用**万**；否则两位小数；负数前加**全角/Unicode 减号**（`−`）。

---

## 4. 外部依赖与数据源

- **库**：`akshare`, `pandas`。
- **数据接口**：`ak.stock_financial_abstract_ths(symbol, indicator="按年度")`；字段名依赖**同花顺摘要**的**中文列名**（`报告期、营业总收入、净利润、...`）。
- **本地文件**：`STOCK_DATA_DIR/{symbol}/profile.json`, `realtime.json`, 输出 `fundamentals.json` 与 `fundamental-report.md`。
- **缓存**：`fetch_fundamentals` **总是重写** `fundamentals.json`；`generate_fundamental_report` 先 `load`，空则**再 fetch**。

---

## 5. 配置项与可调参数

- 无环境变量；**维权重与阈值**全部硬编码在 `score_fundamentals`。
- `fetch_fundamentals` 未暴露 `indicator` 参数，**固定年度**；若需**按季度**需改代码。

**调优建议**：行业中性评分应引入**行业分位**或**相对于行业中值**的 Z-score；亏损 PE 处理应显式**分支**（如用 EV/EBITDA 或**剔除异常**）。

---

## 6. 使用示例与工作流

```python
from fundamental_analysis import fetch_fundamentals, score_fundamentals, generate_fundamental_report

data = fetch_fundamentals("600519")
scoring = score_fundamentals(data)
print(scoring["total_score"], scoring["dimensions"])

md = generate_fundamental_report("600519")
# 同时写 fundamental-report.md
```

**工作流**：先 `update_stock_data` 或至少 `fetch_company_profile`+`fetch_realtime_quote` 保证本地有估值/公司名 → 本模块 `fetch_fundamentals` 或**直接** `generate_fundamental_report`。

---

## 7. 已知限制与改进方向

- **行业未分层**，金融/科技/制造同一 PE 阈值**不合理**；`综合因素` 仅用市值大小，**非** Fama-French 完整定义。
- **同花顺摘要** 字段**偶发缺失**时多维度为 **None→50 分**，易出**无信息中评**。
- **亏损股 PE 逻辑** 未单独建模，分数可能**不直观**。
- **无审计** 财务造假风险；`流动比率` 取到则未参与当前 `score`（**仅**出现在 `financials` 与潜在扩展，**本版本评分未用** 流动比率，属**可改进点**：代码中 `current_ratio` 被拉取进 `financials` 但 `score_fundamentals` **未引用** `current_ratio`）。

---
