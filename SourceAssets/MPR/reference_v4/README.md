# MPR 外部场景：新平面图修订

本轮位置与轮廓以用户提供的 `references/building-road-outline-20261103.png` 和 `references/all-elements-outline-20261103.png` 为准；旧彩色效果图仅用于材质、明暗和建筑细节风格。新平面图使用 `site/plan_registration_v5.json` 独立配准，不再通过旧透视相机反投影来塑造周边建筑。图像是示意资料，建筑高度、不可见细节、车辆与树木尺寸仍含视觉估计，不作为测绘数据，也不宣称完美 1:1。

主仓继续保留 CAD 的 16 段外墙轮廓、74 个门洞及内外接口。UE 目标为 `/Game/Maps/MPR_CAD_Warehouse`；导入仅替换所有权清单明确归属的外部对象。内部对象身份、组件、实例变换和依赖资产由保存重载报告中的保护摘要核对，不能仅凭数量或截图判断未变。

## 可编辑来源与布局

- `architecture/`：主仓外墙、月台、屋面及光伏，入口为 `reference_shell_manifest.json`。光伏依照 `plan_solar_v5.json` 的正交区域和真实留白生成，不把线稿格子断线当成屋顶缺口。
- `site/`：道路、场坪、标线、铁路、水面、车辆与植被。新图道路用 `road_outline_v5.json`，铁路用 `plan_railway_v5.json`，树冠原始落点用 `plan_vegetation_v5.json`；树岛语义与场地细节分别见 `plan_landscape_islands_v5.json`、`plan_site_details_v5.json`。实际落地与避让结果以 `manifest.json` 为准。
- `context/`：132 栋住宅、11 栋非住宅建筑、8 个储罐。住宅与工业建筑使用真实正交局部坐标、共面屋顶及竖直墙，储罐保持真实圆形；完整屋檐和门廊也参与间距检查。
- `props/`：共享树木、拖车、轿车和铁路货车。树源许可与修改说明保留在该目录。
- `MPR_ReferenceExterior.blend`：组合后的完整可编辑外景，共享重复构件网格并打包纹理。

模型坐标为 CAD 米制、Blender Z 向上。UE 只转换一次米到厘米及 Y 反射，实例 yaw 同步取负。`Tools/MPRWarehouse/mpr_reference_catalog.py` 为组合和导入提供相同网格、材质与实例规则。图纸 X/Y 像素尺度不等，不允许通过剪切房屋或拉伸最终截图制造叠图一致。

当前主仓清单为 62 个 LOD0 网格、5 个 LOD1 网格和 714 个实例；周边清单为 29 个 LOD0 网格、45 行全部 LOD。完整场景网格、分区、树车实例和保存 Actor 数量从本轮清单及验证报告读取，不沿用旧版本总数。分区合批与 HISM 管理重复构件；树采用项目既有 Nanite 细叶策略，光伏 SolarBank 保留显式 LOD、关闭 Nanite。光伏底座不含与电池片争夺深度的顶盖。

## 重建与验证

需要 Blender 5.2，以及与其 Python ABI 匹配的 NumPy/Shapely；图像提取和归档另需 Pillow。`Saved/ParkRefinement/python_deps` 是本地依赖缓存。模型生成/FBX 导出使用单线程；Blender 与 UE 验证顺序执行，避免同时占用 GPU。

1. 核对新平面提取清单及独立注册，再运行 `build_mpr_reference_shell_v4.py`、`build_mpr_reference_context_v4.py` 和 `build_mpr_reference_v4_site.py`。共享树车源无改动时复用已发布资产；完整重建树木时仍按 `build_mpr_reference_v4_props.py`、`refine_mpr_oak_canopy.py`、`publish_mpr_refined_canopy.py` 的顺序，不能在已缩放成品上重复缩放枝干。
2. 执行主仓、周边与外场 FBX 回读验证。`validate_mpr_context_orthogonality.py --blender` 检查保存后的实际顶点；`review_mpr_reference_v4_spatial.py` 检查道路、建筑、树干/冠幅、车辆、轨道与铺地的空间关系。
3. `compose_mpr_reference_v4.py -- --render` 组合外景，`validate_mpr_reference_v4_composition.py` 重新打开完整 `.blend` 检查。`review_mpr_plan_alignment.py` 生成新图坐标下的数据叠图；它不代表 UE 外观逐像素一致。
4. 独立 UE 进程运行 `import_mpr_reference_exterior.py`，执行所有权校验、备份和受控外部替换。最终导入保存后先运行 `archive_mpr_plan_validation.py --begin-run`，固定地图与源版本，再运行独立重载、性能和实际游戏截图。
5. `validate_mpr_reference_exterior.py` 重新加载地图，输出内部保护、源清单、导入变换及递归包依赖证据。`capture_mpr_reference_runtime_views.py` 输出八个游戏视角；`capture_mpr_plan_views.py` 输出真实正交总览和住宅正反面、邻仓、罐区近景；`capture_mpr_reference_game.py` 采集旧相机的风格对照。截图进程不保存地图。
6. 人工复核实际原图并记录残差后，运行 `archive_mpr_plan_validation.py --check-only`；来源、地图、报告及原图哈希全部匹配才执行 `--archive`。源模型或材质变更后必须刷新对应证据，旧报告不能继续代表新结果。

## 当前证据入口

`validation/plan_validation_archive.json` 是最终归档入口，记录地图/源文件/报告/原图 SHA-256；`final_pipeline.json` 列出对应步骤。是否属于同一轮应核对哈希，不能用文件名或历史成功状态推断。

`plan_alignment.png/json` 检查新平面布局数据；`spatial_audit.json` 检查空间避让；`context_geometry_validation.json` 检查保存后的正交建筑与完整几何间距；`package_dependencies.json` 检查当前地图递归依赖。`runtime_views/01…08` 与 `plan_views/09…13` 保留本轮 UE 游戏原图及截图报告，联系图仅用于浏览。`native_visual_review.json` 与 `visual_review.md` 记录人工检查范围和仍可见的差异。

`runtime_calibrated.png` 和 `reference_vs_ue_runtime.png` 使用旧透视相机，仅用于风格对照；相机点误差不代表整个场景达到了 1:1。`validation_blender/composition_manifest.json` 与 `composition_validation.json` 绑定各组源及完整组合 `.blend`；Blender 检查不能替代 UE 导入、阴影、抗锯齿和运行性能验证。

最新性能只引用 `validation/performance.json`、`performance_exterior.csv`、`performance_interior.csv` 及配套原图和哈希报告。报告说明硬件、渲染分辨率、采样时长、全部原生帧时及 GPU 数据；不把历史 2026-11-02 运行列为本轮结果。范围限本机单个离屏 UE 游戏进程的静态外景/内部机位，不包含像素流编码、网络、并发访问或全平台验收。

`validation/ghs_quality_regression/` 是 2026-11-02 项目共享 Nanite 画质预算的历史回归。该对照已显示性能成本，不能写成“对 GHS 没有影响”；本轮未修改项目全局画质设置，也未将该历史回归冒充本轮重新测试。
