# GHS Refinement V2

V2 将高货位中的整块长箱改为独立小箱垛，恢复柱边货架与地堆位，闭合外墙，并为全部装卸门增加半开门和等候货车。两套场景分别保留蓝色数字孪生与写实仓库材质：

- `/Game/Maps/GHS_CAD_DigitalTwin`
- `/Game/Maps/GHS_CAD_NormalWarehouse`

本文记录 V2 的交付规格和维护路径；实际应用是否完成以 `Saved/GHS_RefinementV2.json` 的 `success` 为准，保存后验证结果以 `Saved/GHS_RefinementV2Verification.json` 为准。导入完成不等于地图应用完成。

## 实际几何与布局

货架沿用原 CAD 层高、柱截面、宽度与深度。标准托盘为 **1.016 × 1.2192 × 0.123952 m**，叉孔、托盘板和支承块保持不变。小箱为 **0.45 × 0.55 m**，高 **0.36–0.42 m**，最长边与最短边之比最多约 **1.528**。每层四箱，横向间隙 20 mm；箱层直接接触，下层上方不悬空，4 mm 倒角和少量层间错位使分箱清晰。B 型每托盘 1 层，A/D1 型 3–4 层，C/D2 型 3 层；最小箱顶净空为 **0.170048 m**。

货架库包含 33 个兼容型号、原有全部 `mapping_key` 和 7 个材质角色。实际布局使用完整宽度型号，单个网格最高 17,412 三角面。旧窄空框只作为库兼容资产保留，不用于 V2 布局。

每张地图有 **1,629 个货架、7,530 个地堆货位、87 扇装卸门、87 辆等候货车**。70 个原始货架跨恢复为完整跨，取代 80 个切分实例，因此货架数由 1,639 变为 1,629。原先被柱占用而隐藏的 **122 个地堆位全部恢复**；25 条货架列、625 个货架平移，货架最大平移 **0.964 m**；1,044 个既有地堆位移动，涉及 96 个地堆块，最大平移 **0.754 m**。

主纵向货架通道以完整货物外包络量测，最窄为 **2.0002 m**。原有地堆块之间的通道仍最窄 **1.6764 m**；不能把 V2 描述为所有通道均达到 2 m。原地堆块外矩形和行的 Y 位置保留，货架背靠背最小净距约 **0.3048 m**。这些是几何审计值，不代替运营通道设计规范。

外墙按原 CAD 周界闭合，墙厚 **0.254 m**、墙及柱高 **9.6 m**；保留内部平面和无屋顶的剖切展示方式，**不新增屋顶**。87 个门洞各有门楣，门高 **4.2 m**，半开后的下部通行净高 **2.1 m**。门板宽 **2.794 m**，含框总宽约 **3.04165 m**；门板两面均使用门板材质，无整块黑色背板。

每个门外布置一辆货车，车尾对准该门的装卸目标、车头朝建筑外。货车按通用中型厢式货车建模，**尺寸为估计值，非车辆实测或 CAD 尺寸**：车身宽约 **2.58 m**，含后视镜宽 **3.0 m**；导出网格完整外包络长约 **8.9035 m**、高约 **3.7415 m**。布置碰撞检查包含后视镜和车头外包络。

## 文件与证据

路径均相对项目根目录 `D:/UEPro/Test`。

