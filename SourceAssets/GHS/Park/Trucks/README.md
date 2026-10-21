# 园区静态闭门卡车

`SM_GHSPark_ClosedTruck.fbx` 由项目既有 `SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend` 派生。原月台车辆的共享 FBX、Blender 和 UE 网格资产均保持原哈希，不修改原 52 台业务车辆。

- 单个网格、7 个材质槽、44,096 三角面。
- 尾部原点 `(0,0,0)`，车头朝局部 `+X`，单位为米。
- 包含车镜的完整尺寸约 `14.903501 × 3.000000 × 3.741501 m`。
- 保留 423 个原部件的完整顶点形状；移除 16 个侧折门及铰链部件，新建 30 个双扇闭门、锁杆、铰链、密封及装饰部件。
- 两条侧面深蓝腰带由 `0.22 m` 加宽至 `0.62 m`；驾驶室和顶帽深蓝，货箱瓷白。
- `closed_truck.blend` 保留可编辑部件；3 张 PNG 是实际 Blender 渲染，不代表 UE 场景验收。

`closed_truck.json` 记录按 FBX 顺序排列的 `mesh.material_roles`、材质色值、完整包围盒、文件哈希及验证结果。UE 厘米包围盒已反转 Blender 的 Y 轴。放置时应使用包围盒中心偏移及最低 Z 补偿，不沿用旧简化挂车的尺寸。

独立后台生成：

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python 'D:/UEPro/Test/Scripts/ghs/build_park_truck.py'
```

生成器对原资源做哈希保护，对保留部件逐顶点比对，并用 2,350 条射线仅测试新后门组件，防止把货箱前墙误当成关门成功。几何检查不代替 UE 导入、材质绑定和性能验证。

本模型仅用于无碰撞、无 Tick 的园区静态环境实例，不应复制 `IndependentDockTruck`、`TwinId=`、`Dock=` 等业务标签，也不应附加货车数据、POI 或交互组件。
