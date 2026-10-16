# GHS CAD Digital Twin Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent model assets and native execution for CAD/layout integration. Track completed work here.

**Goal:** Build a separate UE warehouse level from the supplied DXF while preserving the approved blue digital twin style and adding two reference-modeled equipment assets.

**Architecture:** Parse DXF into a traced layout manifest in metres, with original coordinates and handles retained. Reuse existing UE materials and meshes, generate reference-specific Blender assets, then populate and verify a separate map.

**Tech Stack:** UE 5.4 Python, Blender 5.2 background Python, DXF parsing, Pillow.

**Spec:** `docs/superpowers/specs/2026-10-15-cad-ghs-digital-twin.md`.

## Global Constraints
- Preserve `/Game/Maps/VideoDigitalTwinWarehouse` and its current materials.
- New map `/Game/Maps/GHS_CAD_DigitalTwin`; new assets `/Game/GHSDigitalTwin`; source `SourceAssets/GHS`.
- DXF defines XY layout and measured scale. Record assumptions for missing heights/details.
- No modeled geometry for AGV scan/diffusion effects. Reuse Time-driven decals.
- Blender workers own separate scripts/output stems; only root controls live UE/Blender.

## Review Focus
- Drawing units vs annotation dimensions; exclude paper-space/title-block geometry.
- Nested block transforms and large global coordinates; check reference points after recentering.
- CAD classification of walls/racks/equipment; do not infer a generic layout when source is available.
- Imported FBX axis/unit conversions, slot names, reference silhouette, cable visibility.
- Independent map save/reload, original level preservation, runtime animation/attachment.

## Tasks and interfaces
- [x] Task 1: `Scripts/ghs/inspect_dxf.py` extracts layers, nested geometry, dimensions, text, placements, bounds and CAD preview; `SourceAssets/GHS/cad_layout.json` uses metres relative to explicit origin.
- [x] Task 2: `Scripts/ghs/build_kuka_agv.py` creates `kuka_agv.blend/json` and `SM_GHS_KukaLowProfileAGV.fbx`. JSON follows `video_reference/common.py` mesh/material schema. Validate silhouette/bounds and render Blender preview.
- [x] Task 3: `Scripts/ghs/build_charger.py` creates `charger.blend/json` and `SM_GHS_WallCharger.fbx` using the same schema. Validate wall mounting, red rails, black casing, cables and plug; render preview.
- [x] Task 4: root creates any CAD-specific architecture with reusable thick wall cross-section; import new meshes to GHS asset directory, compose mapped warehouse using preserved material assets and cloned environment.
- [x] Task 5: save, capture UE overall and close-up images, independently reload and compare layout to CAD manifest, compile applicable assets and inspect any failures.
- [x] Task 6: record source assumptions, usage, outcome, and style memory requested by the user.

## Progress / rulings
- 2026-10-15: Workspace is an existing non-Git UE project. Isolation is through a new map and asset namespace, not a Git worktree.
- 2026-10-15: Source DXF is 32.3 MB, AC1027, declares ANSI_936, uses large site coordinates. Must inspect geometry before assuming extents/header represent the complete intended floorplan.
- 2026-10-15: Supplied screenshots establish asset appearance; exact equipment dimensions will be sought in CAD, otherwise clearly documented estimates.

- 2026-10-15: Built and saved independent GHS level. Fresh UE verification checks all 14079 instance transforms, original-map SHA, 40 animated decals, 14 persisted local material copies and final LOD repairs. GHS Blueprint compilation passed. See Saved/GHS_Verification.json and SourceAssets/GHS/README.md.
