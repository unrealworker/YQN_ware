# GHS 主厂房独立屋顶

目标关卡为 `/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`，Actor 为 `GHS_MainWarehouseRoof`。当前屋顶几何沿用既有源；园区风格阶段把 Roof 槽按 `../Park/reference_style.json.roof_color_linear` 调整为更清晰的淡蓝白色，模型几何保持；用户手工将 Skylight 槽改绑 `M_GHSFacade_Glass`，本轮保留该绑定。当前场景复用原立面 Actor 扩展为四面窗组，最新状态以 [OfficeFacade 文档](../OfficeFacade/README.md) 和 [增量验收文件](../OfficeFacade/Review/acceptance.json) 为准。

## 几何与视觉

屋顶使用 `SourceAssets/GHS/RefinementV2/Envelope/envelope_geometry.json` 的精确厂房外轮廓，保留西南办公室突出体和东南斜角；没有拉伸通用仓库屋顶。主厂房长边为 `465.7344 m`，宽度随轮廓变化；办公室前缘到 `v=137.16 m`，主前缘到 `v=118.872 m`。统一外挑 `0.25 m`。

| 项目 | 当前值 |
| --- | --- |
| 封闭底面／既有墙顶 | 9.60 m |
| 主檐口表面 | 9.76 m |
| 主脊线 | v=59.436 m，高 10.40 m |
| 办公室屋面 | v>118.872 m，9.76 m 低平屋面 |
| 最高货架／净空 | 9.154 m／0.446 m |
| 采光带 | 5 条，不透明蓝色，每条宽 3.6 m、15 格；保留用户 Glass 材质覆盖 |
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
| Roof（当前 UE 展示覆盖） | 0.80 / 0.88 / 1.0 | 0.75 | 0.08 |
| Seams | 0.63 / 0.71 / 0.81 | 0.80 | 0.05 |
| Blue | 0.035 / 0.13 / 0.48 | 0.80 | 0.05 |
| Skylight（用户绑定的 Glass 覆盖） | 0.027 / 0.085 / 0.155 | 0.18 | 0.18 |
| Detail | 0.60 / 0.67 / 0.74 | 0.80 | 0.05 |

Roof 槽展示参数来自 `../Park/reference_style.json`。Skylight 保留用户手工设置的 `/Game/GHSZcoolSmartFactory/OfficeFacade/Materials/M_GHSFacade_Glass` 覆盖，当前底色略微调浅，Fresnel 掠射色为 `(0.085,0.18,0.275)`；它没有被重置为源生成器的旧浅蓝色。其他三槽与源几何保持。FBX 槽名称仍是 `M_GHSMainRoof_<role>`，屋顶默认材质资源位于 `/Game/GHSZcoolSmartFactory/Roof/Materials`。

```text
Blender: (u−239.33385, −(v−60.24019), z) metres
FBX: −Y forward, Z up
UE Actor: location (0,0,0), rotation (0,0,0), scale (1,1,1)
UE vertices: ((u−239.33385)*100, (v−60.24019)*100, z*100) cm
```

UE 网格路径为 `/Game/GHSZcoolSmartFactory/Roof/Meshes/SM_GHS_MainWarehouseRoof`。Actor 无碰撞、无 Tick，不带设备业务身份。所有屋顶细节属于一个 Actor 的一个网格，整体显隐即可，不需逐个隐藏采光带、包边和通风帽。

立面为另一独立 Actor，本轮复用它扩展四面窗组：原办公翼 8 跨保留，新增 15 组／35 跨，合计 43 跨、400 块玻璃、13,380 个三角面。玻璃采用略浅的不透明（Opaque）蓝色 Fresnel 材质，不透视后方原墙。南侧 75–78、51–53、30–33 号月台对应 2／3／2 跨，门间 0.60 m 全高柱与 Z=4.25..7.55 m 白面板将高窗接至卷帘门头；11 个编号只向 +Y 外移 20 cm，X／Z、字号和材质保留。其他方向仍按落地、高位、上下分段窗型区分。屋顶隐藏时立面仍保留，立面不属于屋顶显隐组。

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

园区与屋顶风格统一应用入口为 `Scripts/ghs/apply_reference_style.py`，保存重载入口为 `validate_reference_style.py`，截图入口为 `capture_reference_style.py`；旧 roof-style 入口属于历史阶段，不作为当前执行方法。立面之前的风格基线证据位于 `Saved/ParkReferenceStyle`；新增立面的执行与增量验收见 OfficeFacade 文档。

本轮没有新增产品 UI 屋顶按钮。独立 Actor 显隐和后续交互准备不等于用户按钮已经开发；后续仍需联动内部 POI／选取。

立面之前的风格基线为 360 个 Actor；新增独立玻璃立面后，当前主关卡为 **361 个 Actor**。Ground 使用独立冷灰蓝材质，StudioGround 使用无网格蓝灰背景；旧手动材质已备份，用户位置 `(170,240,0) cm`、缩放 `(1.1,1.1,1.1)` 保留。Cobalt 组件覆盖继续保护。7 个 Truck 材质在 live／disk 表面参数对比一致后，仅补齐实例化 usage 标记并保存；材质图、配色及其余参数未改。

园区与屋顶风格历史证据保留在 `Saved/ParkReferenceStyle`。当前四面扩窗和南侧门头的检查输出位于 `Saved/FacadeExpansion`；最新地图哈希、保存重载、运行状态与 **13 张实景**以 [OfficeFacade/Review/acceptance.json](../OfficeFacade/Review/acceptance.json) 为准，不沿用历史验收结论。

Park 当前 1,657,364 面，屋顶仍为 8,288 面，扩展后立面 13,380 面；Park + Roof + Facade 合计 **1,679,032 个唯一资源三角面**，不含原仓库内部资产。植被为 586 棵树、332 组灌木、24 岛；单树 1,856 面，三类树冠启用 Nanite 并保留完整 fallback。该静态统计不代表性能基准；本轮没有新 EXE 或多人像素流性能测试。
