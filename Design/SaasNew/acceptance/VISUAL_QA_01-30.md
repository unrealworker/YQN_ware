# SaasNew Figma exported-board QA: 01–30

Reviewed the actual Figma PNG exports at 50% scale against current runtime screenshots on 2026-10-28. Contact sheets are `qa-sheet-01-04.png` through `qa-sheet-29-30.png`. The review itself did not modify Figma or production code.

## Blocking state consistency issues in first export

1. **04**: old scene labels and toast say `AGV-12 / 低电量`, while the actual sidebar is `STACKER-04 / 货叉举升异常`. The retained legacy top-level overlays caused the contradiction. The board's name also describes the old state.
2. **02**: actual sidebar selects `AGV-01`, but the scene retains unrelated legacy `CH-07`, `AGV-08` and selection marks without showing the selected AGV-01 at its true location. Requires the new selected-camera/POI capture.
3. **23**: current search input is x=1056, y=80, width=360. Its old result menu remained x=988, y=148, width=420, visibly left-aligned with the old input. Native layout requires x=1056, y=136, width=360 and 64-pixel result rows. Old three-result content also needs a current search capture.
4. **24**: roof is closed, but an old internal type filter remains partly behind the warehouse menu. Current NativePaint hides internal filters when the roof is closed.

These are addressed by a separate current-state cleanup module and new captures; this file records the first-export evidence and does not certify the subsequent import.

## Nonblocking findings and acceptance scope

- No obvious missing or solid-black icon appeared in the first 30 exports. Native header symbols, navigation icons, and statuses render.
- Rings on 01, 06, 17, 20 and 24 are complete and legible. Inventory bars, order line charts and device bars are present. There is no obvious clipping or duplicate chart geometry in the 50% exports.
- Earlier extra-line problems in numeric labels appear resolved: order totals, inventory usage and replay transport buttons stay on one line.
- Several long right sidebars end at the export boundary. Their retained vertical-scroll frames are expected to expose remaining content interactively; a static screenshot cannot prove scrolling acceptance.
- Legacy specification pages 07–09, 21–22, 27, 29–30 show no obvious layout overflow. Their examples may retain old scenario data by design; they should be labeled as specifications rather than current captured device state.
- Pages 25–28 render without clipped input rows or buttons. Their launcher/connection behavior was not re-run by this visual check.
- Pages 03 and 10 originally combined current model-monitoring sidebars with old aggregation popovers. Removing those popovers avoids false state, but the resulting pages no longer demonstrate an expanded aggregation. They need a real capture or truthful board renaming.

## Follow-up validation required

Re-export at least 02, 04, 23 and 24 after cleanup/current capture integration; verify 03 and 10 state naming. Confirm scroll interaction in Figma. Final selected POI anchors must match the exact camera screenshot used under them.
