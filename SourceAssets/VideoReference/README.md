# 参考视频仓储数字孪生场景

新关卡：`/Game/Maps/VideoDigitalTwinWarehouse`。这是基于参考视频制作的独立 UE 5.4 仓储场景，范围为蓝色工业数字孪生仓库，不包含视频末尾的控制室。

场景采用深蓝地面、半透明蓝色隔墙、青色轮廓线、规则货位、立体货架、蓝色/橙色搬运机器人、白色料箱机器人、电梯、绿色路线和橙红故障提示。模型几何在 Blender 中制作，UE 中配置材质、灯光、相机和实例布局。

## 打开与查看

1. 在 UE 编辑器中打开本项目，在内容浏览器进入 `Content/Maps`，双击 `VideoDigitalTwinWarehouse`。
2. 在 World Outliner 的 `VideoTwin/Cameras` 中选择相机；右键选择 Pilot 即可从对应视角查看。预设相机为 `CAM_Video_Overview`、`CAM_Video_Route`、`CAM_Video_Racks`、`CAM_Video_Alarm`、`CAM_Video_Elevator`。
3. 材质、模型和故障面板纹理位于 `/Game/VideoDigitalTwin/Materials`、`Meshes`、`Textures`。场景 Actor 按 `VideoTwin` 文件夹分类，可单独调整设备、货架、隔墙、路线和灯光。
4. 编辑器开启 Realtime（Ctrl+R）或运行场景时，可看到 AGV 雷达往返扫动、拖尾和底部光波向外扩散。机器人和托盘的当前位置是静态展示布局。

本目录内的 `.blend` 文件可以直接用 Blender 打开。每个资产对应独立 Collection，零件保留为可编辑对象；`.fbx` 用于 UE 导入，配套 `.json` 记录材质槽、尺寸包围盒和输出路径。

## 参考来源与比例

来源为用户提供的 `6dc2988787ab4c342c807e37633a086d_raw.mp4`，其本机原始位置、视频信息和抽帧记录见 `video_metadata.json`。`Frames` 保存参考帧，`Video_ContactSheet.jpg` 为视频联系表；`asset_observations.md` 记录逐帧观察到的造型和材质特点。

视频没有测量标尺和建筑图。仓库主体约 **36 × 26 m**，以 **1.2 × 1.0 m 托盘**为比例参照推定，机器人、货架、房间及通道尺寸均为视觉估算，不代表现场实测值。仓库外的辅助网格延伸范围大于主体建筑。

## 五个 Blender 资产库，共 45 个模型

| 可编辑源文件 | 模型数 | 内容 |
| --- | ---: | --- |
| `storage.blend` | 5 | 蓝色网格托盘货物、多层货架、输送线、LM/AP 货位板 |
| `robots.blend` | 5 | 蓝色堆垛搬运机器人、橙色搬运机器人、白色料箱机器人、低底盘报警机器人、交通锥 |
| `architecture.blend` | 7 | 蓝色电梯、工业门架、控制柜、状态环、报警环、目标标记、扫描扇面 |
| `hud.blend` | 1 | 中文故障诊断面板，配透明纹理 `T_VR_AlarmPanel.png` |
| `walls.blend` | 27 | 20 cm 厚蓝色剖切墙，实体压顶、底面、门洞端面及内外双棱 |

机器人模型的托盘/货物在 UE 中独立摆放，便于调整载荷和朝向。模型按米制作，UE 按厘米使用。FBX 导入转换会使 Blender 的 +Y 对应 UE 的 -Y；货叉朝向、平面正反面和文字 UV 均需结合这一转换检查。

## 脚本角色

脚本均位于项目的 `Scripts` 目录；下表路径以项目根目录为起点。重新生成关卡会重新布置设备及材质，建议在编辑副本中进行，以免覆盖手工调整。

| 脚本 | 用途 |
| --- | --- |
| `video_reference/extract_video.py` | 从来源视频抽取参考帧及视频元数据 |
| `video_reference/common.py` | Blender 建模、材质、Collection、FBX 导出及清单公共工具 |
| `video_reference/build_storage.py` | 制作托盘、货架、输送线和货位资产库 |
| `video_reference/build_robots.py` | 制作机器人和交通锥资产库；`--preview` 可生成独立预览图 |
| `video_reference/build_architecture.py` | 制作电梯、门架、控制柜及可视化标记资产库 |
| `video_reference/build_hud.py` | 普通 Python 以 `--texture` 生成中文 PNG；随后在 Blender 中生成保留显式 UV 的面板资产 |
| `video_reference/build_walls.py` | 按关卡墙段制作可编辑实体墙，墙厚 20 cm、高 2.8 m；每段保持独立 Collection |
| `upgrade_video_warehouse_walls.py` | 在当前关卡原位替换墙体；先保存并备份，保留非墙对象的位置、旋转和缩放，隐藏旧细线描边 |
| `build_video_warehouse.py` | 在 UE 中导入资产、创建材质并建立独立视频仓库关卡 |
| `refine_video_warehouse.py` | 对初始展示效果执行细化处理 |
| `finalize_video_warehouse.py` | 最终布局镜像校正、相机调整、墙体透明材质和故障面板可读性修正；校正后保存关卡。镜像有标记保护，避免重复翻转 |
| `capture_video_warehouse.py` | 打开目标关卡、设置视角并生成场景截图 |
| `verify_video_warehouse.py` | 读取已保存关卡，检查模型、材质、关键设备和布局，并写验证报告 |
| `video_reference/agv_fx_shader.py` | 雷达扫描与底部扩散的程序化 HLSL 材质，无特效模型或贴图 |
| `install_agv_animated_fx.py` | 在当前仓库关卡创建 8 个原生动态 Decal，附着到 AGV，隐藏旧静态效果并保存 |
| `verify_agv_animated_fx.py` | 独立读取已保存资源，检查动画图连通、旧效果隐藏，并临时平移/旋转验证附着跟随 |
| `capture_agv_animated_fx.py` | 临时相机近景截图；高分辨率截图可能固定材质时间，连续动作以实时视口录制为准 |
| `open_video_warehouse.py` | 编辑器辅助打开入口；包含当前关卡快照保护，适合按该脚本既定流程使用 |

