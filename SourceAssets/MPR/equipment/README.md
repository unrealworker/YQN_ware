# MPR 分拣设备资产

本目录为独立背景 Blender 生成的可编辑设备资产，没有修改用户打开的 Blender 或 UE 场景。

## 资产与 CAD 摆位

| 资产 | 计划摆位 | 建模格口数 | LOD0 / 1 / 2 三角面 |
|---|---:|---:|---:|
| SM_MPR_Tiangong96 | 不自动摆放，资料库 | 12 列 × 4 层 × 双侧 = 96 | 17620 / 12820 / 6660 |
| SM_MPR_SorterCAD64 | 18 | 8 列 × 4 层 × 双侧 = 64 | 7856 / 5632 / 3256 |
| SM_MPR_SorterCAD120 | 4 | 15 列 × 4 层 × 双侧 = 120 | 13328 / 9840 / 5448 |
| SM_MPR_SorterShort10 | 30 | 5 列 × 1 层 × 双侧 = 10 | 2092 / 1300 / 868 |

CAD 的横向列数和 96 格设备资料存在版本差异，因此保留独立型号。长机的 4 层和短机的 1 层为依据设备形式的场景建模假设，2D CAD 没有证实实际垂直层数和高度；表中数字不是实际安装容量的确认。

96 格装配手册明确 8 组推车、每组 3 × 4 格。推车宽 1.44m、深 0.505m、高 1.687m、层距 0.445m、管径 28mm、脚轮直径 63mm、溜槽 20°。整机约 9.8 × 2.768 × 2.465m 为照片重建，不是厂商总图尺寸。`sorter_manifest.json` 保留来源与文件 SHA256。

`sorter_instances.json` 为 CAD 米制坐标（源原点 [12800,8000]，比例 0.0254），未做 UE Y 翻转。每个模型 X 为长轴，原点位于平面中心地面。父导入器负责转成 UE 厘米，并进行项目统一的 Y 轴转换。

18 支机来自 `14234123` 爆炸线框的侧部 Y 占用区间；4 支机来自 `480` 的精确嵌套 INSERT 边界；30 短支机来自小黄人 4 个父块的真实边界（7/7/8/8 行）与 1.9499961m CAD 重复节距，不是逐个读取独立子块。统计已和 CAD 预览核对。来源和端点保留在 `sorter_cad_groups.json`、`sorter_child_bounds.json`。

CAD 适配模型的外壳相对 CAD 包络约内缩 2～30mm，避免边缘附件超出布局轮廓。端柜、屏幕、驱动结构和垂直尺寸属于外观重建。

## UE 导入与性能

- `sorter_manifest.json`：96 格资料机与三档 LOD。
- `sorter_variants_manifest.json`：三个 CAD 型号与三档 LOD。
- 每个 FBX 只有一个合并 Mesh、固定 7 个材质槽；材质顺序为 Porcelain / Cobalt / SoftBlue / Metal / Charcoal / Rubber / Glass，映射到现有 `/Game/GHSZcoolSmartFactory/Materials/M_Zcool_*`。
- 保存米制、FBX `-Y forward / Z up`，导入 scale=1。LOD1、LOD2 FBX 应导入为 LOD，不作为额外设备摆放。建议屏幕比例 1 / 0.22 / 0.065。
- 同型号重复机器用 HISM；不要逐料框生成 Actor，不添加 Tick，不给装饰零件创建碰撞。
- 独立 `.blend` 保存语义零件和各档 LOD；导出 FBX 才合并。资产不含生产运行状态或自动运动。

## 验证与复现

`Tools/MPRWarehouse/validate_mpr_sorter_fbx.py` 在独立 Blender 中回读全部 12 个 FBX，验证单 Mesh、三角面、材质顺序、边界、有限顶点和地面原点。结果见 `sorter_fbx_validation.json`，12 项通过；此项不代替 UE 导入后检查。

生成脚本：`build_mpr_sorter.py`（96 格）、`build_mpr_sorter_variants.py`（CAD 变体）。CAD 只读解析：`extract_mpr_sorter_placements.py`、`inspect_sorter_children.py`，再运行 `finalize_mpr_sorter_placements.py`。所有脚本位于 `Tools/MPRWarehouse`，使用 `blender --background --factory-startup --python ...`；CAD 脚本使用包含 ezdxf 的 Python 3.12 运行环境。
