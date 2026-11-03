# MPR 外部场景：新平面图修订

本轮位置与轮廓以用户提供的 `references/building-road-outline-20261103.png` 和 `references/all-elements-outline-20261103.png` 为准；彩色参考，包括用户第六图 `references/style-focus-20261103.png`，用于材质、明暗、建筑细节和留空类型判读，不通过其透视轮廓替换新平面落点。新平面图使用 `site/plan_registration_v5.json` 独立配准，不再通过旧透视相机反投影来塑造周边建筑。图像是示意资料，建筑高度、不可见细节、车辆与树木尺寸仍含视觉估计，不作为测绘数据，也不宣称完美 1:1。

主仓继续保留 CAD 的 16 段外墙轮廓、74 个门洞及内外接口。UE 目标为 `/Game/Maps/MPR_CAD_Warehouse`；导入仅替换所有权清单明确归属的外部对象。内部对象身份、组件、实例变换和依赖资产由保存重载报告中的保护摘要核对，不能仅凭数量或截图判断未变。

## 可编辑来源与布局

- `architecture/`：主仓外墙、月台、屋面及光伏，入口为 `reference_shell_manifest.json`。光伏以最新实景 `references/solar-roof-aerial-20261103.png` 的阶梯轮廓、设备孔及通道为准，测量结果写入 `plan_solar_v5.json`；旧线稿规则化轮廓已撤销。
- `site/`：道路、场坪、标线、铁路、水面、车辆与植被。新图道路用 `road_outline_v5.json`，铁路用 `plan_railway_v5.json`，树冠原始落点用 `plan_vegetation_v5.json`；树岛语义与场地细节分别见 `plan_landscape_islands_v5.json`、`plan_site_details_v5.json`。实际落地与避让结果以 `manifest.json` 为准。
- `context/`：132 栋住宅、11 栋非住宅建筑、8 个储罐。住宅与工业建筑使用真实正交局部坐标、共面屋顶及竖直墙，储罐保持真实圆形；完整屋檐和门廊也参与间距检查。
- `props/`：共享树木、牵引车、半挂车、轿车、铁路货车和机车。树源许可与修改说明保留在该目录，完整车辆构成和重建方式见 `props/README.md`。
- `MPR_ReferenceExterior.blend`：组合后的完整可编辑外景，共享重复构件网格并打包纹理。

模型坐标为 CAD 米制、Blender Z 向上。UE 只转换一次米到厘米及 Y 反射，实例 yaw 同步取负。`Tools/MPRWarehouse/mpr_reference_catalog.py` 为组合和导入提供相同网格、材质与实例规则。图纸 X/Y 像素尺度不等，不允许通过剪切房屋或拉伸最终截图制造叠图一致。

车辆清单包含 52 组完整牵引车与半挂车；南侧 14 个、北侧 22 个 CAD 码头组合保持门洞对齐。独立停车位以整车真实占地避让，共 11 处有场内偏移；最后两个受限车位 `SouthStands_8` 与 `SouthEastStands_2` 分别移动 9.657m、13.200m，全部保留，无省略。偏移明细见 `site/manifest.json` 的 `trailer_layout_audit`，不宣称其仍与原图符号中心完全重合。铁路改为三组连续编组，共 56 节，其中 53 节货车、3 台机车；实际曲线上的车钩连接、轮轨接触和主体碰撞由 `rail_consist_audit` 与空间验证记录。

当前主仓清单为 62 个 LOD0 网格、5 个 LOD1 网格、5 个 LOD2 网格和 880 个实例；周边清单为 29 个 LOD0 网格、16 个 LOD1 网格。主仓光伏有 5,077 个视觉模块、957 条近景板带和 5 个 SolarBank 分区；近、中、远三级均保留 16 个实景区域中的 18 处封闭孔和全部外沿凹口。完整场景网格、分区、树车实例和保存 Actor 数量从本轮清单及验证报告读取，不沿用旧版本总数。分区合批与 HISM 管理重复构件；树采用项目既有 Nanite 细叶策略，光伏 SolarBank 保留显式 LOD、关闭 Nanite。光伏底座不含与电池片争夺深度的顶盖。 近景细条间增加下沉 0.14 m 的灰蓝安装槽；LOD 阈值按分区实际包围球半径归一化。实景注册到 7 个 CAD 退台锚点的最大残差为 2.10 m，不代表测绘精度；透视变换只用于测图。195 个实际放置屋顶设备来自照片筛选，并通过完整 footprint 避让。

本轮色调调整使用主仓、周边建筑、场坪、草地与树叶各自的材质角色；主仓码头立面的蓝色区域延伸到门上沿，CAD 轮廓和门洞不变。MPR 定向光、环境光与曝光保持原值。源材质与几何检查不等于最终画面通过；本轮新导入的原生截图、光伏采样和人工复核完成前，不以旧归档替代本次视觉结论。

## 重建与验证

需要 Blender 5.2，以及与其 Python ABI 匹配的 NumPy/Shapely；图像提取和归档另需 Pillow。`Saved/ParkRefinement/python_deps` 是本地依赖缓存。模型生成/FBX 导出使用单线程；Blender 与 UE 验证顺序执行，避免同时占用 GPU。

