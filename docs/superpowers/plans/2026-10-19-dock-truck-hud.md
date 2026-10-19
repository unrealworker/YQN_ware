# Dock truck HUD implementation plan

**Goal:** Implement the approved loading-truck Pencil HUD in GHS_CAD_NormalWarehouse.
**Architecture:** The existing local player controller owns a native UMG overlay. Runtime data components on tagged independent dock trucks expose Blueprint data updates. The overlay projects vehicle anchors into the viewport, limits and separates visible labels, and opens one detail card on click.
**Tech stack:** Unreal Engine 5.4 C++, UMG, Slate; existing warehouse camera unchanged in its controls.
**Spec:** `Design/GHS_Warehouse_HUD/README.md`, truck compact/detail PNG exports.

## Constraints and decisions

- Work in the user's current project so the running editor and current assets remain the integration target. Preserve existing user files and back up touched files/assets before integration.
- Scope is the NormalWarehouse map and actors tagged `IndependentDockTruck`; identities come from `TwinId=` and `Dock=` tags, not editor-only labels.
- Default business values are unknown (`--`, 待接入). Explicit demo telemetry is marked 演示数据. Do not imply live connectivity.
- Keep Chinese text and values as live UI text. Import a project-owned Chinese font for packaged runtime, not a Windows-font-only dependency.
- Labels behind the camera/outside the viewport are hidden. Cap nearby visible labels and avoid collisions. Keep the selected detail card in the viewport.
- HUD clicks must not orbit the camera. Clicking or dragging outside HUD preserves existing left-orbit, right-pan and wheel behavior.
- A destroyed truck, travel, narrow viewport, invalid counts and offline state must fail safely.

## Tasks

- [x] Add and verify runtime telemetry component: identity parsing, update validation, unknown/offline display semantics; automation tests cover invalid counts and transitions.
- [x] Implement UMG overlay and integrate controller lifecycle; render silver/blue labels, anchored lines, selected detail and status variants, with selectable and bounded layout.
- [x] Build editor target; run GHS automation including existing camera tests; run standalone scene verification at two viewport sizes and capture the actual HUD. Save any project asset changes through UE, and document usage/data binding.

## Verification record

- UE 5.4 TestEditor Win64 Development built successfully with MSVC 14.38.33130.
- `Saved/Automation/TruckHUD/index.json`: 12 succeeded, 0 failed, 0 warnings; six truck data tests plus the current camera tests. Tests were authored before the data component, but no pre-implementation RED execution was performed.
- `Saved/GHS_TruckHUD_Runtime_Full.json` and `..._Small.json`: success, 52 actual tagged trucks registered; defaults, selection, pointer hit logic, 18/24 demo progress, offline clearing, restored telemetry and layout bounds checked.
- Inspected fresh full and small viewport screenshots, including readable Chinese and explicit demo provenance. Small viewports use a minimum physical scale to avoid the default UMG half-size text.
- Native mouse verification in PIE: clicked a label to open, clicked close, confirmed camera rotation unchanged on HUD click, dragged blank scene to orbit and retained pawn Z=0. Evidence: `Saved/TruckHUD/InteractiveVerification.json` and before/after snapshots.
- The user's previously dirty `BP_GHS_WarehouseCamera` was backed up under `Saved/Backups/GHS_TruckHUD_20261019` and saved through UE before rebuilding. No map changes were needed. Concurrent camera source changes were preserved.
- No live business feed or packaged executable was requested or verified; Blueprint telemetry API and font/license staging are supplied. See `docs/GHS_DockTruckHUD.md`.
