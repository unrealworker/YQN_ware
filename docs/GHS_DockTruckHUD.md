# 装卸车辆 HUD 接入说明

适用场景：`/Game/Maps/GHS_CAD_NormalWarehouse`。实现位于 `Source/Test/GHSDockTruckHUDWidget.*`、`GHSDockTruckDataComponent.*` 和现有 `GHSWarehousePlayerController.*`。

现已共用同一 HUD 接入 12 台电动堆高车，详见 `GHS_StackerHUD.md`。装卸车与堆高车按类型独立聚合：同一四等分区域可以同时显示两类标签，每类最多四个、合计最多八个活动标签；两类设备不会合并为同一组。

## 显示与操作

本地 `GHSWarehousePlayerController` 在 `BeginPlay` 中为 NormalWarehouse 自动创建 `TruckHUDWidget` 并加入视口，结束运行时移除。车辆数据组件在运行时创建，无需修改、重新保存地图或给每辆车手工放置 Widget。

- 点击单车标签展开该车详情；再次点击同车标签、详情右上角 `×` 或独立游戏中的 `Esc` 可收起。PIE 中 `Esc` 可能由编辑器用于退出运行。
- 当前弹簧臂长度达到聚合阈值时，游戏视口按宽、高各二等分形成 2×2 四象限。同区、同类型的多台设备聚合为数量标签，单台保留独立标签；每个区域的每类设备最多一个活动标签，因此装卸车最多四个、堆高车最多四个，跨区或跨类型均不合并。点击组标签打开每页五台、仅含本类型成员的列表，再点击指定设备进入详情。点击组标签可收起列表，点击空白处收起列表并继续交给相机处理。
- 镜头后方或视口外的车辆不显示；视口内每辆有效车都归属于一个活动标签，取消原先宽/窄画布 8/4 个标签的截断，以及上下寻找空位的避让方式。
- 未接数据时显示“待接入”和 `--`。不会自动生成装载量或假定连接正常。
- `bDemoData=true` 时，紧凑标签保留实际状态并额外显示“演示”标记，详情显示“演示数据”。

### 紧凑布局修订

详情卡由 `456×268` 调整为 `320×184` 逻辑像素，面积减少约 52%。内边距为 12，标题、身份、状态和关闭按钮集中在 50 高的头部；数量与单位相邻，月台与任务使用同一行，连接信息与装载进度收在底栏。数据字段保留，长编号、数量或订单在各自列内省略，避免侵入相邻内容。

常驻标签不再使用固定 `356×42` 宽框：高度为 34，宽度根据实际编号、状态和数量测量，最大约 275，并限制在四等分的单区宽度内。窄屏依次收紧编号和数值槽位，对长文字省略，保留状态和字号。分区布局、引线端点和鼠标点击范围共用实际尺寸。小视口仍保留原有最小物理字号缩放规则，不通过整体无限缩小来压缩空间。

### 聚合与动画

在 `GHS_WarehouseCamera` 实例或 `BP_GHS_WarehouseCamera` 的类默认值中，展开 **Warehouse Camera → HUD 聚合最小臂长**。参数 `HUDClusterMinArmLength` 默认为 **10000 cm**，支持实例编辑和蓝图读写。当前 `SpringArmComponent.TargetArmLength < HUDClusterMinArmLength` 时，所有可见车辆分别显示独立标签；达到或超过阈值时恢复四等分聚合。数值为 0 时始终允许聚合。依据是缩放插值过程中的当前臂长，不是最终目标 `DesiredZoom`。

近景独立标签跟随各自车辆，只约束视口边缘，不受四区中线和每类四标签数量限制，也不执行标签避让。阈值修改运行时生效；切换模式保留当前选中车辆，并复用已有聚合、拆分和详情动画。正在展开的成员列表在成员拆散后自动收起。

`GHSTruckHUDLayout` 按车辆锚点的归一化屏幕位置分区：列为 `floor(2*x/视口宽)`，行为 `floor(2*y/视口高)`，有效行列均为 0–1，分别对应左上、右上、左下、右下。分区后仅对同一区域的同类型设备成组，不依赖标签是否重叠；标签的重叠也不会把不同区域或不同类型连接成大组。视口尺寸来自当前 HUD 几何，与投影使用相同的 DPI/缩放换算，支持窗口、全屏、超宽屏和竖屏，分区始终为当前视口宽、高的一半。四等分仅作为分组规则，运行时不绘制分割线。

