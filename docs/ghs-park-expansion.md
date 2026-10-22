# GHS 园区疏朗扩域树林

目标关卡：`/Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory`。本说明对应 2026-10-22 按用户反馈将五处外围树林扩大、疏化后的版本，覆盖此前模型统计和验收状态。当前布局与统计以版本 3 的 `SourceAssets/GHS/Park/park_manifest.json`、`site_geometry_report.json`、`cad_layout.json` 为准。本轮保留原两片林带的 510 棵树，扩大五处外围树林覆盖、降低密度并增加自然空隙，只刷新六个既有网格。本轮 UE 原位应用、独立视觉复核、保存重载与 14 项运行检查已通过；下文记录疏朗扩域版本的当前证据。

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

当前 manifest 版本 `3`：**22 个唯一网格资产、987,014 个唯一资产三角面、338 栋住宅**。22 个资产由 21 个环境合并网格与 1 个闭门卡车网格组成；卡车网格自身为 44,096 面，复用 27 次。按所有实例展开后的环境三角面为 **2,133,510**，计算为 `987014 + 44096 × (27−1)`，不能将唯一资产面数当成全场实例面数，也不能将展开面数当作每帧实际可见面数。

住宅中 299 栋保留 CAD 中心和外接矩形轴向，39 栋为 `satellite_infill`；补房沿已有 Gray Pine 道路与支路布置。道路／住宅共用范围继续为 `u=[−197,747]、v=[−217,592] m`，不同于较小范围的独立住宅模块预检。本轮只扩展外围森林地面，未扩大这套公共路网／住宅生成范围。

四种住宅模块包含双层体量、坡屋顶、车库、门窗及太阳能板。屋顶限制在源建筑外接矩形内，场景检查的 `footprint_uv_m` 是实际模型的定向包围矩形。335 条车道连接街边，3 户保留短入口。共用车道口整体合并，前草坪按邻近住宅分区，856 段约 `1.4 m` 浅灰侧后院墙避让道路和住宅。

道路先以圆弧相切处理转角，再合并路面并生成外缘路缘，不在交叉口横穿内部白边。虚线沿全程弧长延续，坡道标线顶点随道路高程变化。道路及围栏模块可独立做几何测试。

本轮补林保留全部道路、住宅、停车场、车辆与材质。当前沿用已配准的 79 条 CAD 道路中心线及 `road_union` 的 `3.8 m` 合并圆角，不改变中心线来迁就车位。西南停车场的 72 个泊位、车辆方向、植被与对应输出逐项保持一致；东北停车场已按此前卫星近景补齐。停车、绿岛与森林均从道路保护区外布置。

围栏周长约 `1,533.835 m`，其中约 `1,513.526 m` 有栏，仅在 **SW Main gate** 与 **NE Service gate** 处开口；604 根立柱、4 个门柱、2 个门卫。非入口围栏与道路重叠长度为 `0 m`，52 台既有月台货车轮廓位于围栏范围内。入口门柱间净宽约 `9.813 m`、`10.914 m`。

| 离线检查 | 当前结果 |
| --- | --- |
| 道路合并面 | 有效 |
| 住宅最小道路净距 | `1.064755 m` |
| 受检停车车辆 | 184 台；最小道路净距 `0.309063 m` |
| 两门卫道路净距 | `2.583393 m`、`3.774644 m` |
| 三组挂车泊位道路净距 | 约 `4.040–4.695 m` |
| 前草坪重叠面积 | 约 `1.46e-11 m²`，浮点误差量级 |
| 停车绿岛最小道路净距 | `0.596939 m` |
| 泊位边缘最小道路净距 | `0.029126 m` |
| 停车种植区域与道路重叠面积 | `0 m²` |
| 东北停车场泊位／无障碍位／端岛 | `40 / 2 / 2`；无障碍位计入 40 个泊位 |
| 东北泊位边缘最小道路净距 | `0.094133 m` |
| 东北绿岛最小道路净距 | `0.693841 m` |
| 原林带／全局树心最小间距 | `5.701946 m`，保留原组至少 `5.7 m` 的规则 |
| 五片疏林到全部林树最小中心距 | `10.005902 m`，新组要求至少 `10 m` |
| 林带树冠最小水道净距 | `18.063233 m`，保留 `18 m` 避让策略 |

当前包含 **112 个园区小车泊位、52 个大车泊位、157 台小车、27 台闭门静态展示卡车、1,373 棵树、260 组低矮灌木**。小车中 68 台在园区泊位、89 台在住宅车道；车和泊位的数量不是同一统计口径。1,373 棵树已包含七组林带的 1,062 棵（原 510 + 五片疏林 552），不能再相加。27 台展示卡车独立于原 52 台月台业务卡车，不重复计入设备注册表。

