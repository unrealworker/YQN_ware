# MPR 效果图外景

本版本依据用户确认的最新总览图重建外部场地；周边 CAD 不再约束道路、建筑和绿化。`references/` 保存 7 张原图及 SHA-256。此模型为效果图的视觉复原，外部建筑高度、树木和车辆尺寸不作为工程测量数据。

主楼沿用内部 CAD 的 16 段轮廓及 74 个门洞接口。UE 目标为 `/Game/Maps/MPR_CAD_Warehouse`，只替换明确归属的外部 Actor，保留内部 Actor GUID、组件、实例变换及依赖资产字节。

## 可编辑源与资产

- `architecture/`：主楼外墙、月台、屋顶和光伏；`reference_shell_manifest.json`。
- `site/`：按参考像素描线的道路、场坪、标线、道床、调蓄池；`reference_site_pixels.json` 和 `manifest.json`。
- `context/`：参考中的住宅、周边工业建筑与罐区，分区合批；`manifest.json`。
- `props/`：可实例化的树木、拖车、轿车与铁路货车；`manifest.json`。
- `MPR_ReferenceExterior.blend`：完整外部场景，源材质纹理内嵌，重复构件共享 mesh。

所有清单坐标以 CAD 米为单位，Blender Z 向上。UE 导入只进行一次米→厘米与 Y 反射；实例 yaw 同步取负。`Tools/MPRWarehouse/mpr_reference_catalog.py` 为 Blender 组合和 UE 导入提供同一实例清单。

树源为 Simon Thommes / Blender Studio 的 CC-BY 素材，许可、来源原文件与修改说明保存在 `props/`。原生枝干和重新制作的细叶使用共享网格，UE 树木采用 Nanite `PRESERVE_AREA`，`max_edge_length_factor=0`，并设置 25% 三角面回退；不使用体素树。光伏底座采用无顶盖的五面壳体，电池片不与底座顶面争夺深度；SolarBank 禁用 Nanite，并保留显式 LOD。道路和标线不投影，重复构件以分区 HISM 管理。

草地与水面已移除造成棋盘、斜纹的周期正弦信号。草地使用接近原平均亮度的低幅随机细节，水面使用均匀漫反射和弱随机法线；材质同步写入正式 Blender 源和 UE 导入清单。`validation/surface_texture_review.json` 对比修复前后的频谱，确认 25 个场地网格的几何、UV、变换及全部树车实例保持不变。最终实际游戏近景 `validation/runtime_views/06-pond.png` 中不再可见该规则棋盘与水面斜纹；草地色调、树冠和其他外观差异仍见视觉复查。

`Config/DefaultEngine.ini` 设置项目级 `r.Nanite.MaxPixelsPerEdge=0.25`，为细叶树冠保留较高的远景几何预算。该设置也影响 GHS 等其他使用 Nanite 的场景。已对 GHS 完成两次顺序执行的原生交互/性能路径对照（0.25 与 1.0 各一次），结果见下文；不能把本次单次对照视为统计等效或其他关卡没有性能变化的证明。

正式清单包含 124 个 LOD0 网格、98 个静态分区、26 个共享模块，以及 1,294 个实例（主楼 727、外场 567）。外场含 366 棵树、66 辆拖车、41 辆轿车和 94 节铁路货车。数量由清单推导。正式地图保存 388 个 Actor：136 个原内部、250 个新外部和 2 个现有相机；游戏运行时的临时 Actor 另计。

## 重建与导入

重建需要 Blender 5.2 的 Python 环境可用 NumPy、Shapely 2.x，参考图提取/比较另需 Pillow。脚本会查找项目本地 `Saved/ParkRefinement/python_deps`；该目录是环境依赖缓存，不随模型提交，Shapely 必须与 Blender 的 Python ABI 匹配。已有 CAD 数据及 `Scripts/ghs/park_curves.py`、`park_vehicles.py` 是项目内依赖。

在项目根目录依次运行 Blender 后台脚本，FBX 导出使用 `--threads 1`：

1. `build_mpr_reference_shell_v4.py`
2. `build_mpr_reference_context_v4.py`（读取已归档的 `reference_context_layout.json`；需要重新提取图像轮廓时先用带 Pillow 的 Python 运行 `extract_mpr_reference_context.py`）。
3. `build_mpr_reference_v4_props.py`、`refine_mpr_oak_canopy.py`、`publish_mpr_refined_canopy.py`（保留审核用树冠 `.blend`）。
4. `build_mpr_reference_v4_site.py`
5. `compose_mpr_reference_v4.py -- --render`

树木完整重建必须按步骤 3 的三段顺序执行。`refine_mpr_oak_canopy.py` 会缩放输入枝干，不能在已发布成品上连续重复运行；仅同步材质或重新发布已审核树冠时，单独运行 `publish_mpr_refined_canopy.py`。发布脚本同步正式 `.blend` 与全部 7 个 FBX 的材质，重新回读颜色、几何和材质分配，并更新哈希。

UE 使用独立编辑器进程执行 `import_mpr_reference_exterior.py`。导入前检查资产所有权哈希、拒绝未知目标资产、备份所有待写包；所有资源导入完成后才移除基线中明确归属的外部 Actor。事务备份在 `Saved/MPR/reference_transactions/`，恢复仅允许编辑器已关闭且失败后文件没有再被修改的情况。