Blender 库生成脚本在后台 Blender 执行；UE 场景脚本依赖编辑器的 `unreal` Python 模块，应在 UE 编辑器环境运行。最终呈现以执行 `finalize_video_warehouse.py` 后保存的关卡为准，单独重新执行初始构建脚本不会自动包含最后的展示校正。

`scene_registry.json` 记录已布置对象的标识、模型、位置、朝向和分类，可用于核对和后续继续编辑。运行日志、截图及验证报告保存在项目 `Saved` 目录。

## 墙体更新（2026-10-15）

根据视频 33 秒近景，墙体由原 3.5 cm 薄盒改为 Blender 制作的 **20 cm 厚、2.8 m 高**几何，具有连续宽顶面、门洞端面与双边轮廓。顶部和端面使用不透明蓝灰材质，墙面采用下部 0.40、顶部 0.15 的透明度渐变。尺寸由画面推定。

已替换 27 段墙，108 个旧细线描边对象保留但隐藏。独立 UE 加载检查通过；变更前的关卡副本在 `Saved/Backups/VideoWarehouse_BeforeWallThickness_*.umap`，墙体核验记录在 `Saved/VideoWarehouse_WallsReport.json`。以下初次交付的 18 模型计数不包含此次新增的 27 个墙体模型，当前合计 45 个。

## 初次交付核验（2026-10-15）

- 独立 UE 进程重新加载关卡通过：901 个 Actor、18 个导入模型、32 组货架、7 台机器人、874 个对象登记项、5 个相机。
- 检查 1364 个场景材质槽，没有空材质或默认 WorldGrid；墙体透明通道和报警面板纹理连接均已确认保存。
- 蓝图编译结果：0 个错误、0 个警告、0 个加载失败。日志为 `Saved/Logs/VideoWarehouse_Compile.log`。
- 五张实际 UE 1920×1080 截图为 `Saved/VideoWarehouse_UE_Overview.png`、`Route.png`、`Racks.png`、`Alarm.png`、`Elevator.png`（后四项同样带 `VideoWarehouse_UE_` 前缀）。核验报告为 `Saved/VideoWarehouse_Verification.json`，截图报告为 `Saved/VideoWarehouse_CaptureReport.json`。
- 切换新场景前，原物流园区编辑器状态已另存至 `/Game/Maps/Backups/LogisticsWarehouse_BeforeVideo_20261015_1730`。

当前仍与视频存在细节差异：货架箱货密度、部分近景的标签朝向，以及视频遮挡区域的结构采用重建推定。最终镜像改变 Actor 位置和朝向，不对模型使用负缩放；贴图和文字方向保留可读。

## 当前功能范围

当前交付是**固定设备布局与动态可视化特效**。路线、扫描区域、设备 ID、电量/速度和故障代码用于复现参考画面的展示语义；它们没有连接真实设备数据。没有实现实时设备接入、机器人自主移动、任务动态调度、避障仿真或完整的视频镜头动画。`50001` 故障面板及其“常见原因”文字为视觉展示内容，不作为现场设备诊断依据。

## AGV 动态特效更新（2026-10-15）

7 台 AGV 使用时间驱动的地面扩散投影；CBD50-1 增加朝向避障锥的雷达扫线、拖尾和扩散弧。实现使用原生 `DecalActor` 和程序化材质，特效中没有 StaticMesh。旧的 7 个状态/报警环和扫描扇面保留但隐藏。所有新特效附着到相应 AGV，随位置和朝向变化。

资源位于 `/Game/VideoDigitalTwin/FX`，材质实例可调整 `Speed`（默认 1）、`Tint` 和 `Phase`；投影尺寸由 Decal Size 控制。普通扩散半径 155 cm，报警扩散 175 cm，雷达投影半径 350 cm，实际显示由材质遮罩裁切。地面投射厚度 6 cm，避免把扫线投射到车身上。

`animated_fx.json` 记录附着关系与材料；`Saved/AGVFX_Verification.json` 记录独立加载及临时平移 100 cm、旋转 30° 后的跟随检查。重新运行初始建场脚本会还原旧布局，需随后执行动态特效安装脚本。

最终独立检查通过：8 个 Decal、7 台 AGV、0 个特效网格，退出码 0，无错误/警告。实际前台 UE 视口录制为 `Saved/AGVFX_ActualAnimation.gif`（32 帧，约 7.46 秒），由 `Scripts/make_agv_fx_preview.py` 按原始帧时间编码，未修改材质时间或动画内容；对应证据为 `Saved/AGVFX_AnimationProof.json`。