1. 核对新平面提取清单及独立注册，再运行 `build_mpr_reference_shell_v4.py`、`build_mpr_reference_context_v4.py` 和 `build_mpr_reference_v4_site.py`。共享树车源无改动时复用已发布资产；仅车辆改动执行 `build_mpr_reference_v4_props.py -- --vehicles-only`，然后重建场地。完整重建树木时仍按 `build_mpr_reference_v4_props.py`、`refine_mpr_oak_canopy.py`、`publish_mpr_refined_canopy.py` 的顺序，再补当前车辆分支；不能在已缩放成品上重复缩放枝干。
2. 执行主仓、周边与外场 FBX 回读验证。`validate_mpr_context_orthogonality.py --blender` 检查保存后的实际顶点；`review_mpr_reference_v4_spatial.py` 检查道路、建筑、树干/冠幅、车辆、轨道与铺地的空间关系。
3. `compose_mpr_reference_v4.py -- --render` 组合外景，`validate_mpr_reference_v4_composition.py` 重新打开完整 `.blend` 检查。`review_mpr_plan_alignment.py` 生成新图坐标下的数据叠图；它不代表 UE 外观逐像素一致。
4. 独立 UE 进程运行 `import_mpr_reference_exterior.py`，执行所有权校验、备份和受控外部替换。最终导入保存后先运行 `archive_mpr_plan_validation.py --begin-run`，固定地图与源版本，再运行独立重载、性能和实际游戏截图。
5. `validate_mpr_reference_exterior.py` 重新加载地图，输出内部保护、源清单、导入变换及递归包依赖证据。`capture_mpr_reference_runtime_views.py` 输出八个游戏视角；`capture_mpr_plan_views.py` 输出真实正交总览和住宅正反面、邻仓、罐区近景；`capture_mpr_outside_views.py` 增加完整场地与四个方向的外围视角，共 18 个原生视角。`capture_mpr_detail_views.py` 再增加 7 个整车、车头轮子、机车、车钩、列车编组、水池及院区近景，总计 25 个原生视角；车辆机位读取当前实例清单。`capture_mpr_reference_game.py` 另采集旧相机的风格对照。截图进程不保存地图。
6. `capture_mpr_solar_motion.py` 为基线与最终版本各采集 96 个固定姿态；`review_mpr_solar_motion.py` 在 CPU 上核对相机/FOV/分辨率及原图哈希，生成平面对齐指标和原图并排预览。地图版本允许不同，最终采样必须绑定当前地图与本轮源证据。
7. 人工复核实际原图并记录残差后，运行 `archive_mpr_plan_validation.py --check-only`；来源、地图、报告及原图哈希全部匹配才执行 `--archive`。源模型或材质变更后必须刷新对应证据，旧报告不能继续代表新结果。

## 当前证据入口

`validation/plan_validation_archive.json` 是最终归档入口，记录地图/源文件/报告/原图 SHA-256；`final_pipeline.json` 列出对应步骤。是否属于同一轮应核对哈希，不能用文件名或历史成功状态推断。

`plan_alignment.png/json` 检查新平面布局数据；`spatial_audit.json` 检查空间避让；`context_geometry_validation.json` 检查保存后的正交建筑与完整几何间距；`package_dependencies.json` 检查当前地图递归依赖。`runtime_views/01…08`、`plan_views/09…13`、`outside_views/14…18` 与 `detail_views/19…25` 是对应原图及截图报告的归档入口，联系图仅用于浏览。外围道路末端检查见 `outside_road_review.json`：29 个原图出口沿实测图上切向和宽度延续，在冲突前缩短；末段参考 GHS 的 EdgeFade 顶点色方案过渡到现有草地。没有补画道路闭合、连接支路或未知路口，原图内路面差集为零。渐变使用 MPR 独立材质，不修改共享 GHS 资产。`campus_surface_review.json` 检查池塘铺地补口、院区外围深色绿带及北侧装卸作业面；`transport_geometry_validation.json` 检查完整车辆源网格与地面接触。`native_visual_review.json` 与 `visual_review.md` 记录人工检查范围和仍可见的差异。

`runtime_calibrated.png` 和 `reference_vs_ue_runtime.png` 使用旧透视相机，仅用于风格对照；相机点误差不代表整个场景达到了 1:1。`validation_blender/composition_manifest.json` 与 `composition_validation.json` 绑定各组源及完整组合 `.blend`；Blender 检查不能替代 UE 导入、阴影、抗锯齿和运行性能验证。

`validation/solar_motion/solar_motion_review.json` 记录逐姿态采样的共同蓝面、亮度漂移、高通变化、空间细节强度和遮罩覆盖率；并排 MP4 只用于查看原图序列。每个姿态停留 0.15 秒再截图，播放速度是演示设置，不是实时录屏、连续动态性能或“没有闪烁”的证明。屋顶分析画布已扩展，实际板带覆盖比例读取本轮报告的 `analysis_plane.strip_area_coverage_fraction`，边缘和设备孔附近另由原生近景审查。完整基线/最终各 96 张 PNG 保留在 `Saved/MPR/solar_motion`，归档包含其哈希报告与精选诊断。审计 `success` 表示流程完成，不自动表示视觉合格；变暗、丢失细节或共同遮罩缩小均不能独立作为改善结论。

最新性能只引用 `validation/performance.json`、`performance_exterior.csv`、`performance_interior.csv` 及配套原图和哈希报告。报告说明硬件、渲染分辨率、采样时长、全部原生帧时及 GPU 数据；不把历史 2026-11-02 运行列为本轮结果。范围限本机单个离屏 UE 游戏进程的静态外景/内部机位，不包含像素流编码、网络、并发访问或全平台验收。

`validation/ghs_quality_regression/` 是 2026-11-02 项目共享 Nanite 画质预算的历史回归。该对照已显示性能成本，不能写成“对 GHS 没有影响”；本轮未修改项目全局画质设置，也未将该历史回归冒充本轮重新测试。
