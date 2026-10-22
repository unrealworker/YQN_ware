# GHS 园区参考风格重建

目标关卡：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。当前展示参数以 `SourceAssets/GHS/Park/reference_style.json` 为唯一依据：冷灰蓝底板、中灰蓝道路、亮白路缘、淡蓝屋顶和有体积的云冠树。本轮重做植被与林岛视觉，并重新设置地面、道路和光照；17 个非植被网格角色以及 CAD 道路、建筑、停车和卡车几何保持。

离线生成、32 项几何检查、独立保存重载、15 项实际运行检查及本轮正式图片归档均已通过。此前版本的树木统计、绿色底板和验收时间不作为当前依据。

## 来源、许可和精度

用户提供的源文件：

```text
D:/UEPro/Test/CADGis/cadmapper-muscoy-california-us/cadmapper-muscoy-california-us/cadmapper-muscoy-california-us.dxf
SHA-256: 82ad1a249acc8f1bacf6fb313f8c422c316663ff987738e789b15e448283a9ec
```

该文件为 CADmapper 区域数据。`extract_park_cad.py` 只读提取 419 个建筑 MESH、185 条线要素，其中 79 条为车辆道路中心线。原顶点、原面、原高程、句柄与图层均保留，场景位置采用三点仿射后的 UV。园区边界、入口、停车与细节由用户卫星图及 `satellite_trace.json` 补充，属于展示重建，不是宗地测量。

原许可全文复制到 [SourceAssets/GHS/Park/LICENSE.txt](../SourceAssets/GHS/Park/LICENSE.txt)，同时保存在 `cad_layout.json.attribution`。地图数据归属 OpenStreetMap contributors；高程注明 USGS NED、NASA SRTM 公有领域来源。分发源数据时须随附原许可文本。

必须区分源标签与可信几何：

- `$INSUNITS=4` 标称毫米，但大仓库为约 `465.14 × 137.66` 个坐标单位，与现有约 `465.73 × 137.16 m` 仓库一致。坐标按米解释，不能再乘 `0.001`；文件头范围也是无效占位值，使用实体计算范围。
- 全部建筑默认拉伸 `3 m`，不是实测高度。住宅采用参考图双层形式，高度约 `7.45–7.81 m`，源高度状态仍标为未经验证。
- 原地形高程保留在数据中，场景地面按平坦展示处理；高速跨越 Sycamore 附近仅局部抬升约 `6.1 m`，坡道和标线跟随高程。不是全场真实地形复原。
- 道路宽度、圆角与院落细节是模型参数；几何净距不能代替交通工程转向扫掠或安全认证。

## 配准与既有仓库

唯一大仓库为 `buildings` 图层 MESH `1eb6`。使用三个锚点：

| 锚点 | CAD XY | 现有仓库 UV，米 |
| --- | --- | --- |
| backSW | `(423.8071, 444.0218)` | `(0, 0)` |
| backNE | `(843.2883, 645.0026)` | `(465.7344, 0)` |
| frontSW | `(483.48, 319.9706)` | `(0, 137.16)` |

```text
u = 0.9023064585475312*x + 0.43404048546294594*y - 575.1273211364305
v = 0.4305234644027491*x - 0.8985758812574258*y + 216.52837930202614
```

长边尺度约 `1.001272`、短边约 `0.996387`。三锚点精确吻合，其余角点最大残差约 `2.22 m`；差异保留并报告，不对周围路网做局部变形。**现有仓库墙体和内部模型使用项目内资产，不重建、不旋转、不缩放，园区生成器跳过 `1eb6`**。本轮另按项目内精确轮廓添加独立屋顶；货架、货物、月台和设备不属于重建范围。

局部 `u` 沿仓库长轴，`v` 指向装卸前场。导出约定以 manifest 为准：

```text
Blender metres: X = u - 239.33385; Y = -(v - 60.24019); Z up
FBX: -Y forward, Z up
UE centimetres after import at origin / scale 1:
X = (u - 239.33385) * 100; Y = (v - 60.24019) * 100
```

硬化地坪为 `−4 cm`。原地面标识所在矩形 `u=189.5…277.1、v=147.9…159.7` 保持避让。公共道路、住宅主位置来自 CAD；北侧 Gray Pine 的卫星补房单独标记，不混称为 CAD 建筑。

## 当前资源与布局