四等分只用于成员分组，标签位置不再限制在本格或固定类型分带内。组锚点始终是本组真实成员投影点的平均值，自然标签位置为 `Anchor - (标签宽度/2, 50)`，只做整个视口的边缘限制。聚合标签首次相互遮挡时按自然上下顺序做一次局部排布，在自然位置上下 40 逻辑像素内取所需的最小移动，自然高度相同时装卸车优先在上。此规则同样处理跨区或同类型标签的遮挡，成员仍严格按类型和象限分别归组；每组额外位移上限为 40 逻辑像素。该偏移锁定到稳定的组 key，其他标签离开或重入不会更改已锁定且仍存活的 key，也不逐帧累计避让。近景逐车显示沿用原来的跟随位置和整个视口边缘限制。

工程边界：极密情况下，若已锁定标签与 ±40 像素范围内无法得到可行排布，则保留当前局部位置，不通过扩大偏移把标签远推离设备。

成员按车辆 ID 排序并结合设备类型生成稳定标识，与距离排序和详情选择无关。车辆跨格持续 200 ms 后更新所属区域；短暂越过分界线再返回会取消这次更新。新增和离开的车辆立即更新计数；改变窗口大小时立即按新尺寸重算成员分区。组自身成员变化后生成新 key；保持成员的组持续跟随真实投影中心并保留其已确定的局部偏移，继续用已有局部动画衔接。

组标签为 `184×34`；成员面板宽 260，最多高 222，每页五条，页码和箭头访问余下成员。合并和拆分采用 120 ms 的源位置淡出、目标位置淡入，进入偏移 6 px，跟随滞后最多 8 px，不进行长距离汇入/飞散。详情和列表采用 220 ms 平滑插值，同时改变透明度、96%→100% 缩放与 8 px 位移；中途关闭、重新打开会从当前进度继续。面板首次打开时确定上下方向，跟随并约束在视口内；大距离换位直接重新定位并就地展开。

## 车辆身份与真实数据

车辆必须具有有效且唯一的 Actor Tags，例如：

```text
IndependentDockTruck
TwinId=GHS_DockTruck_002
Dock=2
```

运行时映射为 `TruckId=TRUCK-002`、`DockId=DOCK-02`。使用这些运行时标签识别车辆，不依赖编辑器 Actor Label。重复身份或格式错误的标签不会成为独立有效条目。

蓝图接入路径：

```text
Get Player Controller (0)
  → Cast To GHSWarehousePlayerController
  → TruckHUDWidget
  → GetTruckData("TRUCK-002")
  → Is Valid
  → SetTelemetry(18, 24, Loading, "OUT-1026", false)
```

上面的 `18 / 24` 仅示范参数位置；实际接入应传入业务系统提供的数值。最后一个参数 `false` 表示真实数据，手工演示必须使用 `true`。请检查 `SetTelemetry` 的布尔返回值；查车返回空值时，应等待 HUD 完成初始化并核对标签。

`SetTelemetry(Loaded, Total, NewStatus, NewOrderId, bDemoData)` 接受的运行状态为 `Docked`、`Loading`、`Warning`、`Fault`，数量必须满足 `0 <= Loaded <= Total` 且 `Total > 0`。非法更新返回 `false`，保留此前完整状态。已装 18、总数 24 时，`GetRemainingPallets()` 返回 6，`GetLoadingProgress()` 返回 0.75。

断线时由数据接入方主动调用：

```text
SetTelemetry(-1, -1, Offline, "", false)
```

`Offline` 和 `AwaitingData` 会清空旧数量及订单，剩余数量返回 `-1`、`HasTelemetry()` 返回 `false`。需要恢复等待接入状态时，将上例状态改为 `AwaitingData`。当前没有自动网络订阅或断线检测；接入方必须处理连接中断、超时及恢复，不能只停止发送更新。

