# MPR B50B57 外围扩建

本层使用用户提供的 `topoexport-B50B57.blend` 扩大现有 MPR 场景，沿用当前模型、材质与低对比周边风格。原始输入与许可证保存在 `inputs/`，原文件不回写。

## 保护范围

主仓内外、现有建筑、内部道路、光伏、车辆、植被、铁路、灯光与相机均保留。用户明确授权的例外仅为边界道路末端衔接带：原三个末端 Actor 保持 GUID、位置、材质、标签等字段，只替换网格引用。旧网格资源文件保持不变。

新旧交界采用实体连接，没有渐变；最外围开放道路末端保留渐变收束，不人为闭合。原布局来源是已批准的示意效果图，新输入是 GIS 数据，两者外围不能通过单个刚性变换全部重合。因此以主仓配准新增范围，衔接在旧区域以外处理；仅在原道路口存在厘米级草缝时，按逐口审计增加不超过12厘米的补面，不修改旧路面资源。不宣称整片区域是测绘级复刻。新增铁路在旧端点之外连续延伸；新增道路相交处采用同风格的展示性平交道口，不表示实测桥梁设计。

## 数据与资产

- `inputs/topoexport-B50B57.blend`：只读原始输入副本。
- `inputs/source_geometry.json`：从源 Blender 提取的世界坐标几何。
- `inputs/registration_proposal.json`：主仓16点配准与残差。
- `MPR_ExtensionB50B57.blend`、各 FBX：Blender 生成的新模型；重复树在实例清单中复用原 Nanite 模型。
- `manifest.json`：模型、只读材质、树实例和获准的三处引用替换。
- `geometry_audit.json`：保护区、逐道路连接依据、建筑与树避让、铁路和展示道口记录。
- `scene_ownership.json`：新增资源哈希、Actor GUID、原始及扩建后地图哈希。
- `validation/`：最终对应资产的验证报告与原生 UE 视图。

新增 UE 资源均位于 `/Game/MPRWarehouse/ExtensionB50B57`，演员位于 `MPR/ExtensionB50B57`。树按空间分块使用 HISM，建筑和地面按150米分块合批，复用现有材质及贴图；原场景资源不重新导入。

## 重建与验证

工具入口位于 `Tools/MPRWarehouse/`：

1. `inspect_mpr_extension_blend.py` 提取源数据；`build_mpr_extension.py` 在独立 Blender 后台进程生成增量模型。
2. `verify_mpr_extension_blender.py` 重新读取 Blender/FBX，检查单位、三角面、UV、顶点渐变及保护区避让。
3. `capture_mpr_extension_baseline.py` 在干净 UE 地图上记录全对象及依赖快照。
4. `import_mpr_extension.py` 执行首次增量导入；它会拒绝覆盖已有扩展资源，防止后续用户手动修改被无条件覆盖。
5. `validate_mpr_extension.py` 在新 UE 进程重载，核对原对象与新增 HISM 全量数据及资源哈希。
6. `capture_mpr_extension_views.py` 和 `profile_mpr_extension.py` 验证原生游戏画面与帧耗时。

**不要通过旧 V4 全量导入脚本重建本扩展。** 后续更新应先核对本层 ownership 与用户修改，按本层单独生成差异，并重新验证保护快照。原 `SourceAssets/MPR/scene_ownership.json` 本次只更新地图哈希；原资产登记不改变，新资产在本层独立登记。

性能报告是本机 UE 5.8 单实例、1920×1080、原生游戏视口采样，不代表 Pixel Streaming 网络性能或多用户服务器容量。
