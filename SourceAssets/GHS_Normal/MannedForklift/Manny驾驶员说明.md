# GHS 人工叉车驾驶员

2026-11-10：普通场景和追溯场景使用 MPR 同款 `SKM_Manny_Simple`，
沿用 `MI_Manny_01_New`、`MI_Manny_02_New`。人物坐姿已烘焙到
`manned_forklift_50k.blend` 的 `05_Driver/DRV_Manny_Seated`，不增加运行时骨骼组件。

驾驶员已调整为扶方向盘、双脚落在踏板区域的坐姿。保留叉车车体、轮胎、门架、货叉、
座椅及原点；整体尺寸仍约 344.83 × 124.91 × 233.70 cm。追溯门架与货叉使用原独立资产。

## 材质与性能

- 原有 33 个材质槽保留顺序，避免场景 Actor 的材质覆盖发生错位。
- 新人物材质追加到索引 33、34；原人物的空槽仅用于兼容，不再包含旧人物面。
- 驾驶员为 19,356 三角面；导入 UE 后普通叉车 LOD0 为 51,283 面，追溯车体为 49,783 面。
- 两个网格均保留 4 级 LOD、原 Nanite 配置。普通叉车 LOD0 比替换前增加 1,622 面。

## 重导入

1. 使用后台 Blender 执行 `Scripts/ghs/export_manny_forklift.py`。
2. UE 执行 `Scripts/ghs/import_forklift_driver_manny.py`，只保存两个叉车网格。
3. 独立游戏进程执行 `Scripts/ghs/verify_manny_forklift_runtime.py`，
   检查 16 辆普通人工叉车、5 辆追溯叉车、退出追溯恢复及地图文件未改变。

导出、导入分别校验与替换前包围盒的差值不超过 0.03 cm。
导出保留 UV 与自定义法线，导入临时使用旧版 FBX 工厂以保留空材质槽，完成后恢复导入开关。
不要用原整套回放资产生成器覆盖此人物网格，详见 `SourceAssets/GHS/OrderReplay/README.md`。

`manny_driver_validation.json` 是当前源资产记录，`manny_driver_import_baseline.json`
是替换前用于校验尺寸和材质顺序的基准。原 `manned_forklift_50k_*` 清单保留为历史优化记录。
本地运行验证及截图位于忽略目录 `Saved/MannyForklift/runtime`。
