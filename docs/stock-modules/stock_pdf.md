# 股票 PDF 生成 (stock_pdf) — 详细功能文档

**文件路径**: `scripts/stock/stock_pdf.py`  
**最后更新**: 2026-04-27

---

## 1. 模块概述

- **核心职责**: 为 Jarvis 股票相关能力提供**统一的 ReportLab (platypus) PDF 渲染**：**6 种报告类型**、**A4 页边距**、**中文字体 (STSong-Light CID 优先)**、**与深色 UI 协调的色板**、**表格/标题/脚注** 的一致样式。  
- **系统角色**: **输出层** — 将各 API/扫描结果 JSON 转为可下载/归档的 **PDF 文件**；不计算因子或生成文本结论（内容由上游 data 提供）。  
- **上下游**  
  - 上游: Web/API 或脚本传入 `report_type` + `data: dict`（与各类 JSON 结果结构一致）。  
  - 下游: 默认 `STOCK_REPORTS_ROOT/pdf/{report_type}_{date}.pdf`。

**ReportLab 管道概览**  

```
register CID font → build ParagraphStyle 字典 STYLES
  → 按 report_type 选 _build_* 向 story 堆 Paragraph/Table/Spacer/HR
  → SimpleDocTemplate(pdf_path, A4, margins) → build(story)
  → 返回绝对路径
```

---

## 2. 金融理论基础

- **报告类型与投研场景**  
  - **短期/长期推荐**: 对应**全市场/主题**的**可执行性摘要**与**多维度分**的纸质留存。  
  - **个股分析**: 多章节（技术/基本面/情绪/资金/XGB/价格预测/DeepSeek）的**单票档案**。  
  - **价格预测**: **验证表**（预测 vs 实际、方向对否）+ **MAPE/方向准确率** — 与**预测评估**的实务指标一致。  
  - **自选股**: 持仓/观察列表的**快览表**。  
  - **国家队监控**: ETF/净流入/趋势/异常 — 对应**A 股政策资金与稳市预期**的民间叙事（非监管披露替代）。  
- **视觉语义**: 绿/红/金/紫 **Hex 色** 对应涨跌、贵金属、长期主题，降低**长文本**的认知负荷（仍非投资建议本身）。

---

## 3. 技术实现详解

### 3.1 核心数据结构

- **`ALLOWED_TYPES`**: `short_term`, `long_term`, `stock_analysis`, `price_prediction`, `watchlist`, `national_team`（**frozenset**）。  
- **`REPORT_TITLES`**: 与类型一一对应的中文题头。  
- **`COLORS`**: `primary/secondary/accent_* / text / bg_light / border / header_text` 等 **HexColor**。  
- **`STYLES`**: `title`, `subtitle`, `h1`–`h3`, `body`, `body_small`, `bullet`, `table_cell`, `footer` — 均设 `fontName=_CHINESE_FONT`（在注册成功时）。  
- **输入 `data`**: 因类型而异（见下**分类型**）。

### 3.2 关键函数/类

| 名称 | 作用 |
|------|------|
| `_register_chinese_font` | 注册 `UnicodeCIDFont("STSong-Light")`；失败回退 `Helvetica`（**中文可能缺字**）。 |
| `_safe` | `html.escape` + 换行转 `<br/>` 供 `Paragraph` 用。 |
| `_markdown_to_plain` | 去 `#`、粗体/链接/代码块/列表，用于把 Markdown **降级**为可折行纯文本。 |
| `_hr` | `HRFlowable` 分隔线。 |
| `_make_table` | 表头蓝底白字、斑马纹、网格；`repeatRows=1`。 |
| `_badge` / `_score_bar` | 内联标签与 10 格进度条。 |
| `_extract_date_str` | `data["date"]` 或今日本地日期。 |
| `_append_body_paragraphs` | 多段 `Paragraph` 追加。 |
| `_build_short_term` / `_build_long_term` / `_build_stock_analysis` / `_build_price_prediction` / `_build_watchlist` / `_build_national_team` | 各类型 story 构建。 |
| `generate_stock_pdf(report_type, data, output_dir=None) -> str` | **公共 API**，返回 PDF **绝对路径**。 |
| `_format_kv` | 将 dict/list **递归**格式化为纯文本，用于「趋势/异常」等块。 |

### 3.3 分类型 `data` 约定与布局要点