### 汽车与停车场细节

`park_vehicles.py` 提供轿车与紧凑型 SUV，当前分别 73、84 台；每车实际三角化为 **584 面**。车头朝局部 `+u`，有引擎盖、尾箱、斜前后风挡、车顶、四轮及轮毂、轮眉、后视镜、前后车灯、保险杠和门把手。真实几何约 `4.516 × 1.854 m`，清距记录使用保守 `4.53 × 1.854 m`。白／蓝车身沿用场景材质，深色轮胎和红色尾灯使用独立材质角色，不新增外部纹理。

`park_parking.py` 按用户提供的停车场卫星近景补充泊位与种植细节；上、下的命名对应这张卫星图，不指地理正北和正南。上场中央车辆沿 `v` 排列，下场中央车辆沿 `u` 排列，方向相差 90°。中央两排的两端各设圆头长绿岛，上下两场共 **4 处**，沿岛布置灌木并在端头种树；外围增加贴边停车、入口绿地、沿街绿化、门卫绿岛及车行箭头。

西南上场 35 个泊位、下场 37 个，本轮逐项保持一致；东北停车场保留 **40 个泊位**，全园区共 **112 个**。东北采用中央双排与外围停车，包含 2 个蓝色无障碍位及侧向通道、2 处圆头端岛，并补齐门卫外侧与场边绿化。全场端岛共 6 处，其中西南 4 处、东北 2 处。西南原有 2 个候选泊位仍因侵入行车通道而省略，东北 40 个泊位全部通过放置检查。

东北泊位边缘最小道路净距约 `0.094 m`，东北绿岛最小道路净距约 `0.694 m`；全园区泊位和绿岛的最小值分别为 `0.029 m`、`0.597 m`。157 台小车及 27 台展示卡车的保守包围矩形均避让道路，最小道路净距约 `0.309 m`。卫星图提供排布与绿化形式，车位数量属于按现有 CAD 通道适配的展示模型，不宣称逐位测绘一致。

### 月台原模型派生的闭门展示卡车

`build_park_truck.py` 读取既有 `SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend`，派生 `SourceAssets/GHS/Park/Trucks/SM_GHSPark_ClosedTruck.fbx`。保留原车型的驾驶室、底盘、车轮与货箱细节，移除侧折后门并新建闭合双扇门、锁杆、铰链和密封。驾驶室及顶帽改为深蓝，侧面蓝色腰带由 `0.22 m` 加宽至 `0.62 m`，货箱保持瓷白。

独立源文件 `Trucks/closed_truck.blend` 保留 **455 个可编辑零件**；其中 423 个原部件逐顶点形状保留，16 个旧门与铰链部件被移除，2 个腰带部件改形，新增 30 个闭门及相关部件。导出单网格有 7 个材质槽、44,096 三角面，包含后视镜的完整尺寸约 `14.904 × 3.000 × 3.742 m`。尾部原点、车头朝局部 `+X`，放置使用完整包围盒中心偏移和最低 Z 补偿。

主 `GHS_Park_Source.blend` 保存 27 个 `Park_DisplayTruck_XX` 场景对象，采用 linked mesh data 共用网格；可编辑零件保留在独立 `closed_truck.blend`，场景实例不复制零件几何。UE 导入使用 **一个 HISM 组件、27 个实例**，不克隆原业务 Actor；不附加 POI、数据组件或业务身份，关闭碰撞和 Tick。原 52 台月台业务卡车保留原模型及交互。

派生生成器记录并校验原 `.blend`、`.fbx`、`.uasset` 三个共享资源的 SHA-256，不修改其内容。`Trucks/closed_truck.json` 还包含 2,350 条仅针对新后门的封闭射线检查、材质槽顺序、部件比对及几何结果；离线射线与源哈希保护不能代替本轮 UE 保存重载和业务回归。

### 五处树林扩域、疏化与自然空隙

`park_vegetation.py` 使用圆润、偏心的多簇树冠和可见树干，三种树形按深、中、浅绿色分配树冠，低矮灌木为独立形态。当前树木 **1,373 棵**、低矮灌木 **260 组**；林带共 **1,062 棵**，另有场边、住宅与停车场树木 311 棵。

