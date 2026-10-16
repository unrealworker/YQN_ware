# CAD rack correction implementation plan

> For agentic workers: execute this plan with parallel evidence gathering and isolated Blender asset generation; the root agent owns UE integration and final verification.

**Goal:** Replace the generic four-level racks in both GHS scenes with CAD-specific rack structures, maintaining believable physical proportions.

**Architecture:** Resolve CAD elevation dimensions and main-plan rack classifications into traceable JSON. Generate reusable metre-scale Blender meshes. Apply shared geometry with independent blue and normal material overrides to both existing maps. Keep historical backups and verify saved maps in a fresh UE process.

**Tech Stack:** DXF/ezdxf, Python, Blender 5.2.2, FBX, UE 5.4 Python, HISM.

**Spec:** User's supplied CAD rack detail image (A four levels, B twelve, C five, D1 upper two, D2 five), original DXF, and explicit instruction to modify while respecting overall scene proportions. Both scenes must remain synchronized geometrically.

## Constraints and decisions

- Original DXF is the dimension authority. Distinguish clear building height, rack uprights, beam elevations, and cargo height.
- Keep measured CAD horizontal coordinates, warehouse footprint, clear aisles, and existing column clearances. No indiscriminate global scaling.
- Do not assume W_DOCK means a rack: check actual geometry and placement before replacing it.
- Preserve AGVs, charging equipment, green animated decals, lighting, and both scene palettes.
- Generate in a background Blender process: the user's live Blender contains an unrelated work product.
- Verify mapped types and pass-through variants from CAD colors, attributes, annotations, and geometry; document every remaining interpretation.
- Keep building height as an explicitly identified visualization assumption unless a drawing confirms it. Coordinate any necessary height correction with columns, wall geometry and outlines in both scenes.
- This folder is an existing UE asset workspace, not a Git checkout. Use file backups, asset hashes and change reports.

## Tasks

- [x] Extract five elevation families, exact beam heights, upright height, span, depth and pass-through variants into `SourceAssets/GHS/RackSpecs/cad_elevation_specs.json`; render CAD detail evidence.
- [x] Map main-plan rack instances and cross aisles to specifications in `SourceAssets/GHS/RackSpecs/cad_plan_mapping.json`. Resolve the existing Dock classification; account for every replaced CAD identity.
- [x] Review source specifications and mapping together. Resolve scale and building-height effects before geometry is applied.
- [x] Build editable Blender rack models and FBX under `SourceAssets/GHS/RackSpecs/Models/`; verify dimensions, layer counts, opening clearances, material slots and bounds.
- [x] Back up both saved maps, registries, related manifests and existing verification outputs. Import only new assets and assign independently styled materials.
- [x] Replace affected groups in both UE maps, preserving unrelated actor/component state and CAD coordinates. Update authoritative registries and rebuild integration.
- [x] Verify both maps after fresh load: every instance transform/type, shelf levels and world dimensions, collision/clearance, palette, actor identity, animated FX and non-target file hashes.
- [x] Render rack close-ups and warehouse overview in both palettes; visually inspect scale and occlusion. Update documentation with measured dimensions and remaining assumptions.

## Progress

- Initial audit: main racks all use a four-level 4.8 m mesh; the 87 objects labeled Dock use a four-level 2.8 m mesh. These are not CAD-elevation-derived.
- Parallel investigations started for CAD elevations and plan mapping. Blender model builder owns only new model files.
- Early evidence: elevation sheets contain CLEAR 30' notes; this is not yet accepted as upright height. Plan contains rack block attributes and ACI color distinctions; W_DOCK requires reclassification.
- Elevations now verified from 124 dimension entities and actual front-post geometry: A/B/D1 posts are 9.154 m; C/D2 posts are 9.144 m, with the C pass view retaining its drawn 9.154 m top. A/B/C/D2 named levels include the ground pallet. Five rendered source details visually reviewed.
- Plan mapping resolves 1,639 real placements: A 1,214; A pass 47; B 265; B pass 11; D1 102. C/D2 are available assets only. Twenty-two explicit cross-aisle rack instances supplement the previous 1,617 retained/split identities. `W_DOCK` contains 87 numbered loading doors, not storage racks.
- Building walls, columns and outlines are staged at 9.6 m as an explicit display-envelope assumption; door height 4.2 m is likewise estimated. CAD row positions, full-size pallets and prior column clearances are retained.
- Generated 33 rack meshes and one door mesh; fresh UE import report succeeded for all 34. The staged registry contains 43 HISM groups and 14,138 instances. Source-solid audit reports zero confirmed intersections and zero unresolved bounds overlaps, including open passage checks.
- Independent pre-apply review found no blocking transform/scope bug: unchanged groups and individuals match checkpoint, import dimensions/triangles match the manifest, and the two scene palettes remain independent. Both maps have now been applied and verified in a fresh UE process: `Saved/GHS_CADRackRevision.json` and `Saved/GHS_CADRackVerification.json` both report `success: true`. They contain 43 HISM groups and 14,138 instances each, with 252 blue-map actors and 254 normal-map actors. All 33 rack meshes have four LODs; narrow segments without cargo keep their four actually used material slots, and cargo-bearing meshes keep seven. Historical reports remain untouched. Final captures remain in progress under the root integration task.
- Added maintenance guards to legacy scene/presentation builders and lazy routing from three legacy verification entrypoints to `verify_cad_rack_revision.run()`. Incomplete revisions fail closed and historical Saved reports are not overwritten by those wrappers. Updated GHS, Normal, Presentation and RackSpecs documentation; static validation only for these maintenance edits.
- Completed fresh UE verification through both the new checker and the normal-scene compatibility entrypoint: exit 0, zero errors/warnings, both saved maps and all unrelated actor states verified. Two independent material palettes, 40 animated Decals per scene and all 659 pre-existing non-map assets remain unchanged.
- Rendered and visually inspected 12 final 1920x1080 views across both styles: overall proportions, aisle framing, A four levels, B twelve levels, cross-aisle opening and D1 upper two levels. Moved only the temporary D1 inspection camera into the staging aisle to remove foreground occlusion and recaptured both styles. No capture saved a map. Latest camera/image provenance is consolidated in `Saved/GHS_CADRackVisualReview.json`; comparison preview is `Saved/GHS_CADRack_Comparison.png`.
