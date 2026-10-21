# GHS 园区 CAD 校准与车辆植被细化

目标关卡：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。本说明对应 2026-10-21 的车辆、植被及停车场细化版本，覆盖此前模型统计和验收状态。当前布局与统计以 `SourceAssets/GHS/Park/park_manifest.json`、`site_geometry_report.json`、`cad_layout.json` 为准。

园区以现有仓库为主体，完整展示装卸前场、内部道路、停车、回转、围栏及出入口；公共道路和住宅提供环境参照。沿用瓷白、冷灰与深蓝风格，不使用卫星截图地面贴图。

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

长边尺度约 `1.001272`、短边约 `0.996387`。三锚点精确吻合，其余角点最大残差约 `2.22 m`；差异保留并报告，不对周围路网做局部变形。**现有仓库主模型使用项目内资产，不重建、不旋转、不缩放，园区生成器跳过 `1eb6`**。货架、货物、月台和设备也不属于重建范围。

局部 `u` 沿仓库长轴，`v` 指向装卸前场。导出约定以 manifest 为准：

```text
Blender metres: X = u - 239.33385; Y = -(v - 60.24019); Z up
FBX: -Y forward, Z up
UE centimetres after import at origin / scale 1:
X = (u - 239.33385) * 100; Y = (v - 60.24019) * 100
```

硬化地坪为 `−4 cm`。原地面标识所在矩形 `u=189.5…277.1、v=147.9…159.7` 保持避让。公共道路、住宅主位置来自 CAD；北侧 Gray Pine 的卫星补房单独标记，不混称为 CAD 建筑。

## 本轮生成结果

当前 manifest 版本 `2`：**21 个网格、741,077 个三角面、338 栋住宅**。其中 299 栋保留 CAD 中心和外接矩形轴向，39 栋为 `satellite_infill`；补房沿已有 Gray Pine 道路与支路布置。最终范围约为 `u=[−197,747]、v=[−217,592] m`，不同于较小范围的独立住宅模块预检。

四种住宅模块包含双层体量、坡屋顶、车库、门窗及太阳能板。屋顶限制在源建筑外接矩形内，场景检查的 `footprint_uv_m` 是实际模型的定向包围矩形。335 条车道连接街边，3 户保留短入口。共用车道口整体合并，前草坪按邻近住宅分区，856 段约 `1.4 m` 浅灰侧后院墙避让道路和住宅。

道路先以圆弧相切处理转角，再合并路面并生成外缘路缘，不在交叉口横穿内部白边。虚线沿全程弧长延续，坡道标线顶点随道路高程变化。道路及围栏模块可独立做几何测试。

本轮车辆植被细化沿用已配准的 79 条 CAD 道路中心线，不改变中心线来迁就车位。修复了道路合并过度平滑导致邻近道路间空地被误填为连接面的情况：`road_union` 的合并圆角参数由 `4.0 m` 调为 `3.8 m`，避免误连接，并恢复上场西侧连续 6 个泊位。停车、绿岛与森林均从修正后的道路保护区外布置。

围栏周长约 `1,533.835 m`，其中约 `1,513.526 m` 有栏，仅在 **SW Main gate** 与 **NE Service gate** 处开口；604 根立柱、4 个门柱、2 个门卫。非入口围栏与道路重叠长度为 `0 m`，52 台既有月台货车轮廓位于围栏范围内。入口门柱间净宽约 `9.813 m`、`10.914 m`。

| 离线检查 | 当前结果 |
| --- | --- |
| 道路合并面 | 有效 |
| 住宅最小道路净距 | `1.064755 m` |
| 受检停车车辆 | 167 台；最小道路净距 `0.355629 m` |
| 两门卫道路净距 | `2.583393 m`、`3.774644 m` |
| 三组挂车泊位道路净距 | 约 `4.040–4.695 m` |
| 前草坪重叠面积 | 约 `1.46e-11 m²`，浮点误差量级 |
| 停车绿岛最小道路净距 | `0.596939 m` |
| 泊位边缘最小道路净距 | `0.029126 m` |
| 停车种植区域与道路重叠面积 | `0 m²` |
| 林带树心最小间距 | `5.701946 m`，要求至少 `5.7 m` |
| 林带树冠最小水道净距 | `18.602890 m`，保留 `18 m` 避让策略 |

当前包含 **82 个园区小车泊位、52 个挂车泊位、140 台小车、27 台停放挂车、815 棵树、191 组低矮灌木**。小车中 51 台在园区泊位、89 台在住宅车道；车和泊位的数量不是同一统计口径。815 棵树已包含两片林带的 510 棵，不能再相加。

### 汽车与停车场细节

`park_vehicles.py` 提供轿车与紧凑型 SUV，当前分别 62、78 台；每车实际三角化为 **584 面**。车头朝局部 `+u`，有引擎盖、尾箱、斜前后风挡、车顶、四轮及轮毂、轮眉、后视镜、前后车灯、保险杠和门把手。真实几何约 `4.516 × 1.854 m`，清距记录使用保守 `4.53 × 1.854 m`。白／蓝车身沿用场景材质，深色轮胎和红色尾灯使用独立材质角色，不新增外部纹理。