原两片林带的 510 棵树、固定随机序列、尺度、树形及地面输出保持；原种子为 `173350210`。本轮仅把五处外围树林的参考轮廓按中心线性放大 **1.4 倍**，并降低树群密度。五片使用独立种子 `173352210 + 101 × 组序号`，不会扰动原组。实际放置受中心间距和完整 CAD 避让约束，以完整报告的 **552 棵**为准，不为凑目标数量缩小净距。

| 林带 | 当前状态 | 树木数 |
| --- | --- | --- |
| West woodland | 原左侧林带，保留 | 240 |
| Northeast woodland | 原右上林带，保留 | 270 |
| West outer woodland | 扩大并疏化的西外侧 | 85 |
| Northwest outer woodland | 扩大并疏化的西北外侧 | 66 |
| Gray Pine west woodland | 扩大并疏化的 Gray Pine 西段 | 150 |
| Gray Pine middle woodland | 扩大并疏化的 Gray Pine 中段 | 150 |
| Northeast outer woodland | 扩大并疏化的东北外侧 | 101 |
| 合计 | 原 510 + 五片疏林 552，七组 | 1,062 |

下表仅比较五处外围树林，基线为 `Saved/ParkForestSpread/Before/site_geometry_report.json`（较密版本，提交 `dc15e22`）；“林地”采用报告中五组 `planted_ground_area_m2` 之和，不是整片 Ground 包络：

| 指标 | 较密基线 | 当前疏朗扩域版 |
| --- | --- | --- |
| 五片实际树木 | 696 | 552 |
| 五片实际林地面积 | 43,858.823 m² | 86,999.352 m² |
| 平均树木密度 | 158.691 棵/公顷 | 63.449 棵/公顷 |
| 新组树心间距要求 | 5.7 m | 10 m |

覆盖达到基线 **1.984 倍**，平均密度降低约 **60.02%**。林地内采用变密度树群、较稀疏的边缘和宽阔自然空隙；部分外侧区域因水道或间距限制少于目标棵数，保留空隙，不重新加密填满。

五片新树到全部林树的实际最小中心距为 **10.005902 m**；包含原两片的全局最小值仍为 **5.701946 m**。两个指标的范围不同，不能用全局数值误判新组未达到 10 m。

树林是用户要求的环境补充，**不是卫星逐棵测绘，也不改写 CAD 建筑或道路**。原五处边界由截图地面锚点映射，定位精度估计约 **±10 m**；本轮扩域同样属于展示调整。树冠至道路、建筑及车道、园区、水道的策略净距为 `8 / 10 / 8 / 18 m`，检查使用完整 CAD 道路与建筑保护区。CAD 内 10 条水道保持，当前最小实际树冠水道净距为 **18.063233 m**。

外围森林 Ground 包络单独扩展至约 `u=[−346.541,818.904]、v=[−370.118,592] m`，相对原公共场景地面增加约 **261,350.716 m²**。只输出原地面之外的增量区域，重叠面积约 **6.69e-14 m²**，为浮点误差量级。道路与住宅共享的 `scope` 未扩大；原林带地面不被覆盖，新林地裁去原林地后再输出，避免共面叠加。

生成器唯一资源三角面上限为 **1,100,000**，本轮实际 **987,014**；卡车按全部实例展开后的全场面数为 **2,133,510**。这个预算不是实时帧率承诺。

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

2. 运行几何测试并生成园区。以下包含首次部署的卡车派生命令；本轮补林复用已验证卡车，仅执行测试与最后一条主生成命令：

   ```powershell
   $env:PYTHONPATH = 'D:/UEPro/Test/Saved/ParkRefinement/python_deps'
   & 'D:/WinAPP/Blender/5.2/python/bin/python.exe' -B -m unittest discover -s Scripts/ghs -p 'test_park_*.py' -v
   & 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python Scripts/ghs/build_park_truck.py
   & 'D:/WinAPP/Blender/blender.exe' --background --python-exit-code 1 --python Scripts/ghs/build_park_geometry.py
   ```

   首次部署时，`build_park_truck.py` 是主生成器的前置步骤；本轮补林复用已经验证的派生卡车，不重复修改卡车源。该步骤输出 `Trucks/closed_truck.blend`、闭门卡车 FBX、JSON 和三张预览。随后主生成器调用 `park_site.py`，组合道路、围栏、住宅、车辆、植被与停车模块，读取派生卡车及 `scene_overrides.json`。最终包含主 `.blend` 的 27 个共用网格卡车实例、21 个环境 FBX 与 1 个卡车 FBX、manifest、完整几何报告及预览；成功以各步骤退出码和最终 `GHS_PARK_READY` 为准。

