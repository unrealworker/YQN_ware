# YQN 全球仓库入口 · 地球资产

该资产由 Blender 5.2.2 LTS 独立后台进程制作，不覆盖用户已打开的 Blender 场景。大陆、湖泊、冰川、国界及地形均来自真实地理资料，没有随机拼接陆地轮廓。绿色/沙色为匹配参考图的地图配色，不是实时遥感影像。

## 文件与优化

- `YQN_Earth.blend`：可编辑源文件，贴图已打包；含美洲主视角、灯光、3级模型和地理校准点。
- `SM_Earth_LOD0.fbx` / `LOD1` / `LOD2`：65,024 / 16,128 / 3,968 三角面；每级单物体、单材质。
- `Textures/T_Earth_BaseColor.png`：4096×2048，真实地理配色、国界、15°经纬网合并为一个颜色贴图，减少独立网格与绘制批次。
- `T_Earth_Normal_UE.png`：Unreal / DirectX 法线；`T_Earth_Normal_OpenGL.png` 仅供 Blender；法线、粗糙度关闭 sRGB。
- `earth-americas.png`：1400×1400 透明背景渲染，无文字、无 UI，可供 Figma 独立图层使用。
- `render-projections.json`：由 Blender 实际相机矩阵计算的归一化屏幕坐标，包含 GHS 与参考国家名称锚点。左上为 (0,0)。
- `GeographicCalibration.fbx`：四个具名校准小球，供引擎导入轴向验证，不应加入发行关卡。

基础球半径为 Blender 1 米，即 UE 100 厘米。地形高度及陆地抬升合计最高为半径的 2.4%，为地图可读性做了夸张；这是地形示意，不用来量测海拔。地球标签与 POI 由浏览器和运行时投影，未烘焙进贴图，便于多语言与多仓库扩展。关卡的自转和鼠标操作由 UE 运行时控制，源模型不带强制循环动画。

## 地理坐标与导入

建模坐标为 `X=R*cos(lat)*cos(lon), Y=R*cos(lat)*sin(lon), Z=R*sin(lat)`，北极 +Z、零经线 +X、东经90° +Y。UV 为 `u=(lon+180)/360, v=(lat+90)/180`；PNG 第一行是北极。FBX 导出 `axis_forward=-Y, axis_up=Z` 并写入单位元数据。UE 会执行左右手系转换，导入时须用 `GeographicCalibration.fbx` 的控制点验证轴转换，不能假设 UE 导入坐标与 Blender 完全相同；运行时 POI 必须采用与地球相同的校准变换。

UE 5.8.4 使用 `FbxFactory` 的实测结果为：零经线 `(100.3, 0, 0)`、东经90° `(0, -100.3, 0)`、北极 `(0, 0, 100.3)`、GHS `(-38.48258, 74.15034, 56.75477)`，单位均为厘米。导入变换为 `(x, y, z) → (100x, -100y, 100z)`，其中源坐标以米计。这是从 Blender 右手系转换到 UE 左手系的自然变换，不能再给地球加负 Y 缩放，否则画面大陆会左右镜像。地球 Actor 使用正缩放 `(100, 100, 100)` 放大展示，UE 运行时的经纬度公式采用 `X=R*cos(lat)*cos(lon), Y=-R*cos(lat)*sin(lon), Z=R*sin(lat)`；相机方位也须使用同一左手系。成功导入后的网格包围球半径约 `102.74065 cm`，已加载 3 个 LOD；包围球半径包含包围盒中心偏移，不等同于从球心量取的最高地形半径。

`check_axes.py` 将四个校准网格导入 `/Game/Developers/GlobeValidation`，仅作为编辑器验证资产，不被入口关卡引用。打包应保持排除 Developers 内容。`ue-axis-report.json` 记录实际控制点中心；`ue-import-report.json` 记录实际网格尺寸、LOD 顶点/三角面计数、FBX 导入类型和单位/轴设置。

美洲渲染相机位于经度 -84°、纬度 17°方向，正交宽度2.17米。基于上述相机，GHS 在最终 PNG 的归一化坐标是 (0.28791434, 0.34382385)。

