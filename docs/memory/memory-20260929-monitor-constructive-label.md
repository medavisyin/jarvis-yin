# Memory: Monitor Constructive Label

**Generated**: 2026-09-29
**Last updated**: 2026-09-29 09:40
**Project**: c:\jarvis
**Focus**: Rename the news-monitor Happy variant button to Constructive news

---

## Goal & Scope

On `http://127.0.0.1:18889/news/monitor`, the variant filter button for id `happy` displays "Happy". The layer and panel for that variant are already "Constructive news", so the button label should match.

In scope: frontend button copy only (`VARIANT_LABEL.happy` in `web/src/features/news/worldMonitor/WorldMonitorPage.tsx`), from "Happy" to "Constructive news".

Out of scope: internal variant id `happy`, API query param, keyword classification, tests that assert the id, the layer label (already "Constructive news"), and the other variant buttons.

---

## Key Decisions

1. **Button label becomes "Constructive news"**: Matches the existing layer/panel name. Internal id stays `happy`.
2. **Rejected: short label "Constructive"**: User chose the full source name used by the layer.
3. **Rejected: rename internal id to constructive**: User kept the API variant string as `happy`.

---

## Confirmed Assumptions

- The visible mismatch is the top variant button, not the map-layer checkbox (that checkbox already says "Constructive news").
- Clicking the renamed button should load the same `variant=happy` dashboard as today.

---

## Constraints & Non-Goals

- Do not change the API `variant` string.
- Do not retitle World / Tech / Finance / Commodity / Energy.

---

## Key Discoveries

- Display label lives in `web/src/features/news/worldMonitor/WorldMonitorPage.tsx` (`VARIANT_LABEL.happy = "Happy"`).
- Backend catalog already uses the right words: `scripts/pipeline/world_monitor.py` layer id `happy` has label "Constructive news"; the happy panel list is also "Constructive news".
- Variant id `happy` is part of `MonitorVariant` and `VARIANTS`; keyword bucket is `_HAPPY_KW`.

---

## Current State

- **Working**: `VARIANT_LABEL.happy` is "Constructive news". `web/dist` rebuilt. Fresh browser on `http://127.0.0.1:18889/news/monitor` shows the button; clicking it selects that variant and the map layer is "Constructive news". No button labeled Happy.
- **Pending**: None.
- **Blocked**: None.

---

## Next Steps

1. [x] Set `VARIANT_LABEL.happy` to "Constructive news"
2. [x] Verify the button on `/news/monitor`

---

## References

- `web/src/features/news/worldMonitor/WorldMonitorPage.tsx` -- variant button labels
- `scripts/pipeline/world_monitor.py` -- layer catalog label "Constructive news", variant id `happy`
- `web/src/lib/worldMonitor.ts` -- `MonitorVariant` includes `happy`

---

**Confirmed at**: 2026-09-29