3. 在已打开目标关卡且退出 PIE 的 UE 编辑器中应用。使用当前会话 `Scripts/ghs/live_dispatcher.py` 桥接；未启用时先在编辑器 Python 环境执行该脚本，再投递请求：

   ```powershell
   $parkRequest = @{ id = [guid]::NewGuid().ToString(); script = 'apply_park_forest_fill.py' }
   [IO.File]::WriteAllText('D:/UEPro/Test/Saved/GHS_LiveRequest.json', ($parkRequest | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
   ```

   本轮密度比较基线保存在 `Saved/ParkForestSpread/Before`；局部导入继续复用 `Saved/ParkForestFill/Before` 的原林带和编辑器保护基线，不覆盖任一修改前记录。核对同 ID 的 `Saved/GHS_LiveStatus.json` 和新生成的 `Saved/ParkForestFill/apply_report.json`。局部脚本只原位导入 `Ground`、`Landscape`、`Trees`、`TreesDark`、`TreesLight`、`Trunk` 六个 FBX，复用已有材质，不销毁或重建 Actor，不修改相机或 27 个 HISM 卡车实例。导入前后比较全部 Actor 快照，校验变换、组件材质、标签及实例参数，再保存当前关卡。首次完整部署仍使用 `apply_park_expansion.py`，不要将完整重建入口代替本轮局部应用。`scene_overrides.json` 中 Ground → `M_GHSPark_Landscape`、Blue → `M_Zcool_Cobalt` 两项用户组件材质覆盖必须保留；Ground 既有 Actor 位置 `(170,240,0) cm` 也由局部导入保留。不要重采集或覆盖修改前基线。

4. 以相同请求方式依次运行 `validate_park_expansion.py`、`capture_park_expansion.py`、`capture_park_details.py`。每项完成并核对最新报告后再投递下一项。截图使用异步回调，桥接 `executed` 仅说明已启动，必须等待截图报告自身 `success` 及文件时间更新。

5. 独立进程重载使用 `validate_park_saved.py`，实际运行回归使用 `verify_park_runtime.py`，与编辑器结构检查分别保留证据：

   ```powershell
   & 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEPro/Test/Test.uproject' -run=pythonscript '-script=D:/UEPro/Test/Scripts/ghs/validate_park_saved.py' -unattended -nop4 -NullRHI
   & 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' 'D:/UEPro/Test/Test.uproject' /Game/Maps/GHS_CAD_NormalWarehouse_ZcoolSmartFactory -game -RenderOffscreen -TwinDiagnostics -windowed -ForceRes -ResX=1920 -ResY=1080 -unattended '-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_park_runtime.py'
   ```

## 原场景保护

新增对象使用 `GHSPark_` 前缀和 `GHS_ParkContext` 标签，不带现有设备业务 `TwinId=`，不进入设备搜索或状态统计。展示卡车也不得复制 `IndependentDockTruck`、`Dock=` 标签或附加 POI／数据组件；背景关闭碰撞和 Tick。只调整当前关卡相机实例以容纳园区，不修改共享相机类默认值；旧 `/Game/Maps/GHS_CAD_NormalWarehouse` 地图应保持原哈希。

`Saved/ParkExpansion/scene_inspection.json`、`map_before.umap`、`source_map_baseline.json` 是原扩展前基线，须保留。导入前用户删除 `GHS_SiteTitle` 的证据在 `pre_import_changes.json`，不要恢复标题。验证器对其余 334 个原 Actor 的网格、材质、标签、变换与实例数据逐项比对，仅允许约定的相机变化。`Saved/ParkRefinement/Before` 是此前 CAD 细化前快照，不能当作本轮车辆植被细化后的验收结果。

本轮较密版本对比基线位于 `Saved/ParkForestSpread/Before`，局部导入保护仍使用 `Saved/ParkForestFill/Before`。导入前后所有 Actor 应一致，六个网格的几何内容是唯一修改范围。导入器只拒绝目标六网格存在未保存编辑的情况；其他未保存资产的 dirty 集合须前后相同。当前编辑器中的 7 个 Truck 材质未保存编辑不被重建或写盘，保持用户现有编辑状态。此前东北停车场版本的基线仍保存在 `Saved/ParkNortheast/Before`。当前两项用户组件材质覆盖已写入 `SourceAssets/GHS/Park/scene_overrides.json` 与 manifest：Ground 使用 `/Game/GHSZcoolSmartFactory/Park/Materials/M_GHSPark_Landscape`，Blue 使用 `/Game/GHSZcoolSmartFactory/Materials/M_Zcool_Cobalt`。Ground 的 Actor 位置为 `(170,240,0) cm`，是用户原有编辑状态；`Saved/ParkForestFill/Before/editor_snapshot.json` 与本轮 `reloaded_actors.json` 的该对象记录完全一致。用户已确认材质由本人手工修改，本轮登记和保护该状态，不把 Ground 恢复为默认材质或原点，也不修改共享 Cobalt 资产。27 台新展示卡车与原 52 台业务卡车的数量、身份、源资源哈希须分别检查。