`park_parking.py` 按用户提供的停车场卫星近景补充泊位与种植细节；上、下的命名对应这张卫星图，不指地理正北和正南。上场中央车辆沿 `v` 排列，下场中央车辆沿 `u` 排列，方向相差 90°。中央两排的两端各设圆头长绿岛，上下两场共 **4 处**，沿岛布置灌木并在端头种树；外围增加贴边停车、入口绿地、沿街绿化、门卫绿岛及车行箭头。

上场 35 个泊位、下场 37 个、东北辅助停车场 10 个，共 82 个。2 个原候选泊位因侵入行车通道而省略；保留入口和车道，不强行填满所有空间。泊位边缘最小道路净距约 `0.029 m`，车辆占地最小道路净距约 `0.356 m`，绿岛和种植区不进入道路。卫星图提供排布与绿化形式，车位数量属于按现有 CAD 通道适配的展示模型，不宣称逐位测绘一致。

### 绿色树冠与两片林带

`park_vegetation.py` 用圆润、偏心的多簇树冠和可见树干替换单个棱锥。三种树形按深、中、浅绿色分配树冠，低矮灌木为独立形态。最终树木 815 棵，低矮灌木 191 组。

左侧 **West woodland 240 棵**、右上方 **Northeast woodland 270 棵**，由 `park_forests.py` 使用固定随机种子 `173350210` 生成。这两片林带是用户要求的空白环境补充，**不是卫星逐棵测绘，也不改写 CAD 建筑或道路**。避让策略为道路 `8 m`、建筑及车道 `10 m`、园区 `8 m`、水道 `18 m`；已避让 CAD 内 10 条水道，最小实际树冠水道净距约 `18.603 m`。林带地面沿树群分布形成疏密斑块，保留道路、河道和住宅空隙。

## 依赖与复现

以下命令在 `D:/UEPro/Test` 运行。生成侧使用 Blender 5.2 自带 Python 3.13；Shapely 2.1.2 及其 NumPy 依赖放在项目专用目录，不安装到 UE Python：

```powershell
& 'D:/WinAPP/Blender/5.2/python/bin/python.exe' -B -m pip install 'shapely==2.1.2' --target 'Saved/ParkRefinement/python_deps'
```

DXF 提取复用 `Scripts/_vendor/cad/ezdxf`。Shapely 只负责离线路面合并、带孔三角化和空间裁剪；**FBX、UE 静态网格及运行时不需要 Shapely**。

1. 提取 CAD：

   ```powershell
   & 'D:/WinAPP/Blender/5.2/python/bin/python.exe' -B Scripts/ghs/extract_park_cad.py --extract-only
   ```

   输出 `SourceAssets/GHS/Park/cad_layout.json` 与 `Saved/ParkRefinement/CAD/cad_analysis.json`。带 Pillow 的 Python 可运行同脚本 `--render-only` 重建三张 CAD PNG。

2. 运行几何测试并后台生成：

   ```powershell
   $env:PYTHONPATH = 'D:/UEPro/Test/Saved/ParkRefinement/python_deps'
   & 'D:/WinAPP/Blender/5.2/python/bin/python.exe' -B -m unittest discover -s Scripts/ghs -p 'test_park_*.py' -v
   & 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python Scripts/ghs/build_park_geometry.py
   ```

   生成器调用 `park_site.py`，组合 `park_curves.py`、`park_surfaces.py`、`park_fence.py`、`park_residential.py`、`park_housing.py`，并通过 `park_vehicles.py`、`park_vegetation.py`、`park_parking.py`、`park_forests.py` 生成本轮车辆、绿化及停车细节。生成 `.blend`、21 个 FBX、manifest、完整几何报告及预览；成功以退出码和 `GHS_PARK_READY` 为准。

3. 在已打开目标关卡且退出 PIE 的 UE 编辑器中应用。使用当前会话 `Scripts/ghs/live_dispatcher.py` 桥接；未启用时先在编辑器 Python 环境执行该脚本，再投递请求：

   ```powershell
   $parkRequest = @{ id = [guid]::NewGuid().ToString(); script = 'apply_park_expansion.py' }
   [IO.File]::WriteAllText('D:/UEPro/Test/Saved/GHS_LiveRequest.json', ($parkRequest | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
   ```

   核对同 ID 的 `Saved/GHS_LiveStatus.json` 和新生成的 `Saved/ParkExpansion/apply_report.json`。应用脚本导入 FBX、绑定材质、更新 `GHSPark_` 环境 Actor 并保存关卡。不要重采集或覆盖修改前基线。

4. 以相同请求方式依次运行 `validate_park_expansion.py`、`capture_park_expansion.py`、`capture_park_details.py`。每项完成并核对最新报告后再投递下一项。截图使用异步回调，桥接 `executed` 仅说明已启动，必须等待截图报告自身 `success` 及文件时间更新。

