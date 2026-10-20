# GHS Zcool Smart Factory implementation plan

**Goal:** Deliver the requested separate UE scene with reference styling and original interaction functionality.
**Architecture:** Clone latest saved map and apply component-level material overrides in an independent asset directory. Preserve shared original code paths and original HUD. User explicitly deferred management panels.
**Tech stack:** UE 5.4.4 C++, Slate/UMG, UE Python; MSVC 14.38.33130.
**Spec:** ../specs/2026-10-20-zcool-smart-factory.md

- [x] Clone/material task: `Scripts/ghs/build_zcool_smart_factory.py`; create new map/materials, clone procedural FX, preserve geometry/transforms/attachments; record before/after inventories and original hashes. Saved and reloaded successfully; original 787 Content files unchanged.
- [x] UI scope removed at user request: no new management panels, header or sidebar. Original HUD stays unchanged.
- [x] Validation task: Editor build passed; 55 GHS automation tests, 10 runtime acceptance checks, and WarehouseRuntime.MapDrag with 20 camera configurations passed. Generated 5 runtime captures; visually inspected 3 runtime and all 4 scene captures. Fresh editor reopen passed and new map is left open. Usage recorded in `docs/GHS_ZcoolSmartFactory.md`.

Review focus: map-name HUD activation; original forklift mesh discovery; duplicated stacker IDs; saved lighting and instanced material appearance; original scene/assets unchanged.

Execution: work in the current asset-bearing checkout, independent file ownership for parallel scene and UI tasks; root coordinates UE launches/build and verification. No concurrent UE writes. No commits or default map changes required.
