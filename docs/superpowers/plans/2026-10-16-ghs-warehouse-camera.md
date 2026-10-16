# GHS Warehouse Camera Implementation Plan

> **For agentic workers:** Use executing-plans for the integrated runtime implementation. Read-only audits and independent validation may run in parallel.

**Goal:** Use UniversalCameraPlugin to give the Normal warehouse a polished mouse-operated overview Pawn matching the user's reference.

**Architecture:** Derive a native Pawn from AUniversalCamera and expose a Blueprint child for editing. Start at the CAD warehouse center with Z=0, pan the actual Pawn in XY using the plugin location setter and restrictions, orbit around that moved Pawn, and zoom the spring arm. Both SpringArm offsets stay zero. Native plugin lag drives all three motions, with a minimal subclass Roll=0 correction after native quaternion interpolation. A scene-specific controller handles raw mouse deltas and capture/release, and a scene-specific GameMode selects the Pawn.

**Tech Stack:** Unreal Engine 5.4 C++, UniversalCameraPlugin 2.18, editor Python for Blueprint/map setup and independent verification.

**Spec:** User request and follow-up in this chat: prioritize Plugins/UniversalCameraPlugin functions; reference overview; left-drag orbit with corrected Y direction; wheel zoom; right-drag ground-plane movement; actual Pawn and rotation center follow movement with Z always zero; Home reset. Apply to GHS_CAD_NormalWarehouse. Double only the cargo-box length of the current independent loading trucks.

## Global Constraints

- Preserve current scene objects, materials, light setup, all 24 stacker effects, and other maps.
- Derive from the plugin and reuse its spring arm, desired state, lag and bounds. Startup validation exposed three uninitialized FTargetSettings pointers; initialize only these to nullptr, with the original header backed up.
- Center (-646.665,833.981,0) cm; initial yaw -90, pitch -30, distance 53500 cm, FOV 56 degrees.
- Zoom 900..95000 cm; pitch -80..-15 degrees; no roll. Every parameter remains editable in the Pawn Blueprint.
- Pixel-based orbit has no DeltaTime multiplier. Wheel has proportional steps. Pan speed follows rendered distance/FOV/viewport width.
- Avoid underground camera positions and keep the warehouse recoverable via Home.

## Review Focus

- Losing focus or releasing outside the viewport must stop dragging, with no stuck cursor.
- Simultaneous mouse buttons must not mix orbit and pan; first held button wins until released.
- A simple click and tiny jitter must not rotate/pan the view.
- Zero-sized viewport, very large/invalid input, repeated wheel input and extreme pitch must remain finite and bounded.
- Startup possession and actual game camera must use the new Pawn even if Play is invoked from an arbitrary editor camera.

## Tasks

- [x] Add verification first and demonstrate failures before implementing the camera and its ground-plane revision.
- [x] Implement Source/Test/GHSWarehouseCameraPawn.{h,cpp}, GHSWarehousePlayerController.{h,cpp}, GHSWarehouseGameMode.{h,cpp}; add plugin/UMG dependencies and enable the installed plugin.
- [x] Preserve live editor work, rebuild the editor module, update and save camera Blueprint defaults and the placed Pawn.
- [x] Build a 12m cargo-box truck from the 6m source in Blender. Keep rear origin and existing independent placements; move cab/front axle without stretching their geometry. Import a new scoped mesh and preserve current per-role materials on all 52 trucks.
- [x] Verify saved Normal map in a fresh process: 22 checks passed, 264 total actors, all 211 unrelated actors unchanged, 52 trucks preserve placements/materials and have no pairwise overlap. Content writes restricted to Normal map, camera Pawn Blueprint, and new truck mesh.
- [x] Pass all five native input/composition tests, including actual Tick checks for Z=0 and Roll=0.
- [x] Verify actual standalone game movement/orbit/zoom/reset over 2416 monitored frames. Pawn Z deviation was 0; maximum Roll was numerical roundoff (1.73e-14 degrees). Capture and inspect overview and close truck views.

Evidence is indexed in docs/GHS_WarehouseCamera.md. Backups are indexed by Saved/GHS_WarehouseCameraGroundRevision.json.

No commits are required for this local UE task; keep scoped backups and JSON verification reports.
