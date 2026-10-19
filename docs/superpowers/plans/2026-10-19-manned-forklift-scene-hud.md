# Manned Forklift Scene and HUD Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans for the scoped tasks below.

**Goal:** Import the approved 49,813-triangle staffed forklift, distribute eight independent vehicles in the Normal warehouse floor-storage area, and implement its approved HUD design.

**Architecture:** Keep the existing shared truck/stacker screen HUD and add a third independent equipment type. Import one shared optimized static mesh with faithful material slots and LODs, then place independent static mesh actors with persistent identity tags. Validate against fresh live scene geometry and preserve unrelated actors.

**Tech Stack:** Unreal Engine 5.4, project C++/UMG, Unreal Python, Blender 5.2 source/FBX.

**Spec:** `Design/GHS_Warehouse_HUD/manual-forklift-design.md`; user's approved forklift and latest import/distribution request.

## Global Constraints

- Modify only `/Game/Maps/GHS_CAD_NormalWarehouse`; preserve blue warehouse and current equipment.
- Source LOD0 49,813 triangles; UE cleaned LOD0 49,661 triangles, dimensions 3.448268 x 1.249100 x 2.337000 m, scale 1.
- Actor tags `NormalWarehouseMannedForklift`, `TwinId=GHN_MannedForklift_01` through `08`; display IDs `FORK-01` through `08`.
- 34 px labels, 320 x 184 detail, 260 px list of at most 5 entries per page.
- Separate third-type aggregation, 10000 cm camera threshold, 120 ms local merge/split, 220 ms detail/list, existing bounded 40 px overlap policy.
- Placeholder telemetry must be marked as demo; offline/unknown values cannot masquerade as current data.
- Build with MSVC 14.38.33130; preserve live editor work before restart.

## Review Focus

- Old source manifest lacks updated worker materials: extract final Blender material values and preserve imported slots.
- Forks protrude beyond wheelbase: clearance checks include the whole mesh and both vehicle orientations.
- Merged warehouse walls/floor have huge bounds: use individual wall triangles and floor coverage, not merged AABB alone.
- Third equipment type must never join truck/stacker groups, and stale telemetry must clear on disconnect.
- New native component requires editor reload; no stale DLL or unsaved map overwrite.

## Task 1: Import and distribute (root)

- [x] Inspect live world, dirty state, all visible instance geometry and current vehicle tags; save timestamped backups.
- [x] Extract current optimized material manifest, import into `/Game/GHSNormalWarehouse/MannedForklift`, verify UE units, axes, LOD0 count and material slots.
- [x] Generate eight placements from current ground-storage cargo bounds, preserving 0.5 m near-work clearance and middle aisle traffic space; validate floor/wall/column/cargo/vehicle bounds.
- [x] Spawn independent static mesh actors, tagged persistently; compare all preexisting actor snapshots; save target map only.

## Task 2: Implement manual forklift HUD (HUD agent)

- [x] Add `GHSMannedForkliftDataComponent.h/.cpp`, with identity, load tonnes, speed km/h, driver, area, task, reason, update/connection time and explicit demo states.
- [x] Add `GHSMannedForkliftDataTests.cpp` for identity, valid and invalid updates, offline/fault clearing, initialization persistence.
- [x] Extend `GHSDockTruckHUDWidget.h/.cpp` discovery, counts, `GetMannedForkliftData`, reading, manual-driver icon, label metrics, details, selection and independent type aggregation.
- [x] Preserve truck/stacker APIs, animations and anchor policy; update documentation around actual supported behavior.

## Task 3: Integration verification (root with independent audit)

- [x] Save and close editor safely, compile TestEditor, inspect successful exit; run GHS automation.
- [x] Run owned offscreen game on saved map; verify 52 trucks, nine currently retained stackers and eight manual forklifts, distinct groups, selected manual details and demo/unknown behavior.
- [x] Capture close-up model-to-cargo proportions plus HUD and wide distribution/aggregation screenshots; inspect visually.
- [x] Reopen current map in editor and verify final actor transforms, shared assets and saved artifact existence.
