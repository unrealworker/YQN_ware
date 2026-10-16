# GHS 现状 CAD 数字孪生交付说明

## 场景与状态

当前货架修订以 `RackSpecs/README.md`、`RackSpecs/cad_elevation_specs.json` 和 `RackSpecs/cad_plan_mapping.json` 为准：两场景同步使用 1639 个 A/B/D1 实例（含跨通道版本），C/D2 仅保留在资产库；87 个原 `W_DOCK` 对象更正为装卸门。货架柱高来自图纸，为 9.144/9.154 m；建筑墙、柱及轮廓采用 9.6 m 展示包络，门高 4.2 m，后二者均为明确估算。

新修订目标为每场景 43 组 HISM、14138 个实例，保存及验收状态分别以 `Saved/GHS_CADRackRevision.json` 和 `Saved/GHS_CADRackVerification.json` 的 `success` 为准。旧重建入口检测到修订后会停止，`verify_ue_scene.py` 转入新的双场景验收。以下原构建与逐次修复记录保留为历史，不代表本轮货架类型、数量和高度。

新场景：`/Game/Maps/GHS_CAD_DigitalTwin`。新资源目录：`/Game/GHSDigitalTwin`。原场景与共享资产保留。

初次避让修正阶段已在 UE 5.4 中完成构建、保存与蓝图编译，之后按用户反馈修正柱位和储物穿插。该阶段包含 247 个 Actor、15 组 HISM、14,383 个实例，记录为 `Saved/GHS_ClearanceApplied.json`，独立验收为 `Saved/GHS_ClearanceVerification.json`。这些报告及 `Saved/GHS_Verification.json` 均为历史验证，不代表当前数量。

4 个 GHS Blueprint（1 个生产实例蓝图、3 个隔离测试蓝图）编译无错误、无警告。UE 启动日志中的 Unreal Trace Server `0x00006005` 为追踪辅助进程启动警告，未影响资产编译或场景验证。

## 数据与坐标

唯一平面布局依据为 `D:\EdgeDownload\平面布局图_GHS_0.23_20260710现状.dxf`。采用当前右侧现状主体，建筑底图 INSERT 句柄 `2379D1`；左侧旧方案、图框和网格外延不作为主体位置。下方五类货架立面用于本轮真实结构尺寸，不把立面本身当作仓库内放置位置。

DXF 单位为 inch，换算系数为 **0.0254 m/inch**。文件虽然声明 ANSI_936，实际中文以 UTF-8 解码才能正确读取。

- CAD 局部原点：`[6917380, 1902500]`。
- CAD 局部米坐标：`(DXF_XY - origin) * 0.0254`，保持右手 XY。
- UE 厘米坐标：`(local_X, -local_Y, Z) * 100`，即 UE Y 反向。
- `position_m` 为嵌套变换后的局部几何包围盒中心；`size_m` 为局部轴尺寸，须与 `rotation_deg` 一起使用，不是世界轴对齐包围盒。

准确建筑边界来自 AREA 多段线 `2379D1/4F2C8`，保留东南斜角及西南附房。实际最大外包尺寸 **465.7344 × 137.16 m**，平面面积 **56,116.0983 m²**。建筑块更大的包围盒包含轴网外延，不能当作物理建筑边界。

## 布局清单

| 内容 | 数量 | 依据与说明 |
|---|---:|---|
| 货架 | 1639 个显示实例 | 1214 A、47 A跨通道、265 B、11 B跨通道、102 D1；源handle与分段关系见RackSpecs映射 |
| 托盘/地堆储位 | 7530 | 7408 处放置货物；122 处柱占用位置留空并保留边线 |
| 柱 | 170 | 采用建筑底图柱；36 个 PILLAR 中33个重复绘制、3个未确认离网候选，均保留来源记录不重复显示 |
| 墙段 | 330 | 从 601 条墙面候选线合并；271 对墙面提供实测厚度 |
| 门 | 55 | 建筑门块实例 |
| 装卸门 | 87 | W_DOCK 的 DOCK_NO. 和实体几何证明为门，不属于货架或输送线 |
| 充电位 | 56 | 7 排各 8 个斜置停车格，与“56台充电桩”标注一致 |

按用户选择严格保留现状，**不增加输送线**。未识别到明确输送设备；“皮带机(蓝)”图层仅有文字注释，不能据图层名推定输送线。

`cad_layout.json` 保留初始提取；`clearance_layout.json` 为修正后的物理布局接口；`cad_analysis.json` 为图层、块及文本调查；`cad_raw.json` 保留原始二维展开几何。每个布局项都有 ID、图层和 `source_handles` 来源链。重复对象使用 HISM 实例化，每个实例的 ID 与来源句柄通过 `ue_scene_registry.json` 对应，避免因合批丢失可追溯性。

