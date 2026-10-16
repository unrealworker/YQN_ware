# GHS CAD rack library

This library replaces the former generic four-level rack geometry with the
five elevation types in the supplied GHS DXF. Dimensions are metres in Blender;
the FBX uses the project's existing `-Y` forward / `Z` up export convention.
Each exported mesh has its origin centred on the floor and should be placed at
unit scale. The editable `.blend` separates each asset into a named collection
and arranges those collections on a comparison board after export.

| Type | Storage positions vertically | Load beam tops in metres |
|---|---|---|
| A | Ground + 3 upper levels | 2.3114, 4.6228, 6.9342 |
| B | Ground + 11 upper levels | 0.7502, then increments of 0.762 through 8.3702 |
| C | Ground + 4 upper levels | 1.8542, 3.7084, 5.5626, 7.4168 |
| D1 | 2 upper levels; open below | 4.6228, 6.9342 |
| D2 | Ground + 4 upper levels | 1.8542, 3.7084, 5.5626, 7.4168 |

The A/B/C pass variants retain only the upper levels shown in the CAD detail.
Column height is 9.154 m for A/B/D1 and 9.144 m for C/D2; the C pass detail
measures 9.154 m. The 10 mm difference is present in the drawing geometry and
is retained rather than concealed with an arbitrary global scale.

Standard frame width is 3.81 m including two 76.2 mm upright sections. Frame
depth is 1.0668 m, except type C at 1.524 m. Loads are 1.016 m wide and 1.2192 m
deep, so the 42-inch frames correctly retain 76.2 mm of pallet overhang at each
end. A load's stated CAD height includes its pallet. The pallet is 123.952 mm
high, with 15.875 mm deck thickness and 38.1 mm runners, measured from the CAD
load blocks.

Actual scene spans also include variants trimmed by the earlier clearance
correction. These are rebuilt at their actual span: the upright cross-section,
load dimensions and vertical levels remain fixed. A narrower bay holds fewer
whole loads. The 0.8169 m remnants contain the frame only. They are not scaled
copies of a full three-load bay.

All meshes expose seven named material roles in a fixed order: `Upright`,
`Beam`, `Braces`, `Pallet`, `Cargo`, `CargoEdges`, `Detail`. They correspond to
physical pieces, so both warehouse styles can assign their own materials
without a world-height band shader. Cargo is closed packaging with restrained
seams, rather than open bins. Profile skin thickness, brace gauge, perforations
and seam styling are visual modelling details, not engineering specifications.

`cad_rack_models.json` records the input file hashes, actual exported bounds,
material roles, beam levels, storage bases, triangulation and conservative
local-space solid boxes. `mapping_key` is `type:pass_flag:span_to_4_decimals`.
Types included only in the CAD legend are available in the library but must
not be inserted into a scene without corresponding plan entities.

Current main-plan placement uses 1,639 rack instances: 1,214 A, 47 A pass,
265 B, 11 B pass and 102 D1. Types C/D2 remain catalogue assets only because
no unambiguous current-plan placement was found. The 87 `W_DOCK` symbols
are loading doors with `DOCK_NO.` attributes, not D1/D2 racks.
Building walls, columns and outlines use a synchronized 9.6 m display
envelope; loading doors use an estimated 4.2 m height. Neither value is a
surveyed building elevation. See `../README.md` for revision state, backups,
saved-map verification and guarded legacy entrypoints.

Rebuild using `Scripts/ghs/build_cad_rack_models.py` in a separate background
Blender process with `--specs` pointing to `cad_elevation_specs.json`,
`--mapping` to `cad_plan_mapping.json`, and optionally `--preview`.
