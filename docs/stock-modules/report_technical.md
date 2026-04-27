# 技术分析报告 (report_technical) — 详细功能文档

**文件路径**: `scripts/stock/report_technical.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 将 `technical_analysis.analyze` 产出的**结构化技术分析结果**转换为**纯中文、Markdown 格式、表格化**的**技术分析报告**（可打印或发聊天）；支持**独立运行**或被 `agent.py` 等调用。  
- **系统角色**: **展示层/报告层**，不重新计算 K 线；若未传入 `analysis` 则内部调用 `analyze(symbol)`。  
- **上下游**  
  - 上游: `technical_analysis`（与 `STOCK_DATA_DIR` 中 OHLCV/缓存一致）。  
  - 下游: 默认写 `STOCK_DATA_DIR/{symbol}/technical-report.md`；**不作为** RAG 主索引（与 scanner 的扫描报告可区分）。

---

## 2. 金融理论基础

- **技术分析可读化**: 将 RSI、MACD 柱、KDJ、布林 %B、量比、ATR% 等转化为**非专业用户**可读的**标签**（超买/超卖/放量/高波动等），体现「**指标解释**优先于数字堆砌」。  
- **多周期趋势**: 用收盘价相对 **MA5/20/60** 的偏离度，划分短期/中期/长期表述 — 对应**经典均线投资**的简化版。  
- **风险与波动**: 风险条（1–5）综合 **ATR%、RSI 极端、量比** — 与**波动率与尾部体验**的通俗映射（非 VaR 模型）。  
- **支撑阻力**: 展示枢轴/多档支撑阻力与**回望窗口内**高低点，对应**市场结构 (Market Structure)** 的零售版表述。  
- **A 股**: 报告脚注注明**数据来源: 新浪财经/东方财富**（与行情来源一致，便于用户理解**延迟与复权**等局限）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- 输入 `analysis: dict` 来自 `technical_analysis.analyze`，关键键：  
  - `price`: `close`, `change_pct`, `high`, `low`, `volume`  
  - `indicators`: `rsi_14`, `macd_histogram`, `kdj_j`, `bollinger_pct`, `volume_ratio`, `atr_pct`, `ma5`, `ma20`, `ma60`  
  - `signals`, `patterns`, `support_resistance`, `overall`, `date`  
- 若含 `error` 键，**整报告**只输出错误 Markdown。

### 3.2 关键函数/类

| 函数 | 说明 |
|------|------|
| `_risk_level(analysis) -> (int, str)` | 基础风险 3；`atr_pct>4` +1，`<1.5` -1；`rsi>80` 或 `<20` +1；`volume_ratio>2.5` +1；**夹紧 1–5**；返回中文标签。 |
| `_trend_assessment(analysis) -> dict` | `short`/`medium`/`long` 三档，基于 `close` 与 `ma5/ma20/ma60` 差百分比，阈值 ±5% 分「强势/偏多/偏空/弱势」类文案。 |
| `generate_report(symbol, analysis=None) -> str` | 主入口，返回**完整 MD 字符串**。 |
| `save_report(symbol, analysis=None) -> str` | 调 `generate_report` 后写入 `technical-report.md`，返回路径。 |

- **证券简称**: 尝试读 `STOCK_DATA_DIR/{symbol}/profile.json` 的 `股票简称` 作标题；失败用代码。

### 3.3 算法与计算逻辑

- **emoji 行**: 风险条为 `🟢*(5-risk_num) + 🔴*risk_num`；信号表用 🟢/🔴/⚪ 与中文「看涨/看跌/金叉/死叉/超卖/超买」子串匹配（简单规则，**可误判英文混合信号**）。  
- **形态表**: 遍历 `patterns`，列 `name`, `direction`, `strength`, `desc`。  
- **无形态**: 显式写「今日未检测到显著K线形态。」  
- **成交量展示**: 按亿/手万单位缩写。  
- **与 LLM 的关系**: 本模块**不调用**大模型，纯**确定性**模板渲染。文件头部 docstring 称可被 `agent.py` 调用 — 与 `llm_reasoning` 的**叙事报告**不同。

---

## 4. 外部依赖与数据源

- **import**: `json`, `os`, `logging`, `datetime`, `config.STOCK_DATA_DIR`, `OLLAMA_HOST`, `MODEL_USAGE`（**后二者当前文件内未使用**，保留或历史遗留，以代码为准）, `technical_analysis.analyze`。  
- **数据**: 与技术分析模块相同的数据源（行情 CSV 等）。  

---

## 5. 配置项与可调参数

- 无独立配置文件；**风险阈值**（ATR 4、量比 2.5、RSI 80/20）**硬编码**于 `_risk_level`。  
- **调优**: 若希望更偏保守的零售提示，可略降 RSI 极值或提高 ATR% 的「高风险」门限（需改代码）。  

---

## 6. 使用示例与工作流

```python
from report_technical import generate_report, save_report
md = generate_report("600519")           # 自动 analyze
path = save_report("600519")            # 写入 technical-report.md
```

与 `llm_reasoning` 可串联：先 `save_report` 得技术面附件，再 `generate_prediction` 综合其它维度。

---

## 7. 已知限制与改进方向

- 信号图标的文本匹配**脆弱**；英文信号名需扩展关键词。  
- `_risk_level` 为**经验加权**，**非**回测过最优参数。  
- 未内嵌**图表/截图**；纯 Markdown。  
- `OLLAMA_HOST` / `MODEL_USAGE` 未使用 — 可考虑删除多余 import 以减噪音（属代码卫生，非功能）。  
- 改进: 与统一主题 CSS/HTML 输出、或导出 `stock_pdf` 的技术章节共用片段。