其他蓝图接口：`GetRegisteredTruckCount()`、`GetVisibleLabelCount()`、`SelectTruckById()`、`ClearSelection()`、`GetSelectedTruckId()`。聚合查询和集成接口为 `GetVisibleLabels()`、`ToggleCluster(Key)`、`GetExpandedClusterMembers()`、`SetClusterPage(Page)`、`GetMemberRowPosition(TruckId)`。`GetVisibleLabelCount()` 只统计活动组，过渡中淡出的旧图形不重复计数；`GetVisibleLabelPosition(TruckId)` 返回该车所属组的位置。`HandlePointerClick()`、标签位置及面板位置均使用 Widget 局部坐标，已折算 DPI；不要直接传原始屏幕像素。

## 字体与构建

中文字体源文件为 `Content/GHSNormalWarehouse/HUD/Fonts/DroidSansFallback.ttf`。`Test.Build.cs` 已声明 `UMG`、`Slate`、`SlateCore` 依赖，并将该字体作为 `StagedFileType.NonUFS` 运行依赖打包；发布时保留对应文件路径，不依赖用户电脑安装字体。

在 PowerShell 中构建 Editor 目标，固定使用本机 UE 5.4 对应的 MSVC 14.38 工具链：

```powershell
& 'D:/UE/UE_5.4/Engine/Build/BatchFiles/Build.bat' TestEditor Win64 Development '-Project=D:/UEPro/Test/Test.uproject' -WaitMutex -NoHotReloadFromIDE '-CompilerVersion=14.38.33130'
```

原生代码更新后应使用新构建的模块启动编辑器。关闭已有编辑器前先保存当前工作。

## 复验命令与输出

2026-10-19 当前真实锚点与连续局部排布修订：Editor 编译退出码为 0；`Saved/Automation/HUDAnchorProximity/index.json` 于 14:57:57 记录 44 项 GHS 自动化通过，0 失败、0 警告。Full（14:58:00）、Narrow（14:58:20）、LowAngle（14:58:40 后）真实运行报告均为 `success: true`，每种 28 项检查通过，且 `assets_saved: false`。报告路径为 `Saved/GHS_StackerHUD_Runtime_<Full|Narrow|LowAngle>.json`。验证覆盖真实组中心、每组额外偏移不超过 40 逻辑像素、同类及跨区标签排布、存活 key 的位置稳定，以及设备状态、点击和 120 ms 局部动画。已检查实景 Full、Narrow 和 LowAngle 图像，标签贴近设备且无重叠；低角度截图为 `Saved/GHS_StackerHUD_SeparateTypesWide_LowAngle.png`。尚未进行完整打包构建。

2026-10-19 历史类型隔离与固定分带版本（位置方案已撤销）：Editor 编译退出码为 0；`Saved/Automation/HUDSeparateTypes/index.json` 于 14:33:50 记录 40 项 GHS 自动化通过，0 失败、0 警告。真实 Full 1920×1080（14:34:00）与 Narrow 360×800（14:34:20）各通过 28 项运行检查，两份报告均为 `success: true`、`assets_saved: false`。这些检查验证了当时的类型分带规则，但用户截图指出固定分带将标签推离所属设备，属于错误的位置方案；旧结果不能作为本次定位修订的通过证据。编辑器于 14:34:36 恢复时确认场景、12 台堆高车和 10000 cm 阈值。尚未进行完整打包构建。

以下均为更早版本的历史验证记录。

2026-10-19 历史堆高车与快速聚合修订：35 项 GHS 自动化通过；当时的堆高车/装卸车混合聚合场景 Full、Narrow 各 26 项通过；装卸车独立遥测 Full 20 项通过。聚合改为 120 ms 局部淡入淡出，新增 12 台堆高车与五种演示状态，详情见 `GHS_StackerHUD.md`。

2026-10-19 弹簧臂阈值修订：在 Warehouse Camera 分类暴露 `HUD 聚合最小臂长`，默认 10000 cm。Editor 构建成功，27 项 GHS 自动化全部通过（14 项布局测试），报告为 `Saved/Automation/TruckHUDThreshold/index.json`。编辑器中的场景实例和蓝图默认值均确认为 10000，详情面板已实际显示该参数。

