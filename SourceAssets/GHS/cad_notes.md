# GHS CAD extraction notes

Source: D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf. AC1027. Modelspace only. The file declares ANSI_936 but the actual text is UTF-8; explicit UTF-8 reading restores Chinese correctly.

## Authoritative plan and coordinates

The current plan is the large right-hand plan, base insert 2379D1 (GHS仓底图). Other distant left-hand drawings and rack elevations beneath the current plan are excluded from reconstruction. Full nested INSERT transforms, including negative scaling and rotations, are applied. Entity ancestry is preserved in source_handles.

INSUNITS=1 means inches. Cross-check: FL_PALLET_48W_40D_STD nominal 40 x 48 inches = 1.016 x 1.2192 m; its complete geometric local bbox includes a 5-inch margin, therefore extracted size is 50 x 48 inches. Rack RACK_42D_144B complete bbox is 53.9635 x 150 inches. Do not confuse these geometry bounds with nominal storage depth.

Local mapping is (CAD XY - [6917380,1902500]) * 0.0254. Right-handed XY retained. position_m is the transformed local bbox center. size_m is local-axis size times scale, NOT world AABB. rotation_deg is the world local-X direction. Use these three together. Source Z is intentionally discarded because annotation entities have arbitrary elevations up to 593018 CAD units.

Exact building footprint comes from AREA polyline 2379D1/4F2C8, including southeast diagonal and southwest office extension. Overall physical extents 465.7344 x 137.16 m, area 56116.0983 m2. The larger approximately 524 x 183 m initial block bbox includes grid annotations and must not be used as the building.

## Inventory

- 1607 unique rack centers: 1296 top-level W_RACK_OVERSIZE_WR instances and 311 additional nested instances within LINE1/LOCK/LOCK2/LOCK3. No center duplicates at 1 mm tolerance.
- 7530 W_STORAGE pallet positions, exactly matching the 地堆:7530个 note.
- 206 columns: 170 in architectural base plus 36 added PILLAR instances. These are both retained, not thinned.
- 87 W_DOCK symbols: classified dock racking. This is not evidence of conveyor machinery.
- 55 architectural door block instances.
- 601 candidate wall-face lines; 271 close parallel pairs become measured centerline walls; 59 remain estimated single-face extrusions, giving 330 wall objects. Cutaway height 2.8 m is a visualization choice. The paired wall thickness is measured (often 0.254 m), unpaired thickness 0.15 m is estimated. Some short wall details beneath the 0.35 m extraction threshold remain only in source geometry.
- 56 charging bays: seven arrays of eight 60 x 120 inch angled rectangles. Parent handles 251031,25103B,251040,251044,251049,25104D,251051; matching explicit 56台充电桩 label 251362. parking_center_m is measured. These outlines describe parking bays, not charger casings. dock_point_m is null because the CAD contains no explicit wall-mounted charger socket or support position. Any support partition and physical charger placement are design estimates, not surveyed data.
- No explicit AGV vehicle or operational route was identified. No confirmed conveyor geometry. The 皮带机(蓝) layer contains only four text annotations. No conveyor is invented.

## Rendering and trust

CAD_main_plan.png includes source architectural context (grid and future lines included). CAD_racks_detail.png and CAD_east_charging.png are enlarged source detail views. CAD_verified_layout.png shows only the selected reconstructed categories against the exact footprint. CAD geometry carries physical_candidate flags; grid, dimensions, future, ceiling, lighting, roof, drains and revision entities are retained only for traceability, not automatically turned into physical objects. Raw geometry in cad_raw.json is full drawing XY including excluded diagrams. cad_layout.json is the authoritative integration interface; cad_validation.json records counts and area.

The source plan is huge and highly repetitive. Every physical instance remains represented; no spacing or densities were replaced with generic warehouse examples. Heights, cargo appearance, AGV motion and wall-mounted charger support details require clearly documented visualization assumptions. The CAD contains elevation examples outside the footprint, but their mapping to all plan racks is not explicit, so their heights have not been silently applied to every rack.

Reproduce: inspect_dxf.py, inspect_groups.py, extract_layout.py, refine_layout.py, verify_layout.py, in that order, with the bundled Python and ezdxf in Scripts/_vendor/cad. verify_layout.py asserts instance counts, finite dimensions and permitted wall thickness bounds, and outputs the physical comparison image. All three source CAD image views and the final physical-layout image were visually inspected.