| 项目 | 当前结果 |
| --- | --- |
| Park | 22 个唯一网格，1,657,364 三角面 |
| 独立屋顶 | 1 网格，1 Actor，5 材质槽，8,288 三角面 |
| Park + Roof | 23 个唯一网格，1,665,652 三角面 |
| 含 27 台展示卡车实例展开 | 2,812,148 面，不代表每帧可见面数 |
| 主关卡 | 360 个 Actor，本轮不增减 |
| 住宅 | 338 栋：299 CAD + 39 satellite_infill |
| 小车／小车位／大车位 | 157 台／112 位／52 位 |
| 展示卡车 | 27 台闭门车，1 个 HISM；原 52 台业务车另计 |
| 树木 | 586 棵：280 林树 + 306 街园树 |
| 灌木／林岛 | 332 组灌木，含林岛 72 组；24 个林岛 |

Park 实例展开面数为 `1,657,364 + 44,096 × (27−1) = 2,803,860`，再加屋顶 8,288 面。上述环境统计不含原仓库内部资产，不能当成总场景性能或多人承载能力。

公共路网沿用 79 条 CAD 道路中心线与既有连续圆角、路面合并和标线；住宅、围栏、门卫、停车场及车辆形状与实例不重建。Park 中只允许 Landscape、Trees、TreesLight、TreesDark、Trunk 五角色改变几何，其余 17 类的顶点数、三角面数、包围和实例参数逐项保持。

西南小车位 35 + 37，东北 40（含 2 个无障碍位及 2 个端岛）；共 112 个。157 台小车中 68 台停在园区、89 台在住宅车道。306 棵街园树依据新的真实冠幅进行避让，省略不满足净距的候选；停车道路／泊位／车辆几何保持，`garden_tree_candidates` 是允许变动的景观检查元数据。

闭门展示卡车继续使用原月台长卡车派生的 `Trucks/SM_GHSPark_ClosedTruck.fbx`：44,096 面、7 材质槽、27 个 HISM 实例。可编辑源含 455 个部件；原共享车辆源哈希保持，展示车没有业务 `TwinId`、POI、碰撞或 Tick。屋顶仍是独立非业务 Actor，所有设备与设施统计继续分开验证。

## 云冠树、林岛与安全边界

新树为**五个不等大树冠团、三根支撑枝和一根主干**组成的云冠形态，树冠纬向细分为 12 段，每棵 1,856 面、9 个封闭部分。三个标准变体半径约 `4.05 / 3.70 / 4.60 m`、高约 `8.60 / 10.80 / 8.70 m`，按场景位置缩放。树冠平滑法线和颜色明暗一起表现体积，枝干连接树冠；不是仅对旧模型改色。Trees／TreesLight／TreesDark 三类树冠网格启用 Nanite，并保留完整 fallback；这一细分升级没有改动树位、24 个林岛、树高与安全冠幅。

当前七组林带为：

| 林带 | 树数 | 林岛 | 林岛灌木 |
| --- | ---: | ---: | ---: |
| West woodland | 60 | 5 | 15 |
| Northeast woodland | 60 | 5 | 15 |
| West outer woodland | 30 | 3 | 9 |
| Northwest outer woodland | 20 | 2 | 6 |
| Gray Pine west woodland | 40 | 3 | 9 |
| Gray Pine middle woodland | 40 | 3 | 9 |
| Northeast outer woodland | 30 | 3 | 9 |
| 合计 | 280 | 24 | 72 |

林岛底部 `−0.16 m`、顶部 `0.08 m`，圆角外缘和闭合侧面让地面种植块与环境底板明确分开；24 岛不互相重叠。较大的树冠、短干和零散林岛取代之前的密集小树，不再沿用旧“510 棵完全不变”承诺。

林树中心最小距离 **10.017596 m**；树冠对道路、建筑／车道、园区和水道的保护策略是 `8 / 10 / 8 / 18 m`，本轮几何报告的实际最小值约为 `11.936 / 36.714 / 58.594 / 18.733 m`。三种树的包围经过真实顶点验证；云冠调整未扩大已验证冠幅，最大半径缩小约 `0.005201 m`。街园树也按真实冠幅重新验算，不以名义树高猜测净距。

当前林岛与树木是按参考图做的环境展示，不是卫星逐树测绘。CAD 水道、道路、建筑和原主厂区保持；公共道路／住宅筛选范围不扩大，外围底板几何也保持。具体点位、岛边界和净距见 `site_geometry_report.json.forests`。

## 材质、环境底板与光照

所有当前色值与灯光目标由 **`reference_style.json`** 管理，历史 `presentation_style.json` 只保留阶段来源，不再作为当前执行参数。当前主要线性 RGB 如下：

