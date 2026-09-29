# Memory: 国内大模型 API 现价对比

**Generated**: 2026-09-29 14:00
**Last updated**: 2026-09-29 14:00
**Project**: c:\jarvis
**Focus**: 中国内地官方按量 API 价格，供选型

---

## Goal & Scope

对比国内大模型 API 现价（DeepSeek、智谱 GLM、小米 MiMo，以及通义、豆包、MiniMax、Kimi），按人民币 / 百万 tokens，方便选一个默认可付费模型。

---

## Key Decisions

1. **默认付费模型倾向小米 mimo-v2.6-flash**：实时价输入 1 / 输出 2，无峰谷，1M 上下文，全模态。一次「1 万输入未命中 + 2 千输出」约 0.014 元。
2. **Rejected: Kimi K3 当默认**：中国区输入 20 / 缓存命中 2 / 输出 100，同一次调用约 0.40 元。
3. **DeepSeek Flash 适合能错峰、输出不太长的场景**：空闲 1 / 4，高峰翻倍；周末和法定假日全天按空闲价。思考默认开启。
4. **智谱 GLM-4.7-Flash 可当免费垫底**：文本免费。GLM-4.7 输出超过约 200 token 从 2/8 跳到 3/14。

---

## Confirmed Assumptions

- 用户要的是中国内地官方按量价，用来自己选模型，不是改 Jarvis 配置。
- 口径按短上下文最低档；DeepSeek 分峰谷；促销价单独标注。

---

## Key Discoveries

- 核对日 2026-09-29。完整表在 canvas：`C:\Users\rong.yin.MEDAVIS\.cursor\projects\c-jarvis\canvases\cn-llm-api-prices.canvas.tsx`
- DeepSeek `deepseek-flash` 现为 V4.1-Flash。空闲输入缓存未命中 1 元、输出 4 元；高峰 2 / 8。Pro 空闲 4.5 / 13.5，高峰 9 / 27。高峰为工作日 9:00–12:00、14:00–18:00。
- 小米 `mimo-v2.6-flash`：缓存命中 0.02 / 未命中 1 / 输出 2。`mimo-v2.6-pro`：0.025 / 3 / 6。批量半价。
- 智谱 GLM-5.3：8 / 28，缓存命中 2。GLM-5.3-Flash 限时五折 0.4 / 1.4（标价 0.8 / 2.8）。GLM-5 短上下文 4 / 18。
- 通义中国内地：`qwen-flash` ≤128K 为 0.15 / 1.5；`qwen3.5-flash` 0.2 / 2；`qwen3.5-plus` 0.8 / 4.8；`qwen3.7-max` 12 / 36。
- 豆包：2.0 Mini 0.2 起 / 2 起；2.1 Turbo 3 / 15；2.1 Pro 6 / 30。
- MiniMax-M3 ≤512K 永久五折：2.1 / 8.4，缓存读取 0.42；超过 512K 翻倍。
- Kimi 中国区与国际美元价分开，Key 和 base URL 不要混用。

---

## Current State

- **Working**: 2026-09-29 官方价对比已整理，canvas 可打开。
- **Pending**: 用户尚未最终拍板要接入哪一家。
- **Blocked**: 无。

---

## Next Steps

1. [ ] 用户选定模型后，再改 Jarvis 的 API 配置。

---

## References

- `C:\Users\rong.yin.MEDAVIS\.cursor\projects\c-jarvis\canvases\cn-llm-api-prices.canvas.tsx` — 价格对比 canvas
- https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ — DeepSeek
- https://open.bigmodel.cn/pricing — 智谱
- https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go — 小米
- https://help.aliyun.com/zh/model-studio/model-pricing — 通义百炼
- https://platform.minimaxi.com/docs/guides/pricing-paygo — MiniMax
- https://platform.kimi.com/ — Kimi 中国区 K3 价

---

**Confirmed at**: 2026-09-29
