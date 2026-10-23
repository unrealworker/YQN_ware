# Order replay implementation

Approved: user requested replacement of the formal design and implementation on 2026-10-23.
Reference: `DesignPreviews/order-replay-20261023/proposal.md`.

## Constraints

- Work in the existing checkout because the current saved map contains accepted road and material changes absent from HEAD. Preserve all unrelated dirty files and manual equipment placements. Do not reset the live Blender scene.
- Test data stays explicitly labelled. Four fixed orders select the same complete replay dataset. Minimum elapsed duration is one hour, using Los Angeles civil time with explicit DST ambiguity handling.
- A single replay clock evaluates motion, forks, cargo ownership, truck loads, faults and blue route flow. Seeking does not incrementally simulate history. All pools and visible event windows are bounded.
- Replay hides and pauses original equipment, parking vehicles and traffic without deleting them. Restore precise pre-entry visibility, ticking, roof, selection and camera state on exit. Business inventory is never edited.
- Preserve repaired road ends and junctions. Use checked real-world routes and current warehouse assets; a web animation is not scene acceptance evidence.

## Ownership and interfaces

1. Design worker: formal `Design/GHS_Twin_SaaS_Concept/Saas.pen`, design documentation and exports only, with MCP backup and visual QA.
2. Web worker: `Content/GHSTwinUI/web/`, query/transport/exit state UI, overlay, tests. Existing visual tokens remain authoritative.
3. Scene worker: new `GHSOrderReplaySimulation` / `GHSOrderReplayActor`, motion tests, replay-only source/import assets and data. Explicit deterministic evaluate-at-time API; root owns clock and scene isolation.
4. Root: HUD/controller integration, camera, runtime isolation, native navigation guard, build and integrated verification.

Commands: replayStart(orderId,startUtc,endUtc), replayReady, replayPlay, replayPause, replaySeek(time), replayRate(rate), replaySelect(id), replayFollow(id), replayTrails(mode), replayOverview, replayEndRequest, replayExitConfirm, replayExitCancel, replayLeave(token,title).

Both panel and `replay-overlay.html` receive `window.twinReplayReceive(state)`. State includes active/preparing/playing/completed, time/duration/rate, interval/order, follow/selected IDs, trailMode, eight devices, bounded events/markers, test flag, error and exit dialog fields. Confirmed deferred web operations execute once through `window.twinReplayContinue(token)` after restoration. Native operations are deferred by the same guard.

## Implementation and checks

- [x] Replace and save formal trace artboards; inspect normal, error, replay, events, complete and exit states with latest scene imagery.
- [x] Build web query/index/replay states and timeline overlay. Tests cover 3599/3600 seconds, DST, arbitrary dates, all orders, native bridge, seek play-state retention, exit cancellation and continuation once.
- [x] Export checked real-map pickup/door/route constraints. Split forks and pallet layers. Implement five forklifts, three truck slots, cargo transfer, fault, depart/return/supply cycle and bounded events.
- [x] Test evaluator determinism at forward/backward seek, cargo uniqueness and loads, whole-cycle continuity, fault freeze, finite state and resource bounds.
- [x] Integrate independent replay actor; capture/restore original component states and selected floor instances. Keep replay objects outside the original scene identity index.
- [x] Render timeline in its own transparent scene-bottom browser. Route Home/middle click/navigation/search/live selection/presets through one exit guard; suppress original selection and POIs during replay.
- [x] Compile editor/game module and run targeted automation and production web checks.
- [x] Run real UE offscreen acceptance with captures for upper/lower pickup, carry, unload, full truck departure, fault, follow, seek and exit restoration; validate route envelopes and inspect logs and bounded frame costs.
- [x] Save final design and project assets, report evidence and any actual remaining limitations. Do not infer render success from build or prototype QA.