## 柱位避让修正

初版将货位虚线边距及货架 ATTDEF 文字范围纳入了模型尺寸，且未检查柱网和储物交叉。修正版按实体实线使用 1.016 × 1.2192 m 托盘位、1.0668 × 3.81 m 货架外廓，并对共享端框作局部裁剪。UE 实例按包含 LOD 的真实网格包围盒归一化，同时补偿网格偏心，避免名义尺寸与导入网格边界不符。

柱位保持建筑底图位置；柱体使用与墙面完全相同的 `M_GHS_WallVolume` 材质，柱脚使用墙体截面材质。柱脚外侧预留 0.10 m 净距；122 个冲突库位保留原位置但不放货，货架局部沿长轴分段，40 个小于0.75m的不可用残段不放置并保留记录。这是消除图纸交叉的可视化避让方案，不是宣称原图已注明可用库位净距。

源CAD没有改写。`Saved/GHS_ClearancePlan.json` 保留每项处理原因；`Saved/GHS_OverlapBefore.json` 为修正前几何审查；`Saved/GHS_ClearanceApplied.json` 包含修正前地图和注册表备份位置。

## 墙体接缝与边线修正

330段源墙按真实厚度形成矩形后做几何并集，墙面、顶底盖和青色边带共用同一外轮廓，消除独立墙段交接处的重复线和超出端点。青色边带沿轮廓向墙内收12mm，顶面仅抬高0.5mm避免共面闪烁。保留原CAD全部330个来源ID，不吸附、外扩或封闭原有门洞。

`joined_walls_geometry.json` 保留三角网格、闭环轮廓与来源映射；`joined_walls.blend` 可编辑；三个 `SM_GHS_JoinedWall*.fbx` 导入后替换原来的墙面、截面和边线组。其他对象及原材质保持一致。`Saved/GHS_JoinedWallsApplied.json` 记录修改前备份；`Saved/GHS_WallJoints_Before.png` 和 `Saved/GHS_WallJoints_After.png` 使用用户问题视角直接在UE截图。

墙体验收由 `verify_joined_walls.py` 读取UE保存网格的实际三角形、世界变换与材质，并继续执行柱/货架/货物相交、AGV、动效和LOD检查。历史结果保存在 `Saved/GHS_JoinedWallsVerification.json`。

170根柱体补充与墙体边线相同的 `M_GHS_WallTrim` 青色轮廓：每根顶部四边、底部四边和四条竖棱，共2040条实例。12mm宽边线全部位于原柱体边界内，接角只相接，不叠加伸出。柱体半透明材质保持一致。配置为 `column_outline_style.json`，应用脚本为 `apply_column_outlines.py`。当前CAD货架修订保留相同轮廓规则并同步高度；旧全场重建入口现已受保护。

柱轮廓阶段的历史验收为 `Saved/GHS_ColumnOutlinesVerification.json`，当时场景为248个Actor、16个实例组、14116个实例。截图 `Saved/GHS_ColumnOutlines_After.png` 来自用户检查柱子的同一视点。当前 `Scripts/ghs/verify_ue_scene.py` 优先识别 CAD 货架修订并验收两场景。

## 估算与参考图补充

CAD 确定平面位置、排布、可读尺寸及轮廓。货架现已按独立立面测量柱顶、横梁和货载高度；建筑墙/柱的9.6 m展示高度和装卸门4.2 m高度仍为估算。旧2.8 m墙网格仅作为不可变局部源几何，由实例高度配置同步映射。59 条未配对墙段采用 0.15 m 估算厚度；其余配对墙面厚度从 CAD 距离提取，常见值为 0.254 m。

白灰低底盘 KUKA 外形 AGV 和红黑壁挂式充电器按用户参考截图建模，机壳尺寸、细节、线缆及接头属于截图推定，不是厂商实测模型。

56 个 CAD 充电格的中心和朝向可追溯，停车格约为 1.524 × 3.048 m。CAD 未提供实体充电器的壁挂点、支撑隔板或插座位置；场景中的 **56 处充电器支撑隔板及安装点是结合参考图补充的设计**，不得称为原图已有建筑构件。

场景陈列 34 台 AGV，其中 28 台位于充电区、6 台位于北侧通道。这是可视化布置，不是 CAD 给出的车辆数量或实测停车状态。未获得 AGV 实测轨迹，不能把动效描述成真实运行调度或回放。

## 材质与动态效果