## 本轮验收证据

**本轮疏朗扩域版本验收通过。** 相对 `Saved/ParkForestSpread/Before` 保存的较密版本（提交 `dc15e22`），五片林地扩大为 1.984 倍、平均密度降低约 60.02%。本轮生成退出码为 0；manifest 为 22 个唯一网格、987,014 面、1,373 棵树。离线报告确认原 510 棵及原几何输出保持，五片疏林为 552 棵，新树到全部林树最小中心距 10.005902 m，确定性与避让检查通过。

`Saved/ParkForestFill/apply_report.json` 确认六网格原位导入成功，没有新增或重建 Actor；全部 359 个 Actor 的快照保持。Ground 的 Landscape 组件覆盖及 `(170,240,0) cm` 位置、Blue 的 Cobalt 覆盖均保持用户既有状态；原 7 个 Truck 材质仍未保存，本轮未重建、修改或写盘。原 52 台月台业务卡车与 27 台静态展示卡车保持独立身份。

独立进程在 **2026-10-22 11:06:31（Asia/Shanghai）** 完成保存重载，`saved_validation.json.success=true`，334 个原对象和旧 NormalWarehouse 地图保持。当前地图 SHA-256 与磁盘文件一致：

```text
44951d4361864ce80854b6b2ca647b8c1bcb4a550fb0761ee4d71cc26d736c03
```

本轮实际运行回归 **14 项检查全部通过，耗时 14.297 秒**，报告绑定当前 manifest。覆盖 1920×1080／2560×1600 构图、面板收展、AGV 详情、复位清除选中、货架区／地堆区聚焦及运行不修改地图；设备／设施保持 **106 / 56**，展示卡车不进入业务身份或 POI。

**19 张细节截图**及六个森林视图已完成独立视觉复核，五片树林覆盖更广、树群更疏、空隙更自然，未见道路侵入。`Review` 已覆盖为 **24 张本轮图片**，`acceptance.json` 于 **2026-10-22 11:09:44（Asia/Shanghai）** 更新，记录 `forests.spread_revision` 中的前后面积／密度比较、用户覆盖、未保存材质状态与资产哈希。当前地图、manifest 及全部 24 张图片哈希逐项核对一致；较密版本仅作为比较基线，不作为并列的当前正式设计。

| 范围 | 证据位置与用途 |
| --- | --- |
| 当前生成结果 | `SourceAssets/GHS/Park/park_manifest.json`、`site_geometry_report.json`、`Saved/ParkForestFill/blender_geometry.log`；本轮生成退出码 0 |
| 本轮修改前基线 | `Saved/ParkForestSpread/Before`；较密版本的地图、manifest、报告与编辑器状态 |
| 原边界配准 | `Saved/ParkForestFill/region_mapping.json`、`reference_mapping_overlay.png`；约 ±10 m 的参考定位，本轮在此基础上扩域 |
| 原林带保留与新布局 | `Saved/ParkForestFill/forest_fill_verification.json`；原 510 棵及原输出保持，五片疏林最小中心距 10.005902 m，确定性检查通过 |
| 局部 UE 应用 | `Saved/ParkForestFill/apply_report.json`；六网格原位导入、全部 Actor 快照与用户材质状态保持 |
| UE 保存重载 | `Saved/ParkExpansion/saved_validation.json`、`reloaded_actors.json`；11:06:31 独立进程重载通过 |
| UE 视觉 | `Saved/ParkExpansion/capture_report.json`、`Saved/ParkRefinement/detail_capture_report.json`；本轮全景和 19 张细节截图，含六个森林视图 |
| 实际运行回归 | `Saved/ParkExpansion/runtime_report.json` 与 `Runtime_*.png`；14 项通过，耗时 14.297 秒 |
| 最终归档 | `SourceAssets/GHS/Park/Review/acceptance.json` 与 24 张图片；本轮已覆盖旧归档并核对全部哈希 |

本轮不包含重新打包 EXE。静态网格面数、离线净距及结构检查不证明多人像素流或稳定 60 FPS；本轮环境细化不替代独立性能测试。