实际场景在 Full 1920×1080（含运行中改为 1280×960）通过 30 项检查，Small 960×540、UltraWide 2560×1080、Portrait 800×1200、Narrow 360×800 各通过 28 项。覆盖当前臂长与目标臂长不同、运行时修改阈值、恰好等于阈值、逐车显示时超过四个标签、模式切换动画及选中详情保留。报告为 `Saved/GHS_TruckHUD_Clustering_<变体>.json`；新增 `ThresholdIndividualMid/End` 和 `ThresholdEqualMid/End` 截图。已检查近景独立标签的实际截图，未进行完整打包构建。

2026-10-19 四等分修订：按用户反馈把九等分调整为 2×2 四象限，聚合器与单车标签宽度共用分区常量。Editor 使用 MSVC 14.38.33130 构建成功；23 项 GHS 自动化全部通过，报告为 `Saved/Automation/TruckHUDQuadrants/index.json`。11 项布局测试全部覆盖四等分的实际中线、跨区确认、动态尺寸和身份守恒。

实际场景复验结果：Full 1920×1080（含运行中改为 1280×960）24 项、Small 960×540 22 项、UltraWide 2560×1080 23 项、Portrait 800×1200 23 项、Narrow 360×800 22 项均通过。报告仍为 `Saved/GHS_TruckHUD_Clustering_<变体>.json`，新增 `grid_dimensions: [2, 2]` 和 `maximum_active_labels: 4` 标识本次版本。已查看实际截图，确认同区聚合、跨区独立以及窄屏边界。Pencil 第四画板和 `.pen` 源文件已更新并保存，编辑器恢复至重启前的视角。

验证器使用与 Slate 相同的 float32 逻辑视口尺寸；Small 的非整数 DPI 下，以双精度直接重建宽度曾将恰好在中线的投影点误判到另一侧。尺寸精度统一后，严格四象限检查通过；生产聚合算法无需为此放宽边界。

以下为历史九等分及早期版本验证记录；当前行为以以上四等分说明为准。

2026-10-19 九宫格版复验：Editor 使用 MSVC 14.38.33130 构建成功，23 项 GHS 自动化全部通过，报告为 `Saved/Automation/TruckHUDGrid/index.json`。其中 11 项分区测试覆盖九格独立、同格远距离聚合、跨格不合并、不同尺寸归一化、动态改窗、跨界确认与抖动、身份和数量守恒、无效输入、标签边界及窄屏单车宽度。

实际仓库场景使用独立进程完成以下检查，所有报告均为成功。脚本独立投影车辆，按实际视口计算预期九宫格成员，并核对每个活动标签的全部边界均位于所属格内；同时复验分页选车、合并拆分、详情与列表逐帧开合。原遥测及长文本回归在 Full、Small 两种尺寸也通过。已检查实际截图，尚未进行完整打包构建。

| 运行变体 | 实际视口 | 通过检查数 |
|---|---|---|
| Full | 1920×1080，运行中改为 1280×960 | 24 |
| Small | 960×540 | 22 |
| UltraWide | 2560×1080 | 22 |
| Portrait | 800×1200 | 23 |
| Narrow | 360×800 | 22 |

使用 `Scripts/ghs/verify_truck_hud_clustering.py`，相应变体参数为 `-TruckHUDSmall`、`-TruckHUDUltraWide`、`-TruckHUDPortrait`、`-TruckHUDNarrow`，Full 不加变体参数。每个进程的 `-ResX`、`-ResY` 应匹配表中初始尺寸。结果为 `Saved/GHS_TruckHUD_Clustering_<变体>.json`，截图为 `Saved/GHS_TruckHUD_Cluster_*_<变体>.png`。

以下为早期版本的验证记录。

2026-10-19 初版聚合复验：Editor 构建成功；20 项 GHS 自动化全部通过（新增八项聚合测试），报告为 `Saved/Automation/TruckHUDClustering/index.json`。聚合运行脚本在 1920×1080、960×540 各通过 21 项检查：实际 52 辆车注册、投影内成员数量守恒、静止及轻微镜头扰动时分组稳定、实际点击翻页与关闭按钮、选择非首位成员、合并/拆分的连续位置与透明度、详情/列表逐帧开合，以及展开中关闭、关闭中重新打开。原遥测运行回归分别通过 19、20 项。实际截图确认卡片填充和边框都参与透明度过渡，中文及矢量分页箭头正常，小视口列表和详情没有越界。尚未进行完整打包构建。

