# 主仓种植带与地坪边界整理

直接用于现有 `/Game/Maps/MPR_CAD_Warehouse_B50B57`。只替换原 `MPRSC_MPRR_CampusGreen` 和 `MPRSC_MPR4_TerminalCurb` 两个组件的网格，沿用它们当前的草地、浅灰路缘材质，不新增 Actor 或材质。不改变现有道路、铁路、停车铺装、混凝土作业区、标线和车辆。

原绿地 4,171.18㎡，删除两处合计 2.26㎡的细碎孤片，并以 0.45m 内收圆角整理尖角。新增西侧、东侧三个圆角种植带共 1,685.56㎡，最终绿地 5,848.95㎡。圆顺及去碎片总共从原绿地中减去 7.79㎡。

CAD 米制坐标：

| 种植带 | X 范围 | Y 范围 |
|---|---:|---:|
| 西侧 | -208 至 -201 | -86 至 78 |
| 东侧南段 | 201 至 207.3 | -15 至 28 |
| 东侧北段 | 201 至 207.3 | 38 至 82 |

新带端部圆角为 2m。西侧 Y≈-90/82、东侧 Y≈33 的道路出入口保留断口。新增绿地经过最新 `city_road_removal_20261106/layout.json` 交通范围裁切，不恢复已删除道路；道路至少退让 0.5m、铁路退让 2m，并排除现有硬地、建筑、车辆、作业区和停车出口。最终树木布局应读取 `plan.json` 的 `surfaces[0].polygons`，而不是只依据上表矩形。

绿地贴合原地形三角面，高出地形 0.045m；树根建议按同一地形采样加 0.055m。新路缘宽 0.24m，底部高出地形 0.035m，顶部 0.235m，嵌入草地 1cm。连续实心带替代分段长方体，避免转角楔缝。19 个既有止轮器的 684 个三角形与旧 FBX 精确相同。

## 来源与验证

- `plan.json`：绿地、连续路缘、保护区域、原止轮器及 Actor 映射。
- `manifest.json`：2 个 FBX 的哈希、材质槽、坐标范围、面数及旧→新路径。
- `MPR_LandscapeGround.blend`：可编辑源文件。
- `geometry_validation.json`：独立二进制 FBX 读回、保护范围交叠、地形高度及止轮器保留验证。

输出面数：绿地 2,345 三角形，路缘及止轮器 29,616 三角形。绿地/路缘对设计投影面积差为 0.0056/0.0108㎡，主要来自 Blender float32 存储；地形偏移最大误差小于 0.000001m。道路、铁路、硬地、作业区、停车出口及车辆交叠检查全部为零。最终仍需 UE 原关卡导入、重载和同机位实景验收。

复现顺序：

1. 用本机 Blender Python 运行 `Tools/MPRWarehouse/plan_mpr_landscape_ground.py`。
2. Blender 后台运行 `Tools/MPRWarehouse/build_mpr_landscape_ground.py`。
3. 用 Blender Python 运行 `Tools/MPRWarehouse/plan_mpr_landscape_ground.py --validate`。

规划使用 `Saved/MPR/landscape_layout_20261106/before.json.gz` 识别原组件；应用由主任务统一检查保存。生成器只写本目录，历史来源不改写。