## GHS 地址核实

用户指定地址：17335 Glen Helen Pkwy, San Bernardino, CA 92407, USA。

查询日期：2026-10-31。Esri World Geocoding Service 返回 **PointAddress、匹配分100**，WGS84 / EPSG:4326：

- 纬度：**34.190629582941°**
- 经度：**-117.428430792609°**

原始响应在 `Geodata/warehouse-arcgis.json`。另取 [OSM 建筑 way 521644442](https://www.openstreetmap.org/way/521644442)，其门牌、街道、城市、邮编与用户地址一致；点在该建筑多边形内部，重建脚本执行 point-in-polygon 断言。OSM 历史承租方名称为 Nordstrom，该名称只用于地址交叉核对，不作为当前 GHS 运营主体证据。该位置是地址级地理编码结果，不是测量控制点；没有用 San Bernardino 城市中心代替。

## 地理资料来源与许可

- [Natural Earth I](https://www.naturalearthdata.com/downloads/50m-raster-data/50m-natural-earth-1/)：基于卫星覆盖数据的地表配色和地形阴影。50m 国家、湖泊、冰川矢量来自 [Natural Earth 官方维护仓库](https://github.com/nvkelso/natural-earth-vector)。[Natural Earth 地图数据为公有领域](https://www.naturalearthdata.com/about/terms-of-use/)。地图国界采用该源的绘制方式。
- [NASA Blue Marble Topography](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/topography-bathymetry-maps/)：5400×2700 GEBCO 陆地地形图，值域0～6400m。Credit: NASA Earth Observatory / Jesse Allen, GEBCO / British Oceanographic Data Centre。
- 建筑几何：© OpenStreetMap contributors，[ODbL 1.0](https://www.openstreetmap.org/copyright)。原始响应及其许可字段保留在 `Geodata/warehouse-osm.json`。
- Esri 地址查询原始响应保留供核对，仅用作本次指定地址定位，不作为独立批量地址数据库。

所有下载 URL、字节数和 SHA256 在 `Geodata/sources.json`。175MB 的原始 TIFF 及40MB下载包保留本地但通过局部 `.gitignore` 排除，发行资产不依赖在线地图服务。

## 重建

1. 用带 Pillow / NumPy 的 Python 执行 `Tools/GlobeNavigation/fetch_geodata.py`，下载并记录地理来源。
2. 执行 `prepare_textures.py`，生成纹理并核对 GHS 地址分数、匹配类型及建筑包含关系。
3. 执行 `blender --background --factory-startup --python Tools/GlobeNavigation/create_globe.py`，生成独立 .blend、三组 FBX、投影 JSON 与透明渲染。
4. 先编译 UE 5.8 的 `TestEditor`，再用完整编辑器执行 `run_import.py`，依次运行轴向验证和正式导入。不能使用 `-run=pythonscript` commandlet，因为它不初始化所需的编辑器子系统。

在项目根目录的 PowerShell 中运行（引擎安装目录不同可调整首个路径）：

```powershell
& 'D:\UE\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'D:\UEPro\Test\Test.uproject' '-ExecutePythonScript=D:\UEPro\Test\Tools\GlobeNavigation\run_import.py' -unattended -nosplash
```

该独立编辑器进程完成脚本后退出。运行前先保存正在编辑的项目内容，并避免多个编辑器同时写入这些资产。脚本仅重建专用入口地图中带 `GHS_GlobeStage` 标签的展示 Actor，不重存现有仓库地图。重复导入显式绑定本地 FBX 源文件，并更新旧资产保存的单位/轴设置；缺少源文件立即报错，不等待文件选择框。导入期间临时关闭 FBX Interchange，覆盖 LOD0、重导和 LOD1/2，成功或异常后均恢复原值。运行时、实际画面与切仓流送验收须另行执行，导入成功不代表这些环节已经验收。

Python 下载器仅使用本机显式代理 `127.0.0.1:7897`，其他机器可通过 `GHS_GLOBE_HTTPS_PROXY` 指定；设为空字符串可直接联网。不包含任何凭据。
