# Independent roof / traffic / context review

Reviewed against baseline `3306248`, the supplied plan/review package, current source, generation scripts, and generated route data. This is a source/spec review; existing tests were not rerun and no UE runtime or packaged-game success is claimed here.

## Verdict

- **Spec compliance:** Roof/HUD state and interaction contracts are represented coherently: initially closed; click hides main POI and starts one 0.5s transition; scene picking, interior labels, and selection projection are gated; latest interior navigation waits for opening; overview/reset clears pending navigation and restores exact source material references. Traffic has four corridors, six directions, fixed 16 slots, bounded retirement/reuse, no physics/navigation/business identity. Context scripts implement the requested 18% guarded exterior softening, 65m road tails and sparse islands. **Source/spec review passes after the scoped P2 fix below; final runtime verification remains parent-owned.**
- **Quality:** Focused implementation and suitable lifecycle ownership overall. Hard references cover the new roof variants and car meshes; `Source/Test/Test.Build.cs:17` already stages the JSON data directory. No separate packaging blocker found by inspection. **No outstanding important findings after re-review.**

## Important finding

**[P2] Separate or arbitrate the two Sycamore routes at their shared southern endpoint — ADDRESSED.**

Scoped re-review of `Saved/RoofTraffic/review-fix-package.txt`, current `traffic_routes.py`, and both current JSON files confirms that the active routes now stop/start on their respective original carriageways before the shared terminal join. The new filter at `Scripts/ghs/traffic_routes.py:94-103` excludes every extension sample and the last/first 18m of each original path at that join. Actual sampled clearances are 19.1197m / 19.0m. Both routes remain continuous and exceed 500m, so the unchanged runtime length validation, interpolation and fixed-capacity lifecycle remain valid.

Fresh data inspection confirms all six staged runtime point arrays exactly match the source arrays rounded to millimetres. Sycamore now contains 174 / 169 points and lengths 518.9808m / 503.9771m. The road records retain their 65m visual extensions. The supplied geometry receipt records 8.6196m clearance between conservative 15m x 3m truck envelopes and zero footprint overlap. The new regression checks the conflict previously missed by same-route headway validation. No tests were rerun in this re-review, and no new breakage was found within the scoped change.

Original finding evidence (historical, before the fix):

- Location: `Scripts/ghs/traffic_routes.py:58-60` and `:78-94`; runtime exclusion at `Source/Test/GHSCampusTrafficSimulation.h:89`.
- Both original Sycamore centre lines meet at UV `(92.9018770782, 473.3576705150)`. Extending southbound past that end and northbound before that start turned the shared original endpoint into an interior crossing of the two active routes. The pre-fix generated routes crossed at Z `0.04m`, with headings approximately `11.91deg` and `-122.90deg`. It was 538.0947m along southbound (46.8803m before retirement), and 47.0m along northbound.
- Concrete scenario: a southbound truck reaches 538.09m while a newly spawned northbound car reaches 47m. Both remain active and their centre positions coincide. The simulator excludes every vehicle whose `Route` differs, so neither yields; zero-collision components make the visible models pass through each other. Random spawn timing makes this recur over long sessions even though same-route headway and capacity checks pass.
- Suggested fix: keep the two lane corridors physically separate through the tail, or terminate the active route footprints before the shared junction, or introduce a deterministic shared conflict-zone reservation. Recheck whole vehicle footprints, including the 15m truck, and regenerate both runtime JSON and any context tails affected by the chosen geometry.

## Additional checks / limits

- Fresh numerical inspection of the generated data found the Sycamore north ends 35.71m / 37.27m from the Glen Helen centreline, so the reported crossing is the **southern** shared endpoint, not the northern Glen junction.
- Highway tyre contact samples differ from the corresponding piecewise-linear road heights by 0.02397-0.02607m, consistent with the intended 0.025m clearance. Highway/Sycamore intersections retain grade separation.
- Roof template/mesh cooking is supported by constructor hard references and reflected properties; context meshes/materials are map referenced. Full cook/run verification and visual dissolution quality remain parent-owned evidence.
- No source edits were made during this review; this report is the only written artifact.

## Final scoped HUD follow-up

**PASS — no new findings.** Reviewed `Saved/RoofTraffic/hud-final-review.patch` and the current source. `Overview()` now clears visible/prior labels, positions and age caches synchronously after restoring the roof (`GHSTwinHUDWidget.cpp:471-474`). `GetPOIReport()` gates cached internal items directly on the roof state (`:791`); selection bounds and both internal label paint passes independently use that same gate (`:862`, `:892`, `:903`). Thus neither painting nor diagnostics relies on a later `NativeTick` to suppress old interior labels. The main POI report also checks closed state, and its cleared placement cache is rebuilt normally on the next tick. No array copies or new per-label roof queries were introduced.

The added `restore()` assertion at `Scripts/ghs/verify_roof_traffic_runtime.py:63` checks the immediate post-command report before yielding, then separately waits for the restored main POI. This matches the specific ordering defect. The source/spec verdict remains pass; no tests or runtime checks were rerun by this reviewer.
