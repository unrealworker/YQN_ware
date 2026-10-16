# 物流仓储园区使用说明

这是按通用物流园区尺度制作的静态场景，包含装卸仓库、办公楼、月台、货架及托盘、车辆、道路、围栏、门岗与绿化。

## 在 Unreal Editor 中查看

- 地图：`/Game/Maps/LogisticsWarehouse`。
- 导入网格：`/Game/LogisticsWarehouse/Meshes`；材质：`/Game/LogisticsWarehouse/Materials`。地面等部分设施使用引擎基础网格，材质细节使用项目已有的 StarterContent 纹理。
- 在世界大纲视图中找到 `WH01_RemovableRoof`，点击可见性图标隐藏屋顶，即可检查仓库内部货架、托盘及钢结构。需要时重新显示该对象；仓库主体无需隐藏。
- 预设相机：`CAM_Overview`（园区总览）、`CAM_Loading`（装卸区）、`CAM_Gate`（入口）、`CAM_Interior`（仓库内部）。在大纲视图选中相机并使用“Pilot/驾驶”查看；内部相机可以保留屋顶查看天窗采光。

## 数字孪生数据接口

主要场景对象使用独立名称，并带有 `TwinId=<对象编号>` 标签。`twin_asset_registry.json` 记录对象编号、分类、模型、以米为单位的位置等信息，可作为后续关联库存、车辆和设备数据的索引；场景构建脚本会重新生成此文件。

当前未连接实时数据，也未实现车辆运动或植被风动。车辆、货架和植物均为静态摆放；标签与索引为后续接入预留。

本版采用太阳光、物理天空、实时天光、Lumen、园区路灯和室内补光。车辆与建筑为程序化建模资产；道路和仓库地坪有基础碰撞，详细网格未配置完整行走碰撞或导航。树木尚未设置风动和多级 LOD。

## 源资产与复现

本目录保存 `SM_*.fbx` 以及四份网格/材质清单：`architecture.json`、`vehicles.json`、`vegetation.json`、`site_details.json`。建筑源资产包含独立仓库主体、屋顶、办公楼和货架；其余清单分别组织车辆/托盘、树木和园区设施。`*_preview.blend`、`*_preview.png` 为资产制作阶段的源场景及预览，不代表 Unreal 地图的最终效果。

工程根目录下的复现脚本：

- `Scripts/warehouse_assets/common.py`：Blender 共用材质、几何及 FBX 导出辅助函数。
- `Scripts/warehouse_assets/architecture.py`、`vehicles.py`、`vegetation.py`、`site_details.py`：分别通过 Blender 后台模式生成对应资产及清单。
- `Scripts/build_logistics_warehouse.py`：在启用 Python Editor Script Plugin 的 Unreal Editor 中执行，导入源资产、创建材质并组装上述地图；运行时会更新该地图和对象索引。
- `Scripts/verify_warehouse_editor.py`：供 Unreal Editor 中检查地图和资源使用。

先用 Blender 执行四个资产生成脚本，再在本项目 Unreal Editor 中执行场景构建脚本。脚本当前使用工程绝对路径 `D:\UEPro\Test`，迁移到其他机器时应先调整相应路径，并确保项目保留 StarterContent。
