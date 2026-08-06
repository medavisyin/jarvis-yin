# Memory: National Team ETF Freshness Fix

**Generated**: 2026-07-30 ~14:59 UTC+8
**Last updated**: 2026-07-30 ~20:00 UTC+8
**Focus**: 国家队 — 日更诚实 + 盘中弱代理（放量/止跌/溢价/同步拉升）

---

## Goal & Scope (required)

日更份额诚实展示；盘中弱代理：放量T0 + 止跌灯 + 持续溢价增强 + 多宽基同步拉升；分钟优先 push2delay。

---

## Key Decisions (required)

1. 指标1：T0+1min Low < day_low → RED。
2. 指标2：recovery ≥40% GREEN；[0,40) YELLOW；<0 RED；尾盘收盘结算不跨日。
3. 持续溢价：T0后增强标签；5分钟内3/5次510300>0.10% + 另1只>0.05%；9:30-9:45跳过。
4. 同步拉升：≥3只近5分钟上涨且510300领涨。
5. 资金流 ak 重试改为 3 次后快切 delay。

---

## Current State (required)

- **Working**: intraday 模块含 volume/premium/sync；单测 **32 passed**
- **Pending**: 重启 Jarvis 实测卡片数字与标签
- **Blocked**: 东财全断时仍可能 NO_DATA

---

## Next Steps (required)

1. [ ] 重启 Jarvis 验证盘中卡片
2. [ ] 按需 commit / review

---

## References (required)

- `scripts/stock/national_team_intraday.py`
- `scripts/rag/routes/stock.py` / `templates/index.html`
- `tests/test_national_team_intraday.py`

