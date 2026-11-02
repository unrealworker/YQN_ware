# MPR V4 周边建筑

本目录仅用于外景参考重建，不修改 MPR 仓库内部。位置由用户选定的 1728 × 910 总图反投影而来，不再受周边 CAD 位置约束。楼高、遮挡立面、住宅细节均为视觉估计；邻仓 30 m 的估计高度用来匹配参考中屋檐至墙脚的投影，不能用作建筑测绘数据。

## 重建顺序

1. 使用带 NumPy/Pillow 的 Python 运行 `Tools/MPRWarehouse/extract_mpr_reference_context.py`。
2. 使用 Blender 后台运行 `Tools/MPRWarehouse/build_mpr_reference_context_v4.py`。
3. 使用 Blender 后台运行 `Tools/MPRWarehouse/render_mpr_reference_context_v4.py`，检查同机位总览与邻仓月台。
4. 使用带 NumPy 的 Python 运行 `Tools/MPRWarehouse/validate_mpr_reference_context.py`。

摄像机标定保存在 `SourceAssets/MPR/reference_v3/calibration/camera_calibration.json`，源图绝对路径和 SHA256 保存在 `reference_context_layout.json`。脚本需要现有 `mpr_blender_common.py`、`Scripts/ghs/park_curves.py` 和本地 Blender Python 对应的 Shapely；不会调用 UE。

## 导入接口

只按 `manifest.json` 的 `meshes`、`lod_files` 和 `materials` 导入。目录里可能存在历史实验 FBX，未被清单引用的文件不是当前交付依赖。

`footprints_m` 是建筑和罐体的平面范围；`paved_footprints_m` 是新增罐区铺装，场地主生成器应把它纳入树木和草地排除。所有 LOD0 均为米制世界空间静态网格，`instances` 为空；LOD1 只供 LOD 导入，不生成重复场景物体。住宅按约 150 m 空间单元合批，保留分离门窗、屋脊、门廊/车库；罐体按参考顶面椭圆逐点反投影后垂直挤出。

`context_reference_camera.png` 与 `neighbor_deep_docks.png` 为隔离 Blender 验证图，不能替代最终 UE 总场景验收。`validation.json` 检查清单依赖、材质角色以及罐顶轮廓投影误差；空间穿插审计另见 `reference_v4/validation/spatial_audit.json`。
