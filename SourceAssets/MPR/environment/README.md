# MPR 周边环境源资产

本目录只负责周边道路、铁路、辅助建筑体量、装卸硬地、停车和绿化。主仓建筑、室内模型与 UE 关卡由上一级 MPR 场景生成器组装；不包含页面开发。

## 数据与尺度

- 原始资料：用户提供的 `cadmapper-carteret-new-jersey-us.dxf` 及同目录 8 张实景参考。原文件只读；此处保留 DXF 副本，SHA-256 写入 `environment_geometry.json`。
- CADMapper 的 `INSUNITS=4` 声明与实物尺度不一致，**原始坐标按米**解释。主仓 footprint 面积为 56,250.766 m²，与业主公开的 607,400 sq ft（约 56,429 m²）相符。
- 主仓对应 CADMapper 建筑 `1583`；环境资产排除此建筑，避免与主仓精确模型重复。邻仓为 `1582`。
- 主 CAD 为英寸制，采用 `(12800,8000)` 原点、`0.0254` 米/单位。两份数据使用 16 对轮廓点作无缩放、无镜像的刚体拟合；RMS 误差 0.5846 m，最大 0.8980 m。主仓最终轮廓以主 CAD 为准。
- `environment_geometry.json` 保留原始坐标；`environment_local.json` 已变换到主 CAD 局部米制，**保留 CAD +Y**。Blender FBX 使用 `-Y` forward / `Z` up，按现有导入流程由 UE 坐标转换反射 Y。
- 环境地面 z=-1.2 m，主仓地坪 z=0。该码头高差是参考图推定，不是测量结果。原 CADMapper 的建筑挤出高度统一为 3 m，占位数据不可作为真实高度。

## 复用与优化

- 树木复用 `Scripts/ghs/park_vegetation.py` 的 3 种 GHS 树形生成器；汽车复用 `park_vehicles.py` 的 sedan/SUV 生成器。保留 GHS 灰蓝工业风格，不搬入整块 GHS 场地，也不复制绑定 GHS 世界坐标的遮罩材质。
- 道路、背景建筑和铁路的修订配色由 MPR 自己拥有的四参数 Default Lit 主材质及 17 个实例统一实现，参数为 `SurfaceTint / Roughness / Metallic / Specular`。外场实例不再借用共享 GHS 父材质的节点参数来调色；原 GHS 文件不改写。另有 10 个 HISM 兼容实例继续继承原 GHS 材质，仅开启 UE 5.8 的实例化使用标记，两组实例不能混为一类。
- 当前 `environment_manifest.json`：67 个 FBX，共 179,690 个独有三角面、95 个累计材质槽。环境按近场和东/西/南/北远场分批，地面为 25 块 280 m 网格；这些是源资产统计，不代表 UE 运行性能。
- 3 种树模型供 355 个实例共用；2 种汽车模型供 37 个实例共用，共 392 个实例。`instance_only` 模型只通过 manifest 的 `instances` 放置，不应额外在原点生成实体。
- 140 栋背景建筑保留配准后的原始位置与轮廓，按照片增加有限的坡顶、立面分缝、装卸侧剪影和屋面设备，并降低背景亮度以突出主仓。各栋高度、坡度和细节为展示估计，以 manifest 的逐栋记录为准，不能作为现场测量值。详见 `context_buildings_review.md`。
- 近场道路采用连续圆角与标线，表面按道路/院落范围合并。Port Reading 北段 CAD `Y>355 m` 保留源道路 `16c6`；`Y=335～355 m` 为与源边界衔接的过渡段，不继续向北外推近场控制线。
- 停车绿岛先裁切到停车地块，并扣除道路合并范围外扩 0.25 m 的区域，再统一生成绿地、铺装孔洞与种植中心。所有树位按树冠检查铺装、建筑、水面及铁路避让，不仅检查树干中心。
- 铁路保留源路径和连接关系，细化双轨、道床与枕木，远处枕木稀疏化，按区域合并。钢轨截面、轨距、枕木间距与静态罐车编组是视觉参数，不是铁路工程或实时车辆数据。环境物件默认不生成碰撞。
- 停车标线、装卸硬地、树木位置为参考图重建，不宣称测绘精度。当前 140 个展示停车格只对应模型绘制区域，不代表全园区实际总量。

## 重建

从项目根目录依次执行：

1. Python 运行 `Tools/MPRWarehouse/mpr_environment_extract.py`（Pillow）。
2. Python 运行 `Tools/MPRWarehouse/mpr_environment_align.py`（NumPy）。
3. Blender 后台运行 `Tools/MPRWarehouse/build_mpr_environment.py`（Shapely >=2.1）。本机复用 `Saved/ParkRefinement/python_deps` 的既有 Shapely；其它机器需为其 Blender Python 配置该依赖。
4. Blender 后台运行 `Tools/MPRWarehouse/mpr_environment_validate.py`。

交付入口为 `environment_manifest.json`；`MPR_Environment.blend` 保留可编辑环境和共享实例。`environment_overview.png` 仅为环境检查图，因此主仓位置有意留空。

当前 `environment_validation.json` 记录 67 个 FBX 回导通过，坐标最大差 `0.00007127 m`，实例数 392、独有三角面 179,690；这是源资产单位、边界和材质槽检查，不是本次 UE 画面或运行性能验收。上一版截图和运行报告不自动适用于本次修订。完整说明与估计边界见上级 `EXTERIOR_REVISION_2.md`，UE 最终关卡验证由总场景流程补全。

地图几何来自用户提供的 CADMapper / OpenStreetMap 数据，地图数据署名：© OpenStreetMap contributors，https://www.openstreetmap.org/copyright 。用户实景截图仅作为造型依据，没有用作贴图或再分发。
