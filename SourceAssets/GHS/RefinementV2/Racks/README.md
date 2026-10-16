# Refined CAD rack cargo V2

These assets replace the tall single-crate load envelopes with separate, fixed-size cartons. The authoritative CAD frame, pallet footprint, floor-centred origin, mapping keys, and seven material roles are preserved.

- Carton size: 0.45 × 0.55 m, height 0.36–0.42 m. No nonuniform carton scaling.
- B: one carton layer per pallet. A/D1: three or four layers. C/D2: three layers.
- Four cartons per layer, 20 mm horizontal gaps and a small alternating offset within the pallet footprint.
- Cartons contact the layer below; 4 mm bevels reveal their seams without artificial vertical air gaps.
- Original pallets remain 1.016 × 1.2192 × 0.123952 m with separate runners, spacer blocks and deck boards.
- Material slot order: Upright, Beam, Braces, Pallet, Cargo, CargoEdges, Detail.

`refined_rack_cargo.json` is the integration manifest. Each mesh has `name`, `replaces_mesh`, `mapping_key`, `fbx`, `fbx_sha256`/`sha`, `bounds_m`/`bounds`, `triangles`, `solid_boxes`, and detailed `cargo_stacks` including carton dimensions, layer count and overhead clearance. Its verification summary records unchanged CAD frames and pallets.

`refined_rack_cargo.blend` retains separate editable objects organized into one collection per rack. FBX files each contain one joined static mesh in metres, Z up, X across the rack and Y through its depth, using the original -Y forward FBX conversion. Import with the same unit conversion as the original CAD rack library; do not stretch actors to change cargo proportions.

The two `*_carton_closeup.png` images show low shelves of A and B, and `v2_rack_library_preview.png` compares the five canonical rack types at equal scale. The narrow empty variants remain only for compatibility; the revised layout uses complete wide bays.

To rebuild from the project root in PowerShell:

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --factory-startup --python 'Scripts/ghs/build_refined_rack_cargo.py' -- --preview
& 'D:/WinAPP/Blender/blender.exe' --background --factory-startup --python 'SourceAssets/GHS/RefinementV2/Racks/validate_fbx_roundtrip.py'
```

The second command reads every exported FBX into a separate background Blender and writes `fbx_roundtrip_validation.json`, checking the file hashes, dimensions, origin, orientation, material slots and triangle counts. Neither command uses the interactive Blender session or changes original source assets.