沿用已确认的原场景深蓝数字孪生材质、环境、灯光及厚墙风格。扫描与扩散效果采用 **40 个时间驱动 Decal**；效果由程序化材质实现，不使用特效模型。时间驱动扫描动画并不证明车辆沿实测路径移动。

## 可编辑源文件与脚本

Blender 源文件在本目录：

- `kuka_agv.blend`：AGV 模型；对应 `SM_GHS_KukaLowProfileAGV.fbx`。
- `charger.blend`：壁挂充电器模型；对应 `SM_GHS_WallCharger.fbx`。
- `cad_architecture.blend`：CAD 建筑地面与墙体基础资源；对应 `SM_GHS_CAD_Floor.fbx`、`SM_GHS_WallPanelUnit.fbx`。

脚本入口位于 `D:\UEPro\Test\Scripts\ghs`：

| 阶段 | 脚本 |
|---|---|
| CAD 调查 | `inspect_dxf.py`、`inspect_groups.py` |
| CAD 提取、墙体配对、二维核验 | `extract_layout.py`、`refine_layout.py`、`verify_layout.py` |
| Blender 建模 | `build_kuka_agv.py`、`build_charger.py`、`build_cad_architecture.py` |
| CAD 货架修订 | `prepare_cad_rack_registry.py`、`import_cad_rack_models.py`、`apply_cad_rack_revision.py`；流程见 `RackSpecs/README.md` |
| UE 独立核验 | `verify_ue_scene.py` → `verify_cad_rack_revision.py`（存在成功修订时） |
| 历史初次构建 | `prepare_ue_assets.py`、`build_ue_scene.py`；修订后旧builder明确停止 |
| UE 截图 | `capture_ue_scene.py` |

CAD 脚本使用已配置的 Python 和 `Scripts/_vendor/cad` 下的 ezdxf；Blender 脚本在 Blender 中执行；UE 脚本在 Unreal Editor Python 环境执行。

## 对照图与相机

`CAD_verified_layout.png` 展示准确建筑轮廓及提取的实体分类；`CAD_main_plan.png` 为包含轴网等上下文的源图总览；`CAD_racks_detail.png` 和 `CAD_east_charging.png` 为货架区及充电区细节。`cad_notes.md` 提供更详细的来源与限制，`cad_validation.json` 记录 CAD 数量及面积检查。

场景设置 6 台相机：

1. `CAM_GHS_Overview`：场景总览。
2. `CAM_GHS_CADPlan`：CAD 平面对照。
3. `CAM_GHS_RackAisles`：货架通道。
4. `CAM_GHS_FloorStorage`：地堆储位。
5. `CAM_GHS_Charging`：充电区域。
6. `CAM_GHS_AGV_Charger`：AGV 与充电器近景。

初版验收核对了40个附着于 AGV 的无网格 Decal、6个相机、7个模型资产、5个模型的四级 LOD，以及原地图 SHA；地板包围盒也核对了 CAD 到 UE 的 Y 镜像。柱位修正后的 `Saved/GHS_ClearanceVerification.json` 在新 UE 进程重新读取保存地图，验证9452个柱、柱脚、货物、货架和装卸货架的实际网格包围盒及世界变换，12类对象组合的 OBB 相交均为0（1mm数值容差）。柱体与墙面材质资产相同，原有材质、动效、相机及LOD回归通过。以上均为该阶段历史结果；当前 `verify_ue_scene.py` 优先进入CAD货架双场景验收，历史报告保留。

6 张 UE 实景截图保存于 `Saved/GHS_UE_*.png`（3840 × 2160）。`Saved/GHS_AGV_ActualAnimation.gif` 来自编辑器真实运行画面，共 28 个不同帧，非合成动画。数值证据为 `Saved/GHS_AnimationVerification.json`。

修正后柱边近景为 `Saved/GHS_Clearance_UE_ColumnDetail.png`，货堆与货架细节为 `Saved/GHS_Clearance_UE_FloorStorage.png`、`Saved/GHS_Clearance_UE_RackAisles.png`；均由当时的UE场景直接截图。柱体沿用墙面蓝色半透明效果。

视觉检查修复了 AGV 中央圆盘与平台共面的问题，整车最终高度为 0.324 m；设备远近细节阈值保留近景结构。GHS 货箱的最远 LOD 从过度简化的 290 三角形修复为 1,048 三角形，保留货物、托盘与接缝三个材质段。

实例化渲染使用 `/Game/GHSDigitalTwin/Materials/Instanced` 中 14 个原风格材质的完整副本，实例化使用标记已持久化，原材质文件未写入。记录见 `Saved/GHS_InstanceMaterials.json` 与 `Saved/GHS_SourceMaterialPreservation.json`。
