# MPR reference-v3 shared props

Reconstructed against the supplied multiview reference, especially views 01, 04 and 06. These are visual assets, not surveyed botanical species or manufacturer vehicle drawings.

`manifest.json` is the import contract. It contains 11 instanced assets, three LODs each, per-LOD FBX paths, triangle counts, local metre bounds, material slots, and linear-RGBA material definitions with roughness and metallic values. `validation.json` records all 33 exported FBX readbacks; mesh bounds, triangle counts and material-slot counts match.

All assets have a ground-level local origin. Vehicles face +X, semi-trailer loading doors face -X. FBX export is -Y forward/Z up, consistent with the existing MPR CAD pipeline. Semi-trailers have no tractor cab. Trailer colour variants are white, blue and coral; cars are neutral white/grey; the railway vehicle is a white-grey boxcar approximately 20.8 m overall, including couplers.

| Asset | LOD0 / LOD1 / LOD2 triangles | Maximum XY radius | Height |
|---|---:|---:|---:|
| SM_MPR3_Tree_0 | 16492 / 2048 / 628 | 3.35 m | 8.8 m |
| SM_MPR3_Tree_1 | 16172 / 2048 / 628 | 2.75 m | 10.4 m |
| SM_MPR3_Tree_2 | 16812 / 2048 / 628 | 3.65 m | 7.6 m |
| SM_MPR3_Bush_0 | 5232 / 960 / 252 | 1.10 m | 1.35 m |
| SM_MPR3_Bush_1 | 5872 / 960 / 252 | 1.65 m | 1.9 m |
| SM_MPR3_Trailer_White/Blue/Coral | 7988 / 2208 / 624 | See bounds | See bounds |
| SM_MPR3_Car_0/1 | 964 / 584 / 262 | See bounds | See bounds |
| SM_MPR3_FreightBoxcar | 5272 / 1784 / 656 | See bounds | See bounds |

Foliage consists of a visible branching scaffold, many small opaque irregular micro-clumps, and rounded closed exterior leaf clusters. It has no transparent leaf cards, wind animation or per-asset tick. LOD1/LOD2 replace fine structure while retaining the same radial safety envelope. All copies should be instanced; collision is disabled in the import contract.

`MPR_Reference_Props.blend` retains the editable mesh and material source for every LOD. Source objects are hidden in the library to prevent all 33 coincident meshes rendering at once; select/unhide the required collection or link its LOD0 mesh data into the assembled scene. Presentation images are separate and do not change asset coordinates.

Review renders:

- `contact_sheet.png`: foliage and three trailer colours, rendered in Blender and assembled without generative image edits.
- `foliage_close.png`: final approved dense micro-cluster revision.
- `vehicles_close.png`: semi-trailers, neutral sedan and SUV.
- `rail_boxcar_close.png`: railway freight boxcar.

Rebuild using `D:\WinAPP\Blender\blender.exe --background --factory-startup --threads 1 --python D:/UEPro/Test/Tools/MPRWarehouse/build_mpr_reference_props.py`. The helper `mpr_reference_props_geometry.py` owns geometry only. Rebuilding does not launch UE or change the previous MPR/GHS assets. A complete render uses one Blender CPU thread; `-- --foliage-only` regenerates and validates all assets but renders only the foliage review.

No claim of UE in-scene appearance or runtime performance is made by this props-only validation; those are checked by the scene assembly task.