1. **short_term**（短期推荐）  
   - 标题 + 元数据表: `meta.market_total`, `layer1_count`, `layer2_count`。  
   - `top_picks[]`: 排名、名、价、涨跌幅、分数表四列标题为「综合 / 资金 / 技术 / 情绪」，**实现上**分别取 `final_score`、`fund_score`、`tech_score`、`sentiment_score`（字段名 `fund_score` 在 `scanner` Layer2 中为**基本面**分；列标题「资金」与 `ff_score` 资金流分**并非同一字段**，以当前 `stock_pdf.py` 代码为准）。  
   - `reasoning` / `risk` / `strategy`、买卖区间、**comprehensive** 子结构（**迭代 key：若 value 为 dict 取 name/score/detail**）、**DeepSeek** `report`/`reasoning` 大段。  

2. **long_term**（长期）  
   - 贵金属: `precious_metals.gold`/`silver` 多行表；`gold_silver_ratio`；`llm_outlook` 的 gold/silver/summary。  
   - 主题: `themes[]` 的 `name`, `logic`, `industries`, `catalysts`, 周期与置信。  
   - 长期标的: `picks[]` 含 `recommendation_reason`, `upside.dimensions` 与 `_score_bar`。  

3. **stock_analysis**（个股）  
   - 固定 7 键顺序输出（有则出）: `technical_report`, `fundamental_report`, `sentiment_report`, `fund_flow_report`, `xgb_report`, `prediction_report`, `deepseek_report` — **值为已渲染的长文本**（可 Markdown，经 `_markdown_to_plain` 简化）。需 `data["symbol"]`。  

4. **price_prediction**（价格预测）  
   - `sentiment`（恐惧贪婪/VIX/情绪简写）、`black_swan.alerts` 列表、`verifications` 昨日验证表、`aggregate_stats`、**results** 明日预测大表、非 `done` 的 `status`。  

5. **watchlist**（自选股）  
   - `watchlist[]` → 代码/名称/价格/涨跌幅/板块。  

6. **national_team**（国家队）  
   - `snapshot` KV、`etfs` 表、`trends`（dict 经 `_format_kv`）、`signals` / `anomalies` 列表、`verdict` 结论文本。  

**页脚**: 所有类型底部统一 `生成时间` + `Jarvis 股票模块 · 报告标题`。

---

## 4. 外部依赖与数据源

- **ReportLab**: `SimpleDocTemplate`, `Paragraph`, `Table`, `TableStyle`, `HRFlowable`, `A4`, `mm`, `getSampleStyleSheet`, `UnicodeCIDFont`, `pdfmetrics`。  
- **config**: `STOCK_REPORTS_ROOT`。  
- **无网络**；数据全部由调用方传入。  

---

## 5. 配置项与可调参数

| 项 | 值 | 说明 |
|----|-----|------|
| `_MARGIN_MM` | 18 | 四边页边距 (mm) |
| 输出目录默认 | `STOCK_REPORTS_ROOT/pdf` | 可被 `output_dir` 覆盖 |
| 输出文件名 | `{report_type}_{date}.pdf` | `date` 来自 `data` 或今日 |
| 字体 | STSong-Light CID | 失败回退 Helvetica |

**调优**: 大段 DeepSeek 文本在 PDF 中**无智能分页**优化，极长时可用上游摘要；表格列宽可针对屏幕阅读再调 `col_widths`。

---

## 6. 使用示例与工作流

```python
from stock_pdf import generate_stock_pdf, ALLOWED_TYPES, REPORT_TITLES
path = generate_stock_pdf("short_term", data_dict)  # data_dict 同扫描 JSON 结构
```

**协作**: 先由 `scanner` / `long_term_scanner` / 预测服务产出 JSON，再**原样**或略组装后传 `generate_stock_pdf`。

---

## 7. 已知限制与改进方向

- 中文依赖 **STSong** 在运行环境可注册；部分环境**只余 Helvetica** 时中文**方块或空白**。  
- `_markdown_to_plain` **去格式**强，**丢失列表层级与表格**。  
- `comprehensive` 的遍历在 `short_term` 中**对非 dict 的 value 走 bullet 展示**，若结构异常可能布局怪。  
- 未加**页眉页码/水印/BOM 合规**。（若需合规披露可扩展 `onFirstPage`/`onLaterPages`）  
- 改进: 接入 **Noto Sans CJK** 等 TTF 注册、保留部分 Markdown 结构（`paraStyle` 区分）、**图表**（ReportLab 绘图或嵌入 PNG）。  

---

## 附录: `__all__` 导出

`COLORS`, `STYLES`, `generate_stock_pdf`, `ALLOWED_TYPES`, `REPORT_TITLES` 供其他模块**风格复用**或白盒测试。  