| 内容 | 入口 |
| --- | --- |
| V2 预备注册表 | `SourceAssets/GHS/RefinementV2/revised_registry.json` |
| 货架与地堆布局、位移及通道值 | `SourceAssets/GHS/RefinementV2/Layout/rack_spacing.json` |
| 布局独立检查 | `SourceAssets/GHS/RefinementV2/Layout/rack_spacing_validation.json` |
| 小箱货架 manifest、FBX 和可编辑 Blender | `SourceAssets/GHS/RefinementV2/Racks/refined_rack_cargo.json` |
| 全部 FBX 回读与可编辑性检查 | `SourceAssets/GHS/RefinementV2/Racks/fbx_roundtrip_validation.json`、`blend_editability_validation.json` |
| 外墙与半开门 | `SourceAssets/GHS/RefinementV2/Envelope/envelope_v2.json` |
| 各门朝向与车尾目标 | `SourceAssets/GHS/RefinementV2/Envelope/door_docking_targets.json` |
| 货车资产及估计尺寸 | `SourceAssets/GHS/RefinementV2/Trucks/dock_truck_v2.json` |
| V2 前快照与备份索引 | `Saved/GHS_RefinementV2Checkpoint.json` |
| 导入记录 | `Saved/GHS_RefinementV2Import.json` |
| 地图应用、修改哈希和回滚索引 | `Saved/GHS_RefinementV2.json` |
| 独立空间审计 | `SourceAssets/GHS/RefinementV2/Envelope/scene_geometry_audit.json` |
| 从磁盘重载两张地图的验证 | `Saved/GHS_RefinementV2Verification.json` |

当前 V2 前备份目录是 `Saved/Backups/GHS_CADRacks_20261016_140702`。备份包含地图、注册表和历史报告；恢复时以 checkpoint 的逐文件路径、SHA-256 与应用报告的 `changed_files` 为准，不覆盖该备份。新导入资产位于 `/Game/GHSRefinementV2`，保留旧 CAD 资产用于历史与回滚。

## 维护入口

`Scripts/ghs/cad_rack_revision_state.py` 优先读取 `Saved/GHS_RefinementV2.json`，再检查已保存注册表的 `refinement_v2` 标记。V2 报告存在但未完成、或者标记存在而报告缺失时，旧重建与旧验证均拒绝继续，避免回落至旧场景或覆写历史证据。不能删除标记绕过保护。

明确执行旧验证入口（包括 `verify_cad_rack_revision.py` 的 `__main__` 路径）时，完整 V2 会转交 `verify_refinement_v2.run()`。仅导入旧模块作为辅助函数库时不会派发验证，不产生循环导入执行。V2 验证器重载两张已保存地图，核验实例、材质、边界、门车对齐、文件哈希及历史报告保护；只写新的 V2 验证报告，不保存地图或资产。

执行顺序是：`backup_refinement_v2.py` 先建立快照，`import_refinement_v2.py` 导入版本化新资产，`apply_refinement_v2.py` 应用两图，最后以独立 UE 进程运行 `verify_refinement_v2.py`。布局与资产变更须先重新生成并审计对应 manifest，再按新的检查点处理；不要直接重复旧通用重建脚本。各报告的成功状态必须逐步确认，不能仅凭 PNG 预览或导入记录确认场景已完成。

## 本次保存验证

2026-10-16 已同步保存两张地图。Blue 为236个Actor，Normal为238个Actor；各27个HISM组、13,849个实例。独立UE进程逐一重载校验通过（`GHS_RefinementV2VerificationAccepted.log`：0错误、0警告），旧Content除两张地图外全部保持原哈希，90份历史报告保持原哈希。新资产共52件（38个网格、14个货车材质），货车实例化材质使用标记已持久化。

四个墙门网格已补齐UV和显式法线/切线；最终重导日志`GHS_RefinementV2UVImportVerified.log`为0错误、0警告。仅清理25个零面积多边形，非零表面和材质分配完全保持。已有地堆倒角后的实际边界比CAD名义外包络小最多1.61mm，本次没有再次缩放地堆来避让柱子。

两图各11张1920×1080 UE实拍已完成，拍摄后两图哈希不变。截图为`Saved/GHS_RefinementV2_{Normal|Blue}_UE_*.png`，视觉核验索引为`Saved/GHS_RefinementV2VisualReview.json`。已检查箱垛比例、柱边间隙、门楣、转角闭合、门板两面和车尾对齐；蓝色版本保持原有半透明墙体，浅色版本保持实体墙材质。
