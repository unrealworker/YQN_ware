# MPR 两处绿色地坪扩展

按用户红线，将南侧拖车停车区与围路之间的楔形空地，以及东侧阶梯外墙与弯道之间的区域，补成与主仓园区绿岛相同的绿色。沿用 `MI_MPRH_CampusGreen`，不调整颜色参数。

- 南侧新增 2665.24 m²，东侧新增 1932.78 m²。
- 仅替换原 `MPRSC_MPRR_CampusGreen` 的网格引用；原绿地几何、树木、车辆、道路、建筑和镜头保留。原关卡仍为 `MPR_CAD_Warehouse_B50B57`，855 个 Actor 中其余 854 个完整保留。
- 边界距道路约 0.4 m、距墙约 1 m，并保留门前空间。南侧贴地抬高 0.045 m；东侧新增面抬高 0.10 m，比已有混凝土高 0.025 m，避免共面闪烁。

`plan.json` / `scope_plan.png` 记录范围；范围图的深浅绿仅用于区分新增与既有区域，UE 内使用同一材质。

`geometry_validation.json` 校验源几何、保护区域和贴地；`native_validation.json` 校验 UE 实际渲染网格。导入后 3583 个有效三角与源面一一对应，过滤的 12 个三角均为零面积。`acceptance/reload_report.json` 记录独立重载验证。

`acceptance.json` 关联三组 1920×1080 固定镜头前后图。修改前图片复用上一轮已经归档的原生截图，地图 SHA256 与本轮修改前快照完全一致；三组相机位置、旋转、FOV 和分辨率均逐项核对。

本轮独立静态场景采样为 98.72 FPS，平均帧时间 10.13 ms，P95 为 11.11 ms（1480 帧、约 15 秒）。这是本机 UE `-game -RenderOffscreen` 的固定场景结果。先前另一个 UE 进程同时运行时的低帧率采样也保存在 `acceptance/concurrent_*`，不作为独立场景结果。

复现工具位于 `Tools/MPRWarehouse`：`plan_mpr_green_extension.py`、`build_mpr_green_extension.py`、`mpr_green_extension.py`、`validate_mpr_green_extension_native.py` 和 `capture_mpr_green_extension.py`。在原关卡干净且与基线一致时使用 `mpr_green_extension.run(unreal)`；`export_native(unreal)` 导出实际渲染面用于独立几何核对。重复应用会主动拒绝，避免覆盖后续手动修改。
