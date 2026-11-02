# MPR 外景替换的内部保留边界

本次只替换外壳、屋顶、月台外门、外场、背景和外景灯光。内部布局不重建，内部 Actor 不销毁、不重命名、不迁移目录，也不对其 HISM 组件写入属性。

实际 UE 编辑器只读基线共 399 个 Actor：136 个内部 Actor、261 个旧外部 Actor、2 个现有相机。136 个内部 Actor 包含 4,441 个实例；其 45 个项目资产依赖（网格、材质、材质父级、蓝图）另外记录文件 SHA-256。采集时地图和内容包均无未保存改动。

| 必须保留 | Actor 数 | 实例数 |
|---|---:|---:|
| `MPR_Floor`、`MPR_OfficePartitions`、`MPR_OfficeGlazing` | 3 | 静态网格 |
| `MPR/Architecture/Columns` 的柱与柱脚 | 36 | 328 |
| `MPR/Storage/Racks` 全部货架，含 192 英寸型号 | 27 | 2,867 |
| `MPR/Storage/Floor` 地堆货物 | 8 | 165 |
| `MPR/Operations` 全部作业设备，含共享 GHS 坡道输送机 | 57 | 1,029 |
| `MPR/Equipment` 木马及短支机 | 5 | 52 |

逐对象 GUID、标签、目录及网格清单见 `interior_boundary.json`。原始完整基线归档为 `interior_before.json.gz`，与 `Saved/MPR/reference_v3_interior_before.json` 解压后数据完全相等；指纹为 `4f04d58a0e87fc58ebd1153eed4436b8f1e481a3a0572fac084113f013dbbbab`。完整基线保留 Actor 身份、变换、附着关系、可见性、Tick/碰撞、组件类别、组件变换、材质、HISM 数量、按索引排列的全部实例变换及自定义数据。

旧 `MPR_Exterior_00..15`、`MPR_Roof*`、`MPR/Architecture/Docks`、原 `MPR/Environment` 和 4 个原外景灯光 Actor 可替换。删除必须使用基线中明确标注 `old_exterior` 的 GUID 集，不能根据宽泛的 `MPRWarehouse` 标签删除。

`MPR_WarehouseCamera` 和 `MPR_ReviewCamera` 的身份与原有相机逻辑保留，可调整外景构图。未知或用户添加的 Actor 默认保护，即使位于 MPR 文件夹也不能自动删除。新外景 Actor 使用 `mpr-reference-exterior-v3` 标签和 `MPR/ReferenceV3` 文件夹。

保留校验在导入前、保存前、独立 UE 进程重载后分别执行。内部数量相同并不代表通过：替换 GUID、单个实例位置或顺序变化、同路径资产重导入都必须报错。截图验收临时隐藏新屋顶并恢复，不保存地图，不改变基线。

验证入口：`Tools/MPRWarehouse/test_mpr_interior_preservation.py` 的 14 项无 UE 回归测试；`Tools/MPRWarehouse/validate_mpr_reference_exterior.py` 的独立重载与八视角截图。本文仅记录边界与基线，不能代替最终 UE 重载验收报告。