聚合复验使用下方相同的独立进程参数，将 Python 路径替换为 `Scripts/ghs/verify_truck_hud_clustering.py`。输出为 `Saved/GHS_TruckHUD_Clustering_Full.json`、`Saved/GHS_TruckHUD_Clustering_Small.json`，包含逐帧活动组位置、成员、透明度和详情/列表进度；真实截图为 `Saved/GHS_TruckHUD_Cluster_*_Full.png`、`*_Small.png`。截图在请求后由 UE 后续帧渲染，因此请求帧进度不是图片的精确进度时间戳。

最终在编辑器 PIE 中使用实际鼠标点击两车聚合标签，再点击第二行 `TRUCK-027`，确认成员列表关闭、对应车辆详情展开，镜头没有因 HUD 点击转动。编辑器已恢复并停留在车辆区域运行预览；地图没有保存测试遥测。

2026-10-19 紧凑版复验：Editor 构建成功；现有 12 项 GHS 自动化测试全部通过，报告为 `Saved/Automation/TruckHUDCompact/index.json`。1920×1080、960×540 场景各通过 19 项运行检查，均关联 52 辆车，覆盖标签选择、关闭、待接入、演示更新、离线清空、长值和边界。已逐张检查演示与长值截图：中文正常，文字在各自列内省略，标签未越出视口；详情卡分别占屏约 2.84% 和 6.39%。尚未进行完整打包构建。

原版接入时还在 PIE 实际点击验证过 HUD 点击不转动相机、空白区域仍可拖动相机；紧凑修订保留该输入处理路径，将标签命中、避让和引线统一改为实际内容尺寸。

数据组件自动化与现有相机回归：

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEPro/Test/Test.uproject' -unattended -nop4 -nosplash -NullRHI '-ExecCmds=Automation RunTests GHS.' '-TestExit=Automation Test Queue Empty' -ReportExportPath=D:/UEPro/Test/Saved/Automation/TruckHUD -abslog=D:/UEPro/Test/Saved/Logs/GHS_TruckHUDAutomation.log
```

1920×1080 真实游戏验证：

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' 'D:/UEPro/Test/Test.uproject' /Game/Maps/GHS_CAD_NormalWarehouse -game -RenderOffscreen -windowed -ResX=1920 -ResY=1080 -ForceRes -nosplash -nop4 -unattended '-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_truck_hud_runtime.py' -abslog=D:/UEPro/Test/Saved/Logs/GHS_TruckHUDRuntime_Full.log
```

960×540 小视口验证：

```powershell
& 'D:/UE/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe' 'D:/UEPro/Test/Test.uproject' /Game/Maps/GHS_CAD_NormalWarehouse -game -RenderOffscreen -windowed -ResX=960 -ResY=540 -ForceRes -TruckHUDSmall -nosplash -nop4 -unattended '-ExecCmds=py D:/UEPro/Test/Scripts/ghs/verify_truck_hud_runtime.py' -abslog=D:/UEPro/Test/Saved/Logs/GHS_TruckHUDRuntime_Small.log
```

脚本运行于独立进程，按实际车辆标签数量验收，完成后自动退出。报告为 `Saved/GHS_TruckHUD_Runtime_Full.json`、`Saved/GHS_TruckHUD_Runtime_Small.json`；每种尺寸输出 `GHS_TruckHUD_Default_*`、`GHS_TruckHUD_Offline_*`、`GHS_TruckHUD_LongValues_*`、`GHS_TruckHUD_Demo_*` PNG。额外的长值场景使用显式演示数据检查紧凑布局边界；两种视口都会校验详情卡占用视口面积低于 7%。重复执行会更新这些验收输出。

截图使用 `Shot showui filename="..." -nosuffix`，包括 Slate/UMG；不要用通常不包含界面层的 `HighResShot` 代替。除报告中的身份、数据、交互及边界断言外，还需实际查看截图确认中文、演示标识和布局。演示遥测只在测试进程中设置，不保存到地图。
