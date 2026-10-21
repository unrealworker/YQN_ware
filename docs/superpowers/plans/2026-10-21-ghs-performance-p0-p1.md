# GHS performance P0/P1 implementation plan

> Agent workflow: coordinated implementation with independent review and verification-before-completion.

**Goal:** Improve the current Zcool warehouse's 1080p frame stability and CPU/UI efficiency while preserving its visual design and interactions.

**Architecture:** Keep native Slate/UMG HUD and CEF business pages. Build an opt-in native performance route usable in packaged Development builds. Cache stable scene discovery, amortize storage validation, separate POI candidate work from frame-by-frame projection, and avoid unnecessary page construction/data delivery.

**Spec:** User-approved P0/P1 proposal in this conversation. Target Windows local or future Pixel Streaming, 1920x1080 stable 60fps. Pixel Streaming integration and P2/P3 visual reductions are outside this implementation.

## Global constraints

- UE 5.4, MSVC 14.38.33130. Use the existing current checkout on codex/performance-p0-p1 so the user's project and asset paths remain valid.
- Preserve pre-existing Config/DefaultEngine.ini modification, all maps/assets and source identity, actual CAD matching, nearest cargo selection, dynamically added/removed/copied devices.
- Preserve 320ms page transitions, 420ms reversible panel slide, 60Hz browser rendering and moving POI projection, camera flights, Home/overview clear selection, search focus and scroll.
- Baseline must be frozen before modifying production implementation. Performance route/instrumentation is identical before and after.
- Compare identical packaged Development resolution, rendering settings, route, timing and assets. Measure both CPU/GPU timings and frame spikes, do not infer performance from functionality tests.
- Explicit perf/diagnostic switches only; no benchmark runs during normal usage.
- Do not modify scene quality to claim a P1 performance gain. Keep recovery/full-sync paths for stale UI and changed scene identities.

## Tasks and ownership

1. P0: GHSTwinPerformance.cpp/.h, Test.cpp, Scripts/ghs/perf_* (integration agent). Add opt-in deterministic route, CSV/trace metadata and summaries; build/cook/stage baseline; run and inspect fresh captures before code optimization.
2. Scene data: GHSTwinSceneData.cpp/.h and dedicated tests (runtime_scene_audit). Cache registered candidates and amortize storage checks; preserve mutations and identities. Add behavior regressions before implementing changes; root runs UE compile/tests.
3. Web pages: Content/GHSTwinUI/web JS and dedicated tests (twin_frontend). Cache normalized data and per-page dependencies, hide/resume latest snapshot, diagnostic reporting switch; preserve navigation/selection. Test against real DOM or existing runtime harness.
4. Native HUD: GHSTwinHUDWidget.cpp/.h and dedicated tests (twin_frontend). Avoid repeated layout/geometry allocations, cache POI candidate selection without reducing projection smoothness, gate hidden browser snapshot work, cache brush/font/icon geometry when justified.
5. Integrate, build/cook/stage optimized Development, run identical route; run full UE automation and existing panel/revision runtime acceptance. Capture 1080p and narrow viewport results; run sustained soak and review profiling evidence.
6. Independent code/spec review of the complete diff, fix material findings, record measured gains and limits and restore editor state.

## Shared interfaces

- SceneData retains Refresh/Points/SnapshotJson/Resolve/Pick public semantics. Any new cadence or serialization API is coordinated with root before edits.
- Native-to-web visibility hook and diagnostics flag must be explicit; initial full snapshot and recovery on ready/reopen remain supported.
- Perf route uses existing native command APIs; no test-only production shortcuts or modified normal time step.

## Review focus

- Device spawn/destruction, duplicate copied IDs, component additions and same-count instance movement.
- Rapid selection/clear/selection while snapshot update or page animation is pending.
- Reopening collapsed panel receives latest data without losing active page or geometry stability.
- Fast camera rotation keeps visible label projection and selection precise; density and filters remain correct.
- Expensive full cache validation is bounded per frame and never publishes a partially rebuilt semantic index.
- Benchmark captures are uncontaminated by another running UE, heavy build/cook work, debug reporting or changed resolution/quality.

## Progress

- Baseline source/assets frozen before P1 changes in Saved/PerformanceP0P1/BaselineProject; manifest records source commit and map hashes.
- User editor state recorded and clean editor closed normally. Latest state is editor_state_latest.json (original NormalWarehouse, 248 actors); no assets saved.
- Windows Smart App Control initially blocked generated rules DLLs. User disabled it; current build proceeds. No security settings changed by the agent.
- Packaging blocker found in UE TargetDescriptor: Test is parsed as a build configuration, leaving no target name. Renamed Game target to TestGame and selected it in packaging settings; project/module stay Test. Both Game/Editor pin installed MSVC 14.38.33130. Identical build fixes applied to baseline.
- Baseline and optimized Editor builds and Development Game build/cook/stage/archive passed (ExitCode 0). Optimized packaging succeeded without an explicit target override.
- P1 native/web changes passed independent review. UE automation: 80 passed, zero warnings/failures. Web: 44 passed. Python analyzer: 9 passed.
- Real UE/CEF cache acceptance passed 4 checks; panel acceptance passed 22 checks; Revision8 acceptance passed 42 checks. Actual 1080p and narrow-layout screenshots inspected.
- P0 end-frame exclusion and run metadata review findings were fixed before all six comparable version 2 captures. Baseline and optimized drivers have identical SHA-256.
- Three runs per variant completed. Median GT mean improved 23.5%, GT P99 improved 26.9%; aggregate >33.33ms frames fell from 9 to 1. Total frame mean/P99 and GPU timings did not improve; stable 60fps is not established. See docs/performance/2026-10-21-p0-p1.md and Saved/PerformanceP0P1/matrix_summary.json.
- User requested stopping at this version. The 30-minute soak was explicitly cancelled by terminating only its verified owned TestGame process. Its incomplete capture is excluded; no long-term memory/stability claim is made. No further optimization is scheduled.
- Editor restored at 11:34:27 local to the user's original NormalWarehouse and recorded view, 248 actors, selection empty. Both map hashes unchanged; no assets saved. Fresh editor_restored.json confirms success and the editor remains open.
- Ruling: use current checkout on isolated branch because user requests changes to the current live UE project; map paths, existing uncommitted config, and editor state must remain intact. No worktree duplication or merge is required.
- Ruling: implementation split across existing agents with explicit file ownership; root owns coordinated build/runtime operations to avoid races.
