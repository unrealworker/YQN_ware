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

- 树木完全复用 `Scripts/ghs/park_vegetation.py` 的 3 种 GHS 树形生成器；汽车复用 `park_vehicles.py` 的 sedan/SUV 生成器与角色材质。
- GHS 园区调色来自 `SourceAssets/GHS/Park/reference_style.json`。没有搬入整块 GHS 场地，也没有复制绑定 GHS 世界坐标的遮罩材质。
- 60 个 FBX，共 22,000 独有三角面、78 个材质槽。环境按近场和东/西/南/北远场分批，地面为 25 块 280 m 网格。
- 3 种树模型供 180 个实例共用；2 种汽车模型供 31 个实例共用。`instance_only` 模型只通过 manifest 的 `instances` 放置，不应额外在原点生成实体。
- 140 栋背景建筑仅保留轮廓与屋顶体量；邻仓 14 m、其它工业建筑 9 m、住宅 6 m、小屋 3.2 m 均为明确记录的估计。
- 道路、铁路分叉和绿带共面区域已经合并三角化，避免 CADMapper 分离几何造成黑斑与闪烁。环境物件默认不生成碰撞。
- 停车标线、装卸硬地、树木位置为参考图还原，不宣称测绘精度。182 个展示停车格不是业主公布的全园区 362 格总量。

## 重建

从项目根目录依次执行：

1. Python 运行 `Tools/MPRWarehouse/mpr_environment_extract.py`（Pillow）。
2. Python 运行 `Tools/MPRWarehouse/mpr_environment_align.py`（NumPy）。
3. Blender 后台运行 `Tools/MPRWarehouse/build_mpr_environment.py`（Shapely >=2.1）。本机复用 `Saved/ParkRefinement/python_deps` 的既有 Shapely；其它机器需为其 Blender Python 配置该依赖。
4. Blender 后台运行 `Tools/MPRWarehouse/mpr_environment_validate.py`。

交付入口为 `environment_manifest.json`；`MPR_Environment.blend` 保留可编辑环境和共享实例。`environment_overview.png` 仅为环境检查图，因此主仓位置有意留空。

验证：所有 60 个导出 FBX 回导坐标、材质槽数量均通过；最大坐标误差 0.00006104 m。预览已检查道路交叉处无共面黑斑。UE 最终关卡验证由总场景流程进行。

地图几何来自用户提供的 CADMapper / OpenStreetMap 数据，地图数据署名：© OpenStreetMap contributors，https://www.openstreetmap.org/copyright 。用户实景截图仅作为造型依据，没有用作贴图或再分发。
