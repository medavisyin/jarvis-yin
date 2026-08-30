# 近5年高二次突破检测器与扫描器 (ath_rebreak)

**文件路径**: `scripts/stock/ath_rebreak.py` · `scripts/stock/ath_rebreak_scanner.py`  
**最后更新**: 2026-08-30

## 口径（必须写进报告）

v1 标杆是现有 `daily.csv` 的最高价，约 **5 年、前复权**。用户界面与报告写 **「近5年高（前复权）」**，不要写成上市以来的最高价。

第一次收盘站上该标杆 **不是买点**。回踩后再收盘突破（且距第一次突破至少 3 个交易日、信号落在最近 3 根 K）才是买点候选。涨停可检出但 `tradeable=False`。

回踩标签：`below_high` / `pct_3_8` / `shallow`。状态机：同一根创新高 K 线优先记为二次突破，不可重置为新的第一次突破。

## 接入

- 单股：`technical_analysis.analyze` 写入 `five_year_rebreak`；DeepSeek 材料用 `format_five_year_rebreak_section`。
- 推荐：`ath_rebreak_scanner` 作为统一扫描第三套；左右漏斗不改。
- 小白说明：[strategy-ath-rebreak-deepseek.md](./strategy-ath-rebreak-deepseek.md)
