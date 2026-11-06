# A50 道路局部缺口补片

用户要求补齐铁路靠主仓一侧的道路缺口。当前关卡中 `SM_MPRR_Roads_0_-3` 被手动删除，该 tile 同时包含 A50、C08 和 DA0。因此仅从原资产中提取 A50 的独立路面条带，不恢复整块 tile，也不恢复其他删除。

补片 `SM_MPR_A50_RoadGap.fbx` 包含原来的 181 个完整三角面，面积 511.7896075 平方米，路宽 9 米，中心线长度 56.8655 米。CAD 范围为 X `[0,37.9664]`、Y `[-354.5519,-300]`。二进制 FBX 子集导出保留原面顺序、顶点、法线、UV 和 EdgeFade 颜色，未重采样或改变道路高度。

`validation.json` 验证原属性逐值一致、完整覆盖目标连通分量、与两端邻路接合，并检查 1,540 个道路/地形三角交集角点：最小净空 0.079999664 米。该记录是源文件验证；原生 UE 导入、保存与截图由主任务完成后归档。

在原 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 增加一个 StaticMeshActor：标签 `MPR_A50_RoadGap_20261106`，位置和旋转为 0，缩放为 1。建议资产路径 `/Game/MPRWarehouse/RoadGap20261106/Meshes/SM_MPR_A50_RoadGap`。材质槽为 `MPR4_TerminalAsphalt`，从现有邻路 `SM_MPRR_Roads_-1_-3` 读取有效材质；当前为 `/Game/MPRWarehouse/SiteComplete/Materials/MI_SC_MPR4_TerminalAsphalt`。路缘、边线和虚线仍存在，不需重复增加。

可复现工具按序为 `build_mpr_road_gap.py`、`export_mpr_road_gap.py`、`validate_mpr_road_gap.py`，位于 `Tools/MPRWarehouse`。它们只生成和验证此目录的源文件，不操作 UE 或 Git。`plan.json` 和 `manifest.json` 记录原 FBX 哈希及精确选中面号。