`validate_mpr_reference_exterior.py` 在独立进程重新加载地图，检查原内部快照、资产/材质、实例世界变换和静态网格零位，编辑器视图仅用于辅助诊断。正式八视角使用 `capture_mpr_reference_runtime_views.py` 的实际游戏视口与逐视角预热，归档于 `validation/runtime_views/`。它优先读取当前 `Saved/MPR/reference_v4_build.json`，没有本地运行报告时读取归档 `validation/import_report.json`。内部原始基线为 `../reference_v3/validation/interior_before.json.gz`；V3 文件夹在这里仅保留标定和原始保留边界，不代表加载旧外景。

`capture_mpr_reference_game.py` 从实际 UE 游戏视口采集标定总览，作为同机位视觉对照入口；`capture_mpr_reference_camera.py` 的 SceneCapture 结果用于辅助诊断，两者不能混同为运行画质。截图进程不保存地图。性能由 `profile_mpr_runtime.py` 在独立游戏中采样，不能用 Blender 渲染或编辑器平均帧率替代。

## 验证证据

`validation/` 和 `validation_blender/` 保存源文件对应的空间审计和图像。`validation/reference_vs_ue_runtime.png` 是参考图与实际 UE 游戏画面的原像素对照；`runtime_capture_archive_validation.json` 校验原始 overscan 哈希、裁剪像素和 20 个投影点，`visual_review.md` 记录仍可见的外观差异。最终八视角原图与哈希归档在 `validation/runtime_views/`，缩略总览为 `runtime_views_contact_sheet.png`。具体 UE 导入、重新加载及运行结果以最终地图哈希对应的验证报告为准；相机角点误差不代表整个场景已经达到逐像素一致。正在修改中的模型、旧截图及旧性能报告不能作为最终验收。

内部基线包含 136 个 Actor、4,441 个实例和 45 个项目资产依赖。保留校验比较对象身份、组件状态、逐实例变换及依赖文件哈希；对象总数一致本身不足以通过。旧 V3 文档中的标签与测试数量是基线记录，新外景使用 `mpr-reference-exterior-v4` 标签与 `MPR/ReferenceV4` 文件夹。

性能测试范围为一台本机、一个 UE 游戏进程、固定外景/内部机位；不涵盖像素流编码、网络、多人并发或全平台表现。最终回复与报告应同时注明分辨率、采样时长、帧时及测试硬件。

## 本机运行验证

最终性能运行 `20261102_141742_352356` 对应地图 SHA-256 `75036468cbea7fbbe31216514417a21937441c84abb4082ad1b42ab20369a90f`，已经包含草地与水面纹理修复。导入、独立重载、性能、实际游戏八视角与标定总览五步均通过，归档记录见 `validation/final_pipeline.json` 和 `pipeline_archive_validation.json`。硬件由原生 CSV 读取：Intel Core i9-14900HX、NVIDIA GeForce RTX 5060 Laptop GPU，驱动 582.05；UE 5.8.4、D3D12 SM6、Development Editor-game。

单个本地 offscreen 进程、1920 × 1080、100% Screen Percentage，外景和隐藏屋顶的内部各预热 15 秒、采样 15 秒。使用全部原生 CSV 帧，没有剔除尖峰；截图在性能窗口外拍摄。

| 状态 | 帧数 | 平均帧时 / P95 | GPU 平均 / P95 | 超过 16.67 ms |
|---|---:|---:|---:|---:|
| 外景 | 1,598 | 9.38 / 10.43 ms | 8.81 / 9.37 ms | 0 |
| 内部 | 1,256 | 11.95 / 13.16 ms | 11.29 / 11.87 ms | 1 |

内部最大帧时为 22.63 ms；两个状态均没有超过 33.33 ms 的帧。既有相机的缩放、旋转、重置 API 经真实玩家相机读回验证，重置位置误差为 0 cm；此检查不代表操作系统输入延迟测量。MPR 测试没有 HUD，也不包含像素流编码、网络、多人并发或打包后的全平台表现。

`performance.json`、同 run ID 的两份原生 CSV 和两张 1920 × 1080 截图保留原始字节；`performance_archive_validation.json` 核对文件哈希，并独立重算全部帧时统计。旧运行的图片/CSV 可留在本地，但不属于本次候选提交。

## GHS 共享画质设置回归

`validation/ghs_quality_regression/` 保存 0.25 与 1.0 设置的两次原生 GHS 路径、CSV 和比较结果。相同硬件、1920 × 1080，每次预热 15 秒、路径采样 90 秒；两次均完成 38 个动作与 2 次货物点击。

本次顺序对照中，0.25 相比 1.0 的平均帧时为 9.924 / 9.523 ms，增加约 4.21%；P95 为 14.273 / 13.504 ms，增加约 5.69%。GPU 平均时间增加约 4.17%。因此更高的 Nanite 细节预算存在可测的共享性能成本，不能报告为“对 GHS 没有影响”。每个设置只有一次运行，尚不足以证明统计等效；本回归也不是像素流、网络或画面逐像素一致验收。
