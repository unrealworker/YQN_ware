# Logistics Warehouse Scene Implementation Plan

**Goal:** Create a separate realistic UE 5.4 logistics park map in the current project.
**Authorization:** User requested a new warehouse digital-twin scene and explicitly chose a generic logistics park with direct implementation.
**Architecture:** Blender generates detailed reusable meshes; UE Python imports PBR materials and assembles named actors with stable asset tags, lighting, roads and landscaping. Existing SpongeBob assets remain available.
**Tech Stack:** Blender 5.2, UE 5.4 Python editor scripting, Starter Content textures and foliage.

## Scope and design decisions
- Generic illustrative facility, not a surveyed replica; live telemetry integration is outside this scene-building request.
- Site 240 m x 180 m; main warehouse 96 m x 54 m with 10 docks and a separately selectable roof, office annex, racks and pallets.
- Truck apron, circulation roads, entry guardhouse, car parking, crossings, arrows, perimeter fence, trees and shrubs.
- Daylight, skylight, atmosphere, fog, Lumen, fixtures and modest practical lights. Surface detail and physically plausible dimensions prioritize realism.
- Export geometry in metres; UE uses centimetres. Blender front -Y imports as UE front +Y. Named mesh actors have stable `TwinId` tags.
- No Git repository exists. Work is done in the authorized project with an independently named map `/Game/Maps/LogisticsWarehouse`.

## Tasks
- [x] Generate architecture modules, dock details and warehouse rack assets.
- [x] Generate detailed tractor-trailer, forklift and pallet assets.
- [x] Generate natural branching trees with individual leaves; reuse Starter Content shrubs.
- [x] Import meshes and build reusable PBR materials using existing texture maps.
- [x] Assemble facility, roads, markers, landscaping and lights in the new map.
- [x] Reopen the saved map, verify required actors and bounds, check map errors, capture overview and eye-level views, review composition.

## Verification
Asset generator reports contain mesh bounds and slot assignments. UE reports validate map path, required categories, materials, actor count, independent roof, lighting and camera transforms. Rendered views are inspected for circulation clearances, missing materials, scale, ground contact and framing. A fresh reviewer checks implementation and reports. No synthetic real-time operational data is presented as live data.

## Final evidence
- Saved map: `Content/Maps/LogisticsWarehouse.umap`; 18 imported meshes, 56 custom materials, 1,165 actors, 10 docks, 64 racks, 92 trees.
- `Saved/Warehouse_SavedAssetVerification.json`: fresh UE process passed saved-material, upright-transform, registry and TwinId consistency checks.
- `Saved/Warehouse_Verification.json`: four actual UE captures completed; `Saved/Warehouse_UE_*.png` inspected.
- Latest editor map validation: 0 errors, 0 warnings. Initial import had nonfatal near-zero tangent warnings on five detailed meshes; final rendering was inspected.
- Reviewer findings addressed: rack shelf heights, dock truck offsets, curb openings, fire-road connection and container hardstand.
- Known scope: static illustrative park, no live telemetry or vehicle movement; detailed meshes have no full walking collision/navigation; foliage has no wind or LODs.
