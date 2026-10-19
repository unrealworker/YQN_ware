# Stable truck HUD clustering and motion

**Goal:** Replace label avoidance that jumps between offsets with stable aggregation, and animate aggregation and detail transitions in the existing NormalWarehouse HUD.

**Architecture:** A deterministic screen-space clusterer consumes projected truck identities and natural label footprints. A persistent UMG visual state animates group membership changes independently of camera projection; a compact member picker gives access to every grouped truck. Existing telemetry and camera behavior remain the integration foundation.

**Tech stack:** UE 5.4 C++ / Slate / UMG, existing project fonts, Pencil MCP.

## Design decisions

- Cluster footprints at a 6 px gap; retain existing relations through another 32 px of separation. Require a candidate partition to persist for 0.20 s before commit. Sorted truck IDs determine identity, never camera-distance rank.
- Single labels keep their content width and height 34. Groups are 184×34 with truck icon, count and expand affordance. No greedy alternate offsets and no arbitrary 4/8-vehicle truncation.
- Merge/split visuals interpolate their current position, dimensions and alpha for 0.28 s. New children emerge from the prior group; disappearing children converge on the new group. Camera follow uses frame-rate-independent smoothing.
- Clicking a group opens a 260 px member picker: header 34, five 32 px rows, footer 28 with paging. Select any row to close the picker and open that truck's existing 320×184 detail. Clicking outside dismisses the picker and passes through to camera input.
- Detail/picker open and close use reversible 0.22 s ease-out transitions, opacity, slight scale and vertical movement. Hit areas use the same animated bounds as rendering. Selection and detail placement do not change cluster topology. Placement side is chosen once per opening, then follows smoothly and clamps to the viewport.
- Preserve unknown/offline/demo data semantics, registered actors and current camera edits. Do not save test telemetry into the map.

## Work

- [x] Add clusterer behavior tests for shuffled input, hysteresis/dwell, splitting, removal, invalid coordinates, edge clamping and dense membership conservation; implement the clusterer.
- [x] Replace widget avoidance with persistent animated groups; implement member paging and reversible detail/list animation; keep existing Blueprint identity/data access.
- [x] Add a Pencil interaction board with compact group, member picker and motion notes.
- [x] Build using MSVC 14.38.33130; run all GHS automation tests and owned game validation at 1920×1080 and 960×540. Capture merge/split/detail intermediate frames as visual evidence.
- [x] Review click geometry, interrupted transitions, invalid actors and popup disappearance; restore the editor and document actual results.

## Review focus

Camera jitter at a grouping boundary; membership changes while the picker is open; selecting a nonfirst member after paging; reversing close while opening; animation and clipping at viewport edges/small windows.

## Verification evidence

- Actual Unreal build succeeded. `Saved/Automation/TruckHUDClustering/index.json`: 20 passed, zero failed.
- `Saved/GHS_TruckHUD_Clustering_{Full,Small}.json`: 21 runtime checks passed at each resolution, including actual button clicks and interrupted animation reversals.
- `Saved/GHS_TruckHUD_Runtime_{Full,Small}.json`: existing telemetry regressions passed, 19 and 20 checks respectively.
- Reviewed actual early/intermediate/final screenshots for lists, details, merge and split. Fixed rounded box draw tint so fill and outline fade together, and replaced unavailable pager glyphs with vector arrows.
- Read-only review identified the singleton minus-label toggle; observed its real-game failure before fixing, then passed the expanded regression. Baseline reports retained in `Saved/TruckHUDClustering/`.
- Pencil fourth board exported and source saved through the File menu; existing three boards preserved.