| 材质角色 | 当前线性 RGB |
| --- | --- |
| Ground／无网格 Backdrop | 0.52 / 0.58 / 0.66 |
| Hardstand | 0.53 / 0.60 / 0.68 |
| Roads | 0.17 / 0.225 / 0.30 |
| ContextRoads | 0.18 / 0.235 / 0.31 |
| CampusRoads | 0.38 / 0.45 / 0.52 |
| Curbs／Markings | 0.92 / 0.95 / 0.98；0.95 / 0.97 / 1.0 |
| Landscape | 0.47 / 0.53 / 0.48 |
| Trees／TreesLight／TreesDark | 0.28 / 0.42 / 0.24；0.36 / 0.50 / 0.30；0.18 / 0.32 / 0.15 |
| 主屋顶 Roof 槽 | 0.80 / 0.88 / 1.0 |

`GHSPark_Ground` **已按用户新要求从旧 Landscape 覆盖切换到独立 `M_GHSPark_Ground`**，不能写成地面颜色原样保留。旧手动材质和组件绑定已备份；位置 `(170,240,0) cm`、用户缩放 `(1.1,1.1,1.1)` 保持。`GHN_StudioGround` 换用私有无网格材质 `/Game/GHSZcoolSmartFactory/Presentation/M_GHSReference_Backdrop`；背景不再出现方格，原室内 FloorGrid 不改。Blue 的 Cobalt 用户覆盖继续保留。

当前光照为 key **3.8**、sky **0.5**、光源角 **8°**、旋转 `(-55,-38,0)°`。天空使用平衡的下半球填充，`lower_hemisphere_is_black=false`。AO 强度 **0.9**、半径 **180 cm**、质量 **80**；Bloom **0.02**，曝光 min=max=0、bias=0 锁定 EV0。沿用已有定向光和天空光，不新增灯光；关卡 GI 与反射保持 `NONE`，不混同项目默认 CVar。

材质模块通过 4 个显式参数表达式写入 SurfaceTint、Roughness、Metallic、Specular，更新前循环清空旧表达式，避免 UE 5.4 参数缓存重复。连续候选预览在参数相同时复用材质，最终只保存指定目标资源；初始未保存用户目标材质禁止覆盖。

## 主厂房屋顶与后续交互

屋顶按项目内精确 CAD 厂房轮廓构建，保留西南突出体与东南斜角，外挑 0.25 m。底面 9.60 m、主檐口 9.76 m、脊线 `v=59.436 m` 且高 10.40 m；办公室为低平屋面。最高货架 9.154 m，屋顶底面净空约 0.446 m。屋顶造型是参考展示参数，不是实测建筑结构。

`GHS_MainWarehouseRoof` 为 1 Actor／1 网格／5 槽，8,288 面、5,018 顶点，独立显隐；Blender 保留 431 个命名部件。几何含 5 条浅蓝分格采光带、310 条立缝、18 个主通风帽及 2 个办公室通风口。本轮仅 Roof 槽颜色按 `reference_style.json` 调整为 `(0.80,0.88,1.0)`；其他四槽与几何保持。详细源文件和坐标见 [MainRoof/README.md](../SourceAssets/GHS/MainRoof/README.md)。

**产品 UI 屋顶按钮尚未实现。** 当前仅为独立 Actor 整体显隐，正式按钮仍需联动内部 POI、货物／设备选取及视角。`PickRay` 使用业务包围盒，不会自动因为屋顶遮挡而阻止内部点选，不能把开启碰撞视为交互已完成。

## 当前复现入口

生成使用 Blender 5.2 与项目目录中的 Shapely；UE 运行时不依赖 Shapely。园区生成器输出当前云冠与林岛；本轮屋顶几何沿用既有源，不需重新生成。

```powershell
& 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python Scripts/ghs/build_park_geometry.py
```

在目标关卡退出 PIE 后，通过现有 `live_dispatcher.py` 调用 **`apply_reference_style.py`**。该入口只重导入 Landscape、Trees、TreesLight、TreesDark、Trunk 五个网格，调用 `reference_style_materials.apply` 更新指定材质、两处地面绑定与灯光，并由主应用流程保存关卡。材料模块本身不会保存地图。

当前截图入口为 **`capture_reference_style.py`**；异步截图必须核对其自身报告成功与图片时间，不能只看桥接 `executed`。正式验收包括真实游戏场景帧及 UI 运行截图，编辑器全景只作为额外环境视图。

