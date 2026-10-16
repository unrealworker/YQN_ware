# GHS 仓库相机

场景：`/Game/Maps/GHS_CAD_NormalWarehouse`。项目默认运行此场景，World Settings 使用 `BP_GHS_WarehouseGameMode`。

Pawn：`/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseCamera`。

GameMode：`/Game/GHSNormalWarehouse/Camera/BP_GHS_WarehouseGameMode`。

场景中相机名为 `GHS_WarehouseCamera`，位于 `GHS_Normal/Camera` 文件夹，并自动由 Player 0 控制。不要再放第二个同类 Pawn。

## 操作

| 输入 | 行为 |
| --- | --- |
| 按住鼠标左键拖动 | 绕 Pawn 当前所在位置旋转；向下拖动时俯视角加大 |
| 鼠标滚轮向前 / 向后 | 拉近 / 拉远 |
| 按住鼠标右键拖动 | 在地面 XY 平面移动 Pawn，Z 始终为 0；随距离调整速度 |
| Home | 平滑恢复初始全景 |

轻点不会移动相机；拖动超过 3 像素后开始。左右键同时按下时先按下的键优先。松开或切换窗口后停止拖动。再次快速按住也可继续拖动。移动、旋转与缩放使用插件原生缓动，俯仰和距离有边界。默认最小距离和最浅俯角使实际镜头离地至少约 233cm。

初始旋转中心位于仓库地面中心。平移会移动实际 Pawn，之后围绕新位置旋转；缩放不改变这个位置。SpringArm 的 TargetOffset 和 SocketOffset 均为 0。Home 把 Pawn 和视角恢复到初始全景。Pawn 的高度为 0；实际镜头在 SpringArm 末端，初始离地 26750cm。

## 可调参数

在 Pawn 蓝图的 Class Defaults / Warehouse Camera 中调整，单位遵循 UE：位置和距离为厘米，角度为度。

| 参数 | 默认值 |
| --- | --- |
| Overview Center | X=-646.665，Y=833.981，Z=0 |
| Overview Distance | 53500 |
| Overview Pitch / Yaw | -30 / -90 |
| WarehouseCamera → Field Of View | 56 |
| Orbit / Pitch Degrees Per Pixel | 0.18 / 0.14 |
| Wheel Zoom Exponent | 0.12 |
| Minimum / Maximum Zoom | 900 / 95000 |
| Minimum / Maximum Pitch | -80 / -15 |
| Maximum Pan | 30000 / 15000 |
| Rotation / Movement / Zoom Lag Speed | 16 / 18 / 12 |

实现继承 UniversalCameraPlugin 的 AUniversalCamera。位置、旋转、缩放优先调用插件的 SetDesiredLocation / SetDesiredYaw / SetDesiredPitch / SetDesiredZoom；地面方向使用 GetAlternativeForwardVector / GetAlternativeRightVector；移动边界使用插件的 Raw Location Restrictions，Z 的上下限都是 0。使用插件原生 Movement / Rotation / Zoom Lag，不再另外实现插值算法。CameraComponent 直接连接 SpringArm。边缘滚屏、跟随、自动碰撞缩臂关闭；输入使用原始鼠标位移，不受项目旧 Axis 灵敏度二次缩放。

子类只在原生旋转缓动结果上将 Roll 归零，避免插件的四元数插值在同时改变水平和俯仰角时产生短暂歪斜。鼠标像素转换保留在子类，因为插件的轴输入接口会将数值限制在 ±1 并乘以帧时间。

插件 `FTargetSettings` 的三个对象指针补了 `nullptr` 初始化，修复 UE 启动反射校验报错。没有改动插件的相机算法。

## 验证证据

- `Saved/GHS_WarehouseCameraVerification.json`：新进程重载场景、蓝图、参数、比例缩放、旋转和平移边界。
- `Saved/Automation/WarehouseCameraGroundFinal/index.json`：五组 C++ 输入和地面平移回归测试，包括实际 Tick 下 Z 与 Roll 不漂移。
- `Saved/GHS_WarehouseCameraStandalone.json`：独立游戏进程确认唯一 Pawn、真实 PlayerController、实际相机位置和角度。
- `Saved/GHS_WarehouseCameraOverview.png`：实际游戏相机渲染图。
- `Saved/GHS_WarehouseCameraGroundRevision.json`：地面旋转中心与加长车厢修改前的备份位置。
- `Saved/GHS_GroundCameraLongTrucks.json`：52 辆独立装卸车、材质和摆放保留情况、包修改范围、LOD 和车辆间距检查。

输入绑定由原生自动化测试验证；独立游戏进程验证实际相机及 Pawn 的运动结果，并渲染初始全景。

## 加长装卸车

当前 Normal 场景的 52 辆独立 StaticMeshActor 使用 `/Game/GHSNormalWarehouse/TrucksLong/SM_GHN_LongDockTruck`。车厢由 6m 加长至 12m，整车约 14.90m。驾驶室和前轮整体前移 6m，轮胎尺寸、车尾与装卸门的对齐原点保持原样。各车辆仍可独立移动、复制或删除，保留当前数量、间距和材质。

Blender 源文件：`SourceAssets/GHS_Normal/TrucksLong/dock_truck_long.blend`，包含 441 个独立部件。对应 FBX 和几何校验报告位于同一目录。原始短车模型及其他场景未替换。
