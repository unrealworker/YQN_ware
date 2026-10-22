# GHS 主厂房独立屋顶

本目录保存按用户参考图创建的浅色金属主厂房屋顶。目标关卡为 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`；UE Actor 名为 `GHS_MainWarehouseRoof`。屋顶已独立导入；2026-10-22 13:44:16（Asia/Shanghai）独立保存重载已验证单 Actor／单网格、整体显隐及五个材质参数。15 项运行检查与正式图片归档也已完成；当前状态仅表示独立 Actor 显隐能力，不包含产品 UI 开关。

## 几何与视觉

屋顶使用 `SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json` 的精确厂房外轮廓，保留西南办公室突出体和东南斜角；没有拉伸通用仓库屋顶。主厂房长边为 `465.7344 m`，宽度随轮廓变化；办公室前缘到 `v=137.16 m`，主前缘到 `v=118.872 m`。统一外挑 `0.25 m`。

| 项目 | 当前值 |
| --- | --- |
| 封闭底面／既有墙顶 | 9.60 m |
| 主檐口表面 | 9.76 m |
| 主脊线 | v=59.436 m，高 10.40 m |
| 办公室屋面 | v>118.872 m，9.76 m 低平屋面 |
| 最高货架／净空 | 9.154 m／0.446 m |
| 采光带 | 5 条，不透明浅蓝，每条宽 3.6 m、15 格 |
| 采光带位置 | u=75/155/235/315/395 m，v=15…105 m |
| 立缝 | 310 条，间距 1.5 m、高 0.03 m |
| 包边 | 约 0.36 m 蓝色金属边 |
| 通风口 | 18 个主通风帽 + 2 个办公室通风口 |
| FBX | 1 网格、5,018 顶点、8,288 三角面、5 材质槽 |
| Blender 可编辑部件 | 431 个，按屋面／立缝／采光／包边／通风口命名 |

侧缘为封到底面的白色立面，屋顶各部件为闭合实体。采光带采用不透明材质，避免透明排序影响；整个屋顶隐藏后才完整露出原内部。屋顶高度、坡度和细节为参考风格建模参数，不代表建筑测绘或结构施工数据。

## 材质与坐标

| 固定槽顺序 | 线性底色 RGB | 粗糙度 | 金属度 |
| --- | --- | --- | --- |
| Roof | 0.78 / 0.83 / 0.90 | 0.75 | 0.08 |
| Seams | 0.63 / 0.71 / 0.81 | 0.80 | 0.05 |
| Blue | 0.035 / 0.13 / 0.48 | 0.80 | 0.05 |
| Skylight | 0.24 / 0.45 / 0.70 | 0.42 | 0.05 |
| Detail | 0.60 / 0.67 / 0.74 | 0.80 | 0.05 |

FBX 槽名称是 `M_GHSMainRoof_<role>`；UE 使用屋顶私有资源 `/Game/GHSZcoolSmartFactory/Roof/Materials/M_GHSRoof_<role>`，不修改原仓库或园区共享材质。

```text
Blender: (u−239.33385, −(v−60.24019), z) metres
FBX: −Y forward, Z up
UE Actor: location (0,0,0), rotation (0,0,0), scale (1,1,1)
UE vertices: ((u−239.33385)*100, (v−60.24019)*100, z*100) cm
```

UE 网格路径为 `/Game/GHSZcoolSmartFactory/Roof/Meshes/SM_GHS_MainWarehouseRoof`。Actor 无碰撞、无 Tick，不带设备业务身份。所有屋顶细节属于一个 Actor 的一个网格，整体显隐即可，不需逐个隐藏采光带、包边和通风帽。

## 后续交互边界

**本轮没有新增产品 UI 屋顶开关。** 独立 Actor 只为后续开顶交互准备；通过 Actor 显隐可以验证内外状态。正式 UI 开关应联动内部 POI、设备／货物选取和视角状态。当前业务 `PickRay` 按包围盒选取，不会因为屋顶遮挡而自动禁用内部对象；单独开启屋顶碰撞不能解决这个问题。

## 源文件与复现

- `MainWarehouseRoof.blend`：可编辑部件和预览相机；导出用合并对象在源场景中隐藏以免重复显示。
- `SM_GHS_MainWarehouseRoof.fbx`：唯一导入网格。
- `roof_manifest.json`：尺寸、源轮廓、材质槽、部件与共享源哈希。
- `fbx_roundtrip_verification.json`：独立 Blender 回读验证。
- `roof_preview.png`：仅屋顶的 Blender 几何预览，不替代 UE 实拍。

在项目根目录运行：

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python Scripts/ghs/build_main_warehouse_roof.py
```

生成器只写本目录；项目共享材质与既有墙体源资产只读并校验哈希。生成和独立 FBX 回读退出码均为 0，闭合流形、无退化面、正体积、五槽顺序通过，包围回读误差约 `2.29e-5 m`。

UE 应用、截图与保存重载证据写入 `Saved/ParkRoofStyle`。正式场景图片统一更新到 `SourceAssets/GHS/Park/Review`，避免屋顶版与此前开顶版被混当成同一当前设计；本轮保存重载及 15 项实际运行检查全部通过（运行耗时 15.547 秒）。`Review/acceptance.json` 于 2026-10-22 13:46:00（Asia/Shanghai）更新，30 张正式图片及地图／manifest 的 SHA-256 已核对一致。

当前地图 SHA-256：`08eb315366fda2cc76cdfe147d16a422451e1ba224d4beb7421453095b84f74c`。原 359 个 Actor 保留，新增屋顶后共 360 个；Ground 手动材质及位移、Cobalt 覆盖和未保存 Truck 材质状态均保留。