独立保存重载使用 **`validate_reference_style.py`**：

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEPro/Test/Test.uproject' -run=pythonscript '-script=D:/UEPro/Test/Scripts/ghs/validate_reference_style.py' -unattended -nop4 -NullRHI
```

此前的 `apply_park_roof_style.py`、`apply_park_forest_fill.py` 与最初完整部署入口属于历史阶段，不能代替当前参考风格入口。

## 原场景保护与当前验收

`Saved/ParkReferenceStyle/Before` 保存本轮 360 Actor 基线、旧参数、旧地图和材质备份。全部 Actor 的标签、类别、网格路径、实例和变换保持，只允许两个地面组件材质按当前配置变化，以及 key 的旋转按光照配置变化。所有相机位置也保留；NullRHI 缺失的 Matinee 编辑器预览网格是唯一比较时忽略的编辑器对象。

旧地面颜色被新需求明确替换，位置和 1.1 缩放受到保护；旧手动覆盖可以从备份恢复。真实游戏帧中暴露的卡车黑色回退来自 7 个 Truck 材质缺少 `used_with_instanced_static_meshes`。专用 live／disk 检查确认除 usage 标记外所有已检颜色、参数、表达式数量及材质模式完全一致，表明其 dirty 状态来自编辑器自动补标记；备份后仅补 usage=True、重编译并保存七个目标资源，不重建图、不改配色和其他参数。最新独立重载与游戏日志已验证修复，通用生成器也为 Truck 角色保存该标记，避免重建复发。原 `/Game/Maps/GHS_CAD_NormalWarehouse` 地图哈希保持。27 台静态展示卡车、原 52 台业务卡车和设备／设施注册表分别检查。

本轮 **32 项几何测试、离线生成与实际树冠安全检查通过**。独立进程于 **2026-10-22 15:49:01（Asia/Shanghai）** 完成保存重载：360 个 Actor、20 个目标材质、3 类 Nanite 树冠、7 个 Truck 实例使用标记、固定 CAD 布局与旧地图保护均通过。当前保存地图 SHA-256 为：

```text
eb46503811527cf427450d7a0a67bf9e89b63e4b97f0d50cbc775bca092d4f5b
```

本轮 **15 项实际运行检查全部通过，耗时 32.093 秒**，设备／设施注册表保持 **106 / 56**。6 张场景图来自真实 **1920×1080 游戏视口**，完成时间稳定后取帧；艺术场景帧只隐藏 HUD，另保留 3 张 UI 运行截图。最新 `runtime.log` 无缺少 `bUsedWithInstancedStaticMeshes` 和默认材质回退警告，`render_probe_restoration.json` 确认诊断 CVar 已完全恢复。

| 证据 | 本轮路径与结果 |
| --- | --- |
| 云冠模型、三变体及 32 项测试 | `Saved/ParkReferenceStyle/tree_shape_validation.json`、`tree_shape_tests.log`；1,856 面／9 部分，12 段树冠纬向细分 |
| 林岛、树木与静态布局保护 | `Saved/ParkReferenceStyle/vegetation_geometry_validation.json`；586 树、332 灌木、24 岛与 17 个非植被角色保护 |
| 应用材质、灯光与两处绑定 | `Saved/ParkReferenceStyle/apply_report.json` |
| 卡车实例材质修复 | `truck_materials_live.json`、`truck_materials_disk.json`、`truck_material_usage_fix.json`；只修改 7 个 usage 标记，原参数配色保持 |
| 独立保存重载 | `Saved/ParkReferenceStyle/saved_validation.json`；15:49:01 成功 |
| 场景／UI 实际运行 | `Saved/ParkReferenceStyle/runtime.log`、本轮运行报告和真实游戏帧；15 项通过，32.093 秒 |
| 诊断状态恢复 | `Saved/ParkReferenceStyle/render_probe_restoration.json`；success=true |
| 当前正式归档 | `SourceAssets/GHS/Park/Review/acceptance.json`；15:52:26 更新，共 11 张，全部图片哈希核对通过 |

旧正式 30 图已从 Review 移除，当前 **11 张**只包括 6 张真实游戏场景帧、3 张 UI 运行帧、1 张编辑器园区全景及 1 张拼图。当前地图、Park／屋顶 manifest 和图片哈希与 receipt 对应，不再混用前版图片。

本轮不包含重新打包 EXE，也不包含多人像素流或稳定 60 FPS 性能测试。
