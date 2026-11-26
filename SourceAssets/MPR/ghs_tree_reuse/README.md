# MPR 复用 GHS 树模型

原关卡 `/Game/Maps/MPR_CAD_Warehouse_B50B57` 的 64 组、1002 棵树已替换。单树直接调用 GHS 园区实际使用的 `Scripts/ghs/park_vegetation.py::build_tree`（变体 0）生成，保留五团圆润树冠及树干分枝结构。GHS 的原树网格按全园区合批，因此提取同源单树复用，没有改变 GHS 资产。

统一放大到原 MPR 单树的 6.418 米树冠半径，根部落在模型 Z=0；保持 GHS 自身比例，基准高度由原 15.864 米变为 13.644 米。实例原有缩放保持，各棵树的实际高度随原实例缩放变化。原来的布点、旋转、材质槽和园区颜色遮罩全部保留。

单树为 1856 三角面，原模型为 11292 面，减少 83.56%。继续使用 HISM 实例化，启用 Nanite；该数字仅代表几何数量变化，不是帧率测试结果。UE 导入时省略两个未使用槽，应用脚本明确核对有效槽顺序后恢复 MPR 四槽绑定。

`manifest.json` 记录源代码、FBX 哈希及 Blender 往返验证；`verification.json` 记录实际保存和独立重载结果。925 个 Actor 全量核对通过，其中 861 个非树 Actor 不变。前后近景为同一相机、1920×1080 的原生运行截图，另保留替换后全景。没有生成逐帧序列。

生成入口：`Tools/MPRWarehouse/build_ghs_tree_reuse.py`（Blender）。应用入口：`Tools/MPRWarehouse/apply_ghs_tree_reuse.py`（独立 UE Python commandlet，按顺序使用 `-own -TreeAudit`、`-own -TreeApply`、`-own -TreeVerify`）。捕获入口：`Tools/MPRWarehouse/capture_ghs_tree_reuse.py`（独立原生运行，`-TreeBefore` 选择替换前）。应用脚本在保存前完整检查场景差异；已应用的场景应使用 Verify，不重复 Apply。
