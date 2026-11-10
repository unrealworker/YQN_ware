# Order replay motion assets

The replay actor owns a fixed pool of five staffed forklifts, three trucks and ten
single loaded blue pallets. It does not tick or modify map actors. The session
owns time, original scene visibility, navigation guards and restoration.

`EvaluateAt` derives all transforms and pallet ownership from absolute playback
time. The 2463-second test cycle includes outbound loading, three actual gate
departures, public-road return, unloading and visible restoration of both tiers
of each source stack. There is no visible stock reset at the cycle boundary.

The original source meshes and map remain unchanged. New meshes use
`/Game/GHSOrderReplay`. `replay_assets.json` records the protected source hashes.
`order-replay.json` stores the selected original component/instance identities
for reversible isolation and full-open replacements of dock doors 75, 51 and 20.

## Geometry contracts

- Forklift cargo attachment: local X 1.93 m, Z -0.0204 m; fork lift is applied once.
- Truck cargo slot X 0.68 m, Y ±0.54 m; bottom slot Z 1.13 m above rear origin.
- Final forklift origin stays 1.25 m behind the truck rear origin. The chassis
  and backrest remain outside the cargo body. About 72% of the pallet length is
  supported by the tines.
- Truck doors swing outward 100 degrees; loaded trucks travel with doors shut.
- D1 racks over dock apertures are hollow below their 4.4704 m lower beam. Static
  collision checks use their real upright/brace parts instead of their full box.
- Loaded route roots retain a tapered 0.35 m rearward allowance at bends. Tests
  validate the actual animated poses, including cargo, rather than route centers.

## Rebuild and verify

Run these Python scripts from the project directory in order:

1. `Scripts/ghs/replay_plan_routes.py` (Blender's Python 3.13 with the existing
   `Saved/ParkRefinement/python_deps` Shapely/NumPy packages).
2. `Scripts/ghs/replay_truck_routes.py` (same interpreter; independently validates
   departure and arrival routes against roads, gates and static exterior objects).
3. `Scripts/ghs/replay_build_timeline.py` (standard Python).
4. `Scripts/ghs/replay_validate_static_actions.py` (Python 3.13).
5. `Scripts/ghs/replay_validate_timeline.py` (standard Python).

Evidence is in `Saved/OrderReplay`: `static_actions_validation.json`,
`timeline_validation.json`, `truck_routes_qa.json`, `contact_geometry_review.json`,
`asset_import.json`, `trail_coverage_validation.json` and the root session's
`Runtime/verification.json`.
The static check uses 0.2 m / 2 degree maximum pose steps and continuous part
hulls, with 3 mm rotational padding. The dynamic check sweeps all eight vehicle
envelopes every 0.1 seconds. Intentional raised fork insertion into its own open
truck is checked separately using the actual FBX geometry. These are geometric
checks of this recorded scene and test schedule, not a vehicle physics solver.

Trails are generated once from visible motion keys, including pickup/dropoff
branches and truck arrivals. Collinear intervals are merged to remove repeated
or reversed traversals. The current motion produces 1613 segments in eight ISMs;
the audited maximum route simplification error is under one centimetre.

Native automation tests: `GHS.Replay.Motion.DirectSeek`,
`GHS.Replay.Motion.CargoOwnership`, `GHS.Replay.Motion.BoundedEvents`,
`GHS.Replay.Motion.CompleteTrails`.

## 2026-11-10 叉车驾驶员更新

普通人工叉车和追溯叉车已改用 MPR 同款 Manny，坐姿烘焙为静态网格。
叉车当前源文件为 `SourceAssets/GHS_Normal/MannedForklift/manned_forklift_50k.blend`。
重建这两个叉车网格时，使用后台 Blender 执行
`Scripts/ghs/export_manny_forklift.py`，再在 UE 执行
`Scripts/ghs/import_forklift_driver_manny.py`，保留 UV、原有 33 个材质槽顺序及新增人物材质。
`Scripts/ghs/verify_manny_forklift_runtime.py` 用于独立游戏进程验证 16 辆普通叉车、5 辆追溯叉车及退出恢复。

旧 `replay_build_assets.py` / `replay_import_headless.py` 是原始整套资产生成流程，
不能直接用于当前叉车：旧网格合并不保留人物 UV，且会重排材质槽。
其他回放资产若需重建，应先隔离输出并审核差异。不要在用户正在使用的 Blender 中生成资产，也不要保存原场景地图。