5. 独立进程重载使用 `validate_park_saved.py`，实际运行回归使用 `verify_park_runtime.py`，与编辑器结构检查分别保留证据：

   ```powershell
   & 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEPro/Test/Test.uproject' -run=pythonscript '-script=D:/UEPro/Test/Scripts/ghs/validate_park_saved.py' -unattended -nop4 -NullRHI
   & 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' 'D:/UEPro/Test/Test.uproject' /Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory -game -RenderOffscreen -TwinDiagnostics -windowed -ForceRes -ResX=1920 -ResY=1080 -unattended '-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_park_runtime.py'
   ```

## 原场景保护

新增对象使用 `GHSPark_` 前缀和 `GHS_ParkContext` 标签，不带现有设备业务 `TwinId=`，不进入设备搜索或状态统计。背景关闭碰撞和 Tick。只调整当前关卡相机实例以容纳园区，不修改共享相机类默认值；旧 `/Game/Maps/GHS_CAD_NormalWarehouse` 地图应保持原哈希。

`Saved/ParkExpansion/scene_inspection.json`、`map_before.umap`、`source_map_baseline.json` 是原扩展前基线，须保留。导入前用户删除 `GHS_SiteTitle` 的证据在 `pre_import_changes.json`，不要恢复标题。验证器对其余 334 个原 Actor 的网格、材质、标签、变换与实例数据逐项比对，仅允许约定的相机变化。`Saved/ParkRefinement/Before` 是此前 CAD 细化前快照，不能当作本轮车辆植被细化后的验收结果。

## 本轮验收证据

2026-10-21 23:39 完成最终导入，23:40 完成近景截图并保存，23:41 独立命令行进程重载退出码为 0。保存重载检查通过：334 个原对象的网格、材质、标签、变换与实例数据保留；当前地图共 358 个 Actor，其中园区使用 21 个合并静态网格及 3 个既有评审相机。旧 NormalWarehouse 地图哈希保持不变。

23:43 实际运行回归完成，14 项检查全部通过：1920×1080 / 2560×1600 全景构图、面板收展、AGV-07 选择与详情、全景复位清除选中、货架区／地堆区聚焦，以及设备 106 台、设施 56 个的注册表保持一致。运行测试未保存或更改地图。32 项道路、曲线和空间几何测试也已通过。

本轮 UE 近景确认汽车轮廓、绿色多簇树冠、西侧及东北林带、上下停车场不同方向、四处端头绿岛与道路净空。上场西侧为连续 6 个泊位；中央车辆朝向、轮挡与白线封底统一在共享中线一侧，车道开口保持敞开。`SourceAssets/GHS/Park/Review` 已覆盖旧图并保存 15 张本轮图片（含 1 张实拍拼图），地图、manifest 和图片哈希记录在 `acceptance.json`。

| 范围 | 证据位置与用途 |
| --- | --- |
| 源完整性 | `Saved/ParkRefinement/CAD/validation.json`：419 个网格、185 条线逐项一致，源哈希未变 |
| 配准 | `Saved/ParkRefinement/CAD/CAD_raw_context.png`、`CAD_registered_uv.png`、`CAD_warehouse_alignment.png` |
| 最终离线几何 | `SourceAssets/GHS/Park/park_manifest.json`、`site_geometry_report.json`、`Saved/ParkPolish/blender_geometry.log` |
| 模块预检 | `Saved/ParkRefinement/housing_validation.json`、`residential_validation.json`；独立预检范围较小，不代替最终 338 栋统计 |
| 车辆及植被 | `Saved/ParkPolish/vehicle_detail_report.json`、`vehicle_detail_perspective.png`、`vehicle_detail_top.png`、`vegetation_validation.json`、`vegetation_variants.png` |
| 林带及停车复核 | `Saved/ParkPolish/forest_validation.json`、`forest_layout.png`、`parking_independent_review.json` |
| UE 应用与结构 | `Saved/ParkExpansion/apply_report.json`、`validation.json`：最终 21 网格绑定正确 |
| UE 保存重载 | `Saved/ParkExpansion/saved_validation.json`、`reloaded_actors.json`：334 原对象与旧地图保留 |
| UE 全景截图 | `Saved/ParkExpansion/capture_report.json`：3 个全景视角成功 |
| UE 近景 | `Saved/ParkRefinement/detail_capture_report.json`：10 个近景成功 |
| 实际运行回归 | `Saved/ParkExpansion/runtime_report.json` 与 `Runtime_*.png`：14 项通过 |
| 提交内的最终证据 | `SourceAssets/GHS/Park/Review/acceptance.json`、`Polish_Summary.png` 及 14 张原始截图 |

本轮未重新打包 EXE。静态网格面数、离线净距及结构检查不证明多人像素流或稳定 60 FPS；本轮环境细化不替代独立性能测试。
