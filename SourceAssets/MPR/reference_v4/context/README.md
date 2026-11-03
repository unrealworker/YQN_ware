# MPR 周边建筑：2026-11-03 平面图修订

本目录只生成外部周边建筑，不修改主仓 CAD 或内部。最新来源为 `references/building-road-outline-20261103.png`（1728 × 910）；`reference_context_plan_v5.json` 记录独立提取的建筑轮廓。坐标使用 `site/plan_registration_v5.json`，新模型不使用旧透视反投影。住宅、斜向建筑分别建立正交局部坐标，仅旋转和平移，不把像素非等比变换应用于完整网格。

当前包含 132 栋住宅、11 栋非住宅建筑、8 个圆形储罐。保留左上与西侧真实 L 形轮廓；邻仓高度为 17 m，28 个装卸口具有真实 3.4 m 凹腔。建筑高度、不可见立面细节仍是合理估计，不作为测绘数据或“视觉 1:1”证明。

## 重建顺序

1. 用带 NumPy/Pillow 的 Python 运行 `Tools/MPRWarehouse/extract_mpr_plan_context.py`，核对 Saved/MPR/road_v5 中的提取结果后，将已确认清单保存为本目录的 `reference_context_plan_v5.json`。
2. 用 Blender 后台运行 `Tools/MPRWarehouse/build_mpr_reference_context_v4.py`（建议 `--threads 1 --python-exit-code 1`）。
3. 用 Blender 后台运行 `Tools/MPRWarehouse/validate_mpr_context_orthogonality.py -- --blender --output SourceAssets/MPR/reference_v4/context/orthogonality_validation.json`；重新打开正式 blend 核对保存后的顶点。
4. 用带 NumPy/Shapely 的 Python 运行 `Tools/MPRWarehouse/validate_mpr_reference_context.py`，检查 FBX SHA、LOD、材质、图源、注册与罐体半径。
5. 单独运行 `Tools/MPRWarehouse/render_mpr_plan_context.py`，检查住宅正反低视角、邻仓月台与 L 形建筑。渲染与 UE 不并行占用 GPU。

生成依赖 `mpr_context_rectification.py`、`mpr_plan_layout.py`、`mpr_plan_site.py`、`mpr_blender_common.py`、`Scripts/ghs/park_curves.py` 与匹配 Blender Python ABI 的 Shapely。旧透视模式保留供历史重现，只有缺少新 plan 清单时才会启用。

## 导入接口

只按 `manifest.json` 的 `meshes`、`lod_files` 和 `materials` 导入。目录里可能存在历史实验 FBX，未被清单引用的文件不是当前交付依赖。

`footprints_m` 是建筑和罐体的平面范围；`paved_footprints_m` 是按最新道路裁切后的罐区铺装，场地主生成器应把它纳入树木和草地排除。所有 LOD0 均为米制世界空间静态网格，`instances` 为空；LOD1 只供 LOD 导入，不生成重复场景物体。住宅按约 150 m 空间单元合批：29 个 LOD0 网格、45 行全部 LOD，共 67,843 / 76,411 三角形。储罐使用真实圆柱；像素半径换算为注册 X/Y 尺度的几何均值，保持面积而不拉成椭圆。

紧邻住宅保留中心，必要时局部等比缩小；道路附近只作记录在 `road_setback_adjustment` 中的小范围退让。完整屋檐、檐条、门廊与车库包络均包含在住宅净距审计中。当前保存后的模型最小净距为 3.10 m，零互穿、零压路；屋顶共面、墙竖直与八个罐体圆度均通过。低角度前后遮挡仍可能出现，不等于实体相交。

当前保存几何证据为 `orthogonality_validation.json`、`validation.json` 与根目录 `../validation/context_geometry_validation.json`：按 manifest 的分栋顶点范围检查实际合批网格，并核对交付依赖与来源哈希。最终可见效果以本轮真实 UE 游戏视图 `../validation/plan_views/10-houses-close.png`、`11-houses-reverse.png`、`12-neighbor-docks.png`、`13-east-context.png` 及其 capture report 为准，来源绑定见 `../validation/plan_validation_archive.json`。旧 `plan_validation/01…05` Blender 图已过期，应排除出本轮候选证据；旧透视截图和旧邻仓图也不代表当前结果。

罐区基础按最新封闭外轮廓恢复，图纸底边裁切处向外合理延续。覆盖率与道路相交检查由当前 `tank_pad_validation.json` 重算，并要求源哈希匹配。整体布局与空间避让分别见 `../validation/plan_alignment.json`、`../validation/spatial_audit.json`；本轮人工可见差异见 `../validation/native_visual_review.json`。上述检查不替代运行性能验收，也不宣称新平面示意图与真实三维透视画面达到逐像素 1:1。
