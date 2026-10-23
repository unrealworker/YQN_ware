# 回放期间的去停车车辆替代资产

这组资产只用于订单追溯的临时场景隔离。运行时替换原组件的 StaticMesh，结束时恢复原 mesh 和可见性；原地图、原园区资产及用户摆放不修改。

## 精确识别依据

从 `Park/site_geometry_report.json` 获取已占用停车位与住宅 driveway 路径，调用原 `Scripts/ghs/park_vehicles.py::build_car` 重建车辆顶点、面、角色和绕序。将其转换为原 Blender 坐标和 float32，再与 `GHS_Park_Source.blend` 的实际多边形逐面匹配。每个预期面必须唯一存在；两个车身色候选必须恰好命中一个；所有 157 辆必须匹配才能导出。

匹配结果：68 辆停车场车辆、89 辆住宅车辆，合计删除 91,688 个三角面。未使用包围盒或位置范围删除几何。

## 输出与保留

| 原角色 | 原面数 | 删除车辆面 | 保留面数 | 回放处理 |
| --- | ---: | ---: | ---: | --- |
| Buildings | 22,626 | 4,800 | 17,826 | SM_ReplayNoCars_Buildings |
| Blue | 1,619 | 1,480 | 139 | SM_ReplayNoCars_Blue |
| Detail | 13,462 | 11,304 | 2,158 | SM_ReplayNoCars_Detail |
| Solar | 3,510 | 942 | 2,568 | SM_ReplayNoCars_Solar |
| Markings | 11,874 | 3,454 | 8,420 | SM_ReplayNoCars_Markings |
| Rubber | 15,700 | 15,700 | 0 | 临时隐藏 |
| VehicleLights | 1,884 | 1,884 | 0 | 临时隐藏 |

替代 mesh 精确保留非车辆面的 float32 顶点坐标、顶点绕序、面序、材质索引和 smooth 标记，保存前后以 SHA256 比较。剥离后顶点按原序重索引，不改变坐标/原点/变换。建筑、门岗、路面标线、住宅太阳能板等同 role 非车几何保留。

每个输出 FBX 保持原材质槽顺序；UE 导入时复制原 mesh 的完整 static_materials，因此 slot 名称和材质引用保持兼容。组件已有 override materials 必须由回放 Session 保留，不应被替换资产覆盖。

## 文件与执行

- `manifest.json`：157 辆来源、各 role 删除/保留统计、保留面哈希、源文件哈希和 asset 映射。
- `exact-match-probe.json`：精确匹配检查结果。
- `GHS_OrderReplay_NoParkingCars.blend`：独立、可编辑的 5 个替代网格。
- `SM_ReplayNoCars_*.fbx`：5 个原点对齐的导入源。
- 构建：`D:/WinAPP/Blender/blender.exe --background --factory-startup --python-exit-code 1 --python Scripts/ghs/build_order_replay_parking.py`。
- 导入：通过受调度的 UE live dispatcher 执行 `Scripts/ghs/import_order_replay_parking.py`，只创建 `/Game/GHSOrderReplay/Parking` 的 5 个新 mesh；不操作场景组件。
- 运行映射：`Content/GHSTwinUI/data/order-replay-parking.json` 是标准 JSON 数组，5 条 source/replacement、2 条 source/hide。
- 导入验证：`Saved/OrderReplay/parking_import.json`，检查原 UE 三角数、目标三角数、材质槽、边界、组件快照、原资产/map 文件哈希和 dirty-map 状态。

实际回放隔离与结束恢复仍须由 Session 运行验收；这组资产导入不改变当前编辑器场景。所有 `.blend` 操作均在独立背景进程执行，未访问或保存用户实时 Blender 工作。

本轮 UE 实际导入已通过，持久证据为 `ue-import-verification.json`。目标 5 个 mesh 三角数依次为 Buildings 35,652、Blue 258、Detail 4,348、Solar 5,136、Markings 16,804；最大边界误差 0.00452 cm。Markings 原稿中 6 个面积严格为 0 的非车辆三角在原/目标 UE 导入时均被剔除，已单独记录其原多边形 ID；不是车辆识别遗漏，也不是额外删除路面标线。

交付清单为 `delivery-files.json`。自动 `.blend1` 备份不属于交付依赖。
